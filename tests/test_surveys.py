"""Tests for app/models/surveys.py."""
from __future__ import annotations

import datetime as dt
import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from app.models import SurveyRepo, UserRepo
from app.models.surveys import SurveyStateError


class TestSurveyRepo:
    def _make_user(self, db):
        return UserRepo(db=db).create("alice", "password123")

    def test_create_and_get(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="Test Survey", owner_id=uid)
        survey = repo.get(sid)
        assert survey["title"] == "Test Survey"
        assert survey["status"] == "draft"
        assert survey["token"] is None

    def test_create_empty_title(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        with pytest.raises(SurveyStateError):
            repo.create(title="   ", owner_id=uid)

    def test_publish_generates_token(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        token = repo.publish(sid)
        assert isinstance(token, str)
        assert 6 <= len(token) <= 12
        assert repo.get(sid)["status"] == "published"
        assert repo.get(sid)["published_at"] is not None

    def test_publish_then_close(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        repo.publish(sid)
        repo.close(sid)
        assert repo.get(sid)["status"] == "closed"

    def test_cannot_close_draft(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        with pytest.raises(SurveyStateError):
            repo.close(sid)

    def test_cannot_publish_closed(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        repo.publish(sid)
        repo.close(sid)
        with pytest.raises(SurveyStateError):
            repo.publish(sid)

    def test_find_by_token(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        token = repo.publish(sid)
        survey = repo.find_by_token(token)
        assert survey["_id"] == sid

    def test_list_by_owner(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        for i in range(3):
            repo.create(title=f"Survey {i}", owner_id=uid)
        results = repo.list_by_owner(uid)
        assert len(results) == 3

    def test_set_deadline(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        deadline = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
        repo.set_deadline(sid, deadline)
        assert repo.get(sid)["deadline"] == deadline

    def test_is_open_for_submission_published(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        repo.publish(sid)
        assert repo.is_open_for_submission(repo.get(sid)) is True

    def test_is_open_for_submission_draft(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        assert repo.is_open_for_submission(repo.get(sid)) is False

    def test_is_open_for_submission_expired(self, db):
        uid = self._make_user(db)
        repo = SurveyRepo(db=db)
        sid = repo.create(title="S", owner_id=uid)
        repo.set_deadline(sid, dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc))
        repo.publish(sid)
        assert repo.is_open_for_submission(repo.get(sid)) is False
