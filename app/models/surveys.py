"""`surveys` collection repository.

Implements docs/数据库设计.md §4.2 and §9:

* status is a one-way state machine: ``draft → published → closed``
* publishing generates a unique 6-12 char alphanumeric ``token``
* ``deadline`` is enforced on submission, not on state mutation
"""
from __future__ import annotations

import datetime as dt
import secrets
import string
from typing import Any, Iterable, Optional

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from ..config import config
from ..db import get_db

VALID_STATUSES = ("draft", "published", "closed")
# transitions allowed by §4.2: draft → published → closed
_ALLOWED_TRANSITIONS = {
    "draft": ("published",),
    "published": ("closed",),
    "closed": (),
}

_TOKEN_ALPHABET = string.ascii_letters + string.digits


class SurveyStateError(RuntimeError):
    """Raised for illegal status transitions or publish precondition failures."""


class SurveyRepo:
    """Data-access object for the ``surveys`` collection."""

    def __init__(self, db=None):
        self._db = db if db is not None else get_db()
        self._coll: Collection = self._db["surveys"]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        title: str,
        owner_id: ObjectId,
        description: str = "",
        allow_anonymous: bool = False,
    ) -> ObjectId:
        if not isinstance(title, str) or not title.strip():
            raise SurveyStateError("title is required")
        doc: dict[str, Any] = {
            "title": title.strip(),
            "description": description or "",
            "allow_anonymous": bool(allow_anonymous),
            "owner_id": owner_id,
            "status": "draft",
            "token": None,
            "deadline": None,
            "created_at": dt.datetime.now(dt.timezone.utc),
            "published_at": None,
        }
        return self._coll.insert_one(doc).inserted_id

    def get(self, survey_id: ObjectId) -> Optional[dict]:
        return self._coll.find_one({"_id": survey_id})

    def find_by_token(self, token: str) -> Optional[dict]:
        return self._coll.find_one({"token": token})

    def list_by_owner(self, owner_id: ObjectId, *, limit: int = 50) -> list[dict]:
        cursor = (
            self._coll.find({"owner_id": owner_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        return list(cursor)

    def set_deadline(self, survey_id: ObjectId, deadline: Optional[dt.datetime]) -> None:
        self._coll.update_one({"_id": survey_id}, {"$set": {"deadline": deadline}})

    # ------------------------------------------------------------------
    # state machine
    # ------------------------------------------------------------------

    def publish(self, survey_id: ObjectId) -> str:
        """Transition ``draft → published``. Generates ``token``. Returns token."""
        survey = self.get(survey_id)
        if survey is None:
            raise SurveyStateError(f"survey not found: {survey_id}")
        self._assert_transition(survey["status"], "published")

        token = self._mint_token()
        now = dt.datetime.now(dt.timezone.utc)
        try:
            self._coll.update_one(
                {"_id": survey_id},
                {
                    "$set": {
                        "status": "published",
                        "token": token,
                        "published_at": now,
                    }
                },
            )
        except DuplicateKeyError:
            # extremely unlikely with 7-char alphanumeric pool — retry once
            token = self._mint_token()
            self._coll.update_one(
                {"_id": survey_id},
                {
                    "$set": {
                        "status": "published",
                        "token": token,
                        "published_at": now,
                    }
                },
            )
        return token

    def close(self, survey_id: ObjectId) -> None:
        survey = self.get(survey_id)
        if survey is None:
            raise SurveyStateError(f"survey not found: {survey_id}")
        self._assert_transition(survey["status"], "closed")
        self._coll.update_one({"_id": survey_id}, {"$set": {"status": "closed"}})

    def delete(self, survey_id: ObjectId, owner_id: ObjectId) -> bool:
        """Delete a survey and all its questions/submissions (owner only).

        Only draft surveys can be deleted. Returns True if the survey existed
        and was deleted.
        """
        survey = self.get(survey_id)
        if survey is None:
            return False
        if survey["owner_id"] != owner_id:
            raise PermissionError("not the owner")
        if survey["status"] != "draft":
            raise SurveyStateError("only draft surveys can be deleted")
        # cascade delete: submissions → questions → survey
        self._db["submissions"].delete_many({"survey_id": survey_id})
        self._db["questions"].delete_many({"survey_id": survey_id})
        result = self._coll.delete_one({"_id": survey_id})
        return result.deleted_count > 0

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def is_open_for_submission(self, survey: dict, *, now: Optional[dt.datetime] = None) -> bool:
        """Check whether a survey document currently accepts responses (§9).

        Returns ``True`` only if status is ``published`` AND ``deadline`` is
        either unset or in the future.
        """
        if survey is None:
            return False
        if survey.get("status") != "published":
            return False
        deadline = survey.get("deadline")
        if deadline is None:
            return True
        now = now or dt.datetime.now(dt.timezone.utc)
        # pymongo returns timezone-aware datetimes when tz_aware=True
        return deadline > now

    @staticmethod
    def _assert_transition(current: str, target: str) -> None:
        if target not in _ALLOWED_TRANSITIONS.get(current, ()):
            raise SurveyStateError(
                f"illegal status transition: {current} → {target} "
                f"(allowed: {_ALLOWED_TRANSITIONS.get(current, ())})"
            )

    def _mint_token(self) -> str:
        """Mint a unique token, sampling until uniqueness is confirmed.

        Length follows ``config.SURVEY_TOKEN_LEN``; the bound is 6-12 chars
        per the design doc, which the config slot validates.
        """
        if not (6 <= config.SURVEY_TOKEN_LEN <= 12):
            raise SurveyStateError("token length must be 6-12 characters")
        for _ in range(8):
            token = "".join(
                secrets.choice(_TOKEN_ALPHABET) for _ in range(config.SURVEY_TOKEN_LEN)
            )
            if self._coll.find_one({"token": token}, projection={"_id": 1}) is None:
                return token
        raise SurveyStateError("failed to mint a unique token after 8 attempts")


def iter_active_surveys(surveys: Iterable[dict]) -> list[dict]:
    """Filter helper used by the submission endpoint."""
    return [s for s in surveys if SurveyRepo().is_open_for_submission(s)]
