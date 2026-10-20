"""MongoDB client and database access.

This module owns the single `MongoClient` for the whole application.
Call :func:`get_db` from anywhere to obtain the active database handle.

Follows the design in ``docs/数据库设计.md``:

* collection names: ``users``, ``surveys``, ``questions``,
  ``responses``, ``answers``
* all indexes in §7 are created via :func:`ensure_indexes`
"""
from __future__ import annotations

from typing import Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from .config import config

# ---------------------------------------------------------------------------
# MongoClient lifecycle
# ---------------------------------------------------------------------------

_client: Optional[MongoClient] = None


def _build_client() -> MongoClient:
    """Create a new MongoClient.

    Using ``tz_aware=True`` makes all ``datetime`` round-trips unambiguous
    with the ``ISODate`` types declared in the design doc.
    """
    return MongoClient(
        config.MONGO_URI,
        tz_aware=True,
        serverSelectionTimeoutMS=config.MONGO_TIMEOUT_MS,
        maxPoolSize=50,
        minPoolSize=1,
    )


def get_client() -> MongoClient:
    """Return the process-wide MongoClient (lazy singleton)."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def get_db(db_name: Optional[str] = None) -> Database:
    """Return the active database handle.

    Parameters
    ----------
    db_name:
        Optional explicit database name. Defaults to ``config.MONGO_DB``.
        Tests pass an isolated name to avoid polluting ``survey_system``.
    """
    name = db_name if db_name is not None else config.MONGO_DB
    return get_client()[name]


def reset_client() -> None:
    """Drop the cached client. Intended for tests / process shutdown."""
    global _client
    if _client is not None:
        _client.close()
    _client = None


# ---------------------------------------------------------------------------
# Indexes (docs/数据库设计.md §7)
# ---------------------------------------------------------------------------


def ensure_indexes(db: Optional[Database] = None) -> None:
    """Idempotently create every index declared in the design document.

    Safe to call repeatedly: ``create_index`` is a no-op for an index
    whose key spec + options already exist.
    """
    db = db if db is not None else get_db()

    # users
    db["users"].create_index([("username", ASCENDING)], unique=True, name="uniq_username")

    # surveys
    db["surveys"].create_index(
        [("owner_id", ASCENDING), ("created_at", DESCENDING)],
        name="owner_created",
    )
    db["surveys"].create_index([("token", ASCENDING)], name="idx_token"),
    # NOTE: we deliberately do NOT make this index unique. Multiple drafts can
    # have token=null; uniqueness is enforced at publish time when the token
    # is minted and the field is updated to a non-null value.
    db["surveys"].create_index(
        [("status", ASCENDING), ("deadline", ASCENDING)],
        name="status_deadline",
    )

    # questions
    db["questions"].create_index(
        [("survey_id", ASCENDING), ("order", ASCENDING)],
        unique=True,
        name="uniq_survey_order",
    )
    db["questions"].create_index(
        [("survey_id", ASCENDING), ("type", ASCENDING)],
        name="survey_type",
    )

    # responses
    db["responses"].create_index(
        [("survey_id", ASCENDING), ("submitted_at", DESCENDING)],
        name="survey_submitted",
    )
    db["responses"].create_index(
        [("survey_id", ASCENDING), ("user_id", ASCENDING)],
        name="survey_user",
    )

    # answers
    db["answers"].create_index([("response_id", ASCENDING)], name="response")
    db["answers"].create_index([("question_id", ASCENDING)], name="question")
