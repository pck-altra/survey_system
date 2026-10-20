"""Tests for app/models/responses.py."""
from __future__ import annotations

import pytest
from bson import ObjectId
from app.models import ResponseRepo, SurveyRepo, QuestionRepo, UserRepo
from app.models.responses import SubmissionError


class TestResponseRepo:
    def _setup(self, db, anonymous=False):
        uid = UserRepo(db=db).create("alice", "password123")
        self.survey_id = SurveyRepo(db=db).create(
            title="S", owner_id=uid, allow_anonymous=anonymous,
        )
        SurveyRepo(db=db).publish(self.survey_id)
        self.q_repo = QuestionRepo(db=db)
        # Q1: sequential (next), Q2: by_option A→3, B→end, Q3: end
        self.q_repo.add(self.survey_id, type="single", title="Q1", options=["A", "B"],
                         required=True,
                         next_rule={"mode": "default", "fallback": "next"})
        self.q_repo.add(self.survey_id, type="text", title="Q2",
                         validation={"min_len": 3}, required=True)
        self.q_repo.add(self.survey_id, type="text", title="Q3",
                         validation={"min_len": 1}, required=False)
        self.repo = ResponseRepo(db=db)
        self.uid = uid

    def test_start_published_survey(self, db):
        self._setup(db)
        rid = self.repo.start(self.survey_id, user_id=self.uid)
        assert rid is not None

    def test_start_draft_survey_rejected(self, db):
        uid = UserRepo(db=db).create("alice", "password123")
        sid = SurveyRepo(db=db).create(title="S", owner_id=uid)
        repo = ResponseRepo(db=db)
        with pytest.raises(SubmissionError):
            repo.start(sid, user_id=uid)

    def test_start_anonymous_attribution_recorded(self, db):
        """``allow_anonymous`` is now a stats-visibility flag, not an auth gate.

        A submission is always attributed to a user. The survey's
        ``allow_anonymous`` setting is recorded on the response as
        ``is_anonymous`` so the statistics endpoint can decide whether
        to expose the username.
        """
        self._setup(db, anonymous=True)
        rid = self.repo.start(self.survey_id, user_id=self.uid)
        resp = self.repo.find_by_id(rid)
        assert resp is not None
        assert resp["user_id"] == self.uid
        assert resp["is_anonymous"] is True

    def test_start_records_is_anonymous_false(self, db):
        self._setup(db, anonymous=False)
        rid = self.repo.start(self.survey_id, user_id=self.uid)
        resp = self.repo.find_by_id(rid)
        assert resp["is_anonymous"] is False

    def test_record_step_validates_required(self, db):
        self._setup(db)
        rid = self.repo.start(self.survey_id, user_id=self.uid)
        questions = {q["order"]: q for q in self.q_repo.list_by_survey(self.survey_id)}
        # Q1 is single-choice, required=True; value=None should fail
        with pytest.raises(SubmissionError):
            self.repo.record_step(rid, order=1, value=None,
                                  next_rule={"mode": "default", "fallback": "next"},
                                  questions_by_order=questions)

    def test_record_step_records_answer(self, db):
        self._setup(db)
        rid = self.repo.start(self.survey_id, user_id=self.uid)
        questions = {q["order"]: q for q in self.q_repo.list_by_survey(self.survey_id)}
        _, nxt = self.repo.record_step(
            rid, order=1, value="A",
            next_rule={"mode": "default", "fallback": "next"},
            questions_by_order=questions,
        )
        assert nxt == 2  # advances to next question
        # check answer stored
        ans = db["answers"].find_one({"response_id": rid})
        assert ans["value"] == "A"
        # check path recorded
        resp = self.repo.find_by_id(rid)
        assert resp["answer_path"] == [1]

    def test_record_step_with_by_option_routing(self, db):
        """Q1's by_option routing: selecting B jumps to order 3."""
        uid = UserRepo(db=db).create("alice", "password123")
        sid = SurveyRepo(db=db).create(title="S", owner_id=uid)
        SurveyRepo(db=db).publish(sid)
        q_repo = QuestionRepo(db=db)
        # Order matters: Q1 first so it gets order=1, then Q2 (order 2), then Q3 (order 3).
        # Q1's goto:3 must reference an order that exists at save time.
        q_repo.add(sid, type="single", title="Q1", options=["A", "B"],
                    required=True,
                    next_rule={"mode": "by_option",
                               "branches": [{"when": "B", "goto": 3}],
                               "fallback": "next"})
        q_repo.add(sid, type="text", title="Q2", validation={"min_len": 1}, required=False)
        q_repo.add(sid, type="text", title="Q3", validation={"min_len": 1}, required=False)
        repo = ResponseRepo(db=db)
        rid = repo.start(sid, user_id=uid)
        questions = {q["order"]: q for q in q_repo.list_by_survey(sid)}
        # Q1 with "B" → goto: 3
        _, nxt = repo.record_step(
            rid, order=1, value="B",
            next_rule=questions[1]["next_rule"],
            questions_by_order=questions,
        )
        assert nxt == 3  # explicit goto 3

    def test_finalize(self, db):
        self._setup(db)
        rid = self.repo.start(self.survey_id, user_id=self.uid)
        resp = self.repo.finalize(rid)
        assert resp["submitted_at"] is not None

    def test_list_by_survey(self, db):
        self._setup(db)
        for _ in range(3):
            rid = self.repo.start(self.survey_id, user_id=self.uid)
            self.repo.finalize(rid)
        results = self.repo.list_by_survey(self.survey_id)
        assert len(results) == 3

    def test_count_by_survey(self, db):
        self._setup(db)
        for _ in range(2):
            rid = self.repo.start(self.survey_id, user_id=self.uid)
            self.repo.finalize(rid)
        assert self.repo.count_by_survey(self.survey_id) == 2
