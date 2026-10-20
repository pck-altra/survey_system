"""Pytest fixtures shared by all test modules."""
from __future__ import annotations

import pytest
from bson import ObjectId
from app import get_db, reset_client, ensure_indexes
from app.config import config


# Reduce connection pool size for tests to avoid "Too many open files" on
# resource-constrained MongoDB instances (e.g. local laptop install).
_original_timeout = config.MONGO_TIMEOUT_MS
config.MONGO_TIMEOUT_MS = 10000


@pytest.fixture(scope="function")
def db():
    """Return an isolated test database and clean up after each test.

    The test database name is ``survey_system_test_<random>`` so parallel
    test runs (or any two test sessions) never interfere.
    """
    test_db = f"survey_system_test_{ObjectId()}"
    db = get_db(test_db)
    ensure_indexes(db)

    yield db

    # teardown — drop all collections
    for coll in ["answers", "responses", "questions", "surveys", "users"]:
        try:
            db[coll].drop()
        except Exception:
            pass  # ignore if MongoDB is temporarily unreachable

    reset_client()
