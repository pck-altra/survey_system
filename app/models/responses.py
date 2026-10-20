"""`responses` collection repository.

Implements docs/数据库设计.md §4.4.

A response represents one fill-out session. The actual answers live in
``answers``; ``responses.answer_path`` records the orders that were
actually visited so an audit can replay the session without re-running
the routing engine.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from bson import ObjectId
from pymongo.collection import Collection

from ..db import get_db
from ..routing import resolve
from ..validation import ValidationError
from .surveys import SurveyRepo
from .questions import QuestionRepo


class SubmissionError(RuntimeError):
    """Raised when a submission violates the schema or submission rules."""


class ResponseRepo:
    """Data-access object for the ``responses`` collection."""

    def __init__(self, db=None):
        self._db = db if db is not None else get_db()
        self._coll: Collection = self._db["responses"]
        # collaborators
        self._surveys = SurveyRepo(db=self._db)
        self._questions = QuestionRepo(db=self._db)

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------

    def start(
        self,
        survey_id: ObjectId,
        *,
        user_id: ObjectId,
        duration_ms: Optional[int] = None,
    ) -> ObjectId:
        """Create a blank response document.

        Caller fills in ``answer_path`` and the corresponding ``answers``
        records before calling :meth:`finalize`.

        ``user_id`` is mandatory — every submission is attributed to a
        logged-in user. The survey's ``allow_anonymous`` flag is recorded
        on the response as ``is_anonymous`` so the statistics view can
        decide whether to expose the username.

        Raises
        ------
        SubmissionError
            if the survey is closed or missing.
        """
        survey = self._surveys.get(survey_id)
        if survey is None:
            raise SubmissionError(f"survey {survey_id} not found")
        if not self._surveys.is_open_for_submission(survey):
            raise SubmissionError("survey is not accepting submissions")

        doc: dict[str, Any] = {
            "survey_id": survey_id,
            "user_id": user_id,
            "is_anonymous": bool(survey.get("allow_anonymous", False)),
            "submitted_at": None,
            "answer_path": [],
            "duration_ms": duration_ms,
        }
        return self._coll.insert_one(doc).inserted_id

    def record_step(
        self,
        response_id: ObjectId,
        *,
        order: int,
        value: Any,
        next_rule: dict,
        questions_by_order: dict[int, dict],
    ) -> tuple[ObjectId, Any]:
        """Append an answer to the response, advance the path.

        Returns the new ``answer_id`` and the resolved ``next`` target
        (``int order``, ``"end"`` or ``"next"``).
        """
        question = questions_by_order[order]
        try:
            self._questions.validate_answer_for_question(question, value)
        except ValidationError as exc:
            raise SubmissionError(str(exc)) from exc

        answer_id = self._db["answers"].insert_one(
            {"response_id": response_id, "question_id": question["_id"], "value": value}
        ).inserted_id

        # advance path
        self._coll.update_one(
            {"_id": response_id},
            {"$push": {"answer_path": order}},
        )

        # compute next step
        next_target = resolve(next_rule, value)
        if next_target == "next":
            nxt = self._next_order(questions_by_order, after=order)
        elif next_target == "end":
            nxt = "end"
        else:
            nxt = next_target
        return answer_id, nxt

    def finalize(
        self,
        response_id: ObjectId,
        *,
        duration_ms: Optional[int] = None,
    ) -> dict:
        """Stamp ``submitted_at`` and return the final response document."""
        update: dict[str, Any] = {
            "submitted_at": dt.datetime.now(dt.timezone.utc),
        }
        if duration_ms is not None:
            update["duration_ms"] = duration_ms
        self._coll.update_one({"_id": response_id}, {"$set": update})
        return self._coll.find_one({"_id": response_id})

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def find_by_id(self, response_id: ObjectId) -> Optional[dict]:
        return self._coll.find_one({"_id": response_id})

    def list_by_survey(
        self,
        survey_id: ObjectId,
        *,
        submitted_only: bool = True,
        limit: int = 200,
    ) -> list[dict]:
        query: dict[str, Any] = {"survey_id": survey_id}
        if submitted_only:
            query["submitted_at"] = {"$ne": None}
        cursor = self._coll.find(query).sort("submitted_at", -1).limit(limit)
        return list(cursor)

    def count_by_survey(self, survey_id: ObjectId) -> int:
        return self._coll.count_documents(
            {"survey_id": survey_id, "submitted_at": {"$ne": None}}
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _next_order(questions_by_order: dict[int, dict], *, after: int) -> Any:
        """Find the next visitable order strictly greater than ``after``."""
        candidates = sorted(o for o in questions_by_order if o > after)
        return candidates[0] if candidates else "end"
