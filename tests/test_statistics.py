"""Tests for app/models/answers.py — StatisticsService."""
from __future__ import annotations

import pytest
from bson import ObjectId
from app.models import AnswerRepo, ResponseRepo, SurveyRepo, QuestionRepo, UserRepo
from app.models.answers import StatisticsService


class TestStatisticsService:
    def _setup_with_submissions(self, db):
        uid = UserRepo(db=db).create("alice", "password123")
        sid = SurveyRepo(db=db).create(title="S", owner_id=uid)
        SurveyRepo(db=db).publish(sid)
        q_repo = QuestionRepo(db=db)
        q_repo.add(sid, type="single", title="Gender", options=["男", "女"])
        q_repo.add(sid, type="multi", title="Sports", options=["跑步", "游泳", "篮球"])
        q_repo.add(sid, type="number", title="Age", validation={"min": 0, "max": 120})
        q_repo.add(sid, type="text", title="Comment")

        resp_repo = ResponseRepo(db=db)
        ans_repo = AnswerRepo(db=db)
        questions = {q["order"]: q for q in q_repo.list_by_survey(sid)}

        def submit(choices: list, ages: list, comments: list):
            rid = resp_repo.start(sid, user_id=uid)
            resp_repo.record_step(rid, order=1, value=choices[0],
                                  next_rule=questions[1]["next_rule"],
                                  questions_by_order=questions)
            resp_repo.record_step(rid, order=2, value=choices[1],
                                  next_rule=questions[2]["next_rule"],
                                  questions_by_order=questions)
            resp_repo.record_step(rid, order=3, value=ages[0],
                                  next_rule=questions[3]["next_rule"],
                                  questions_by_order=questions)
            resp_repo.record_step(rid, order=4, value=comments[0],
                                  next_rule=questions[4]["next_rule"],
                                  questions_by_order=questions)
            resp_repo.finalize(rid)

        # 3 submissions
        submit(["男", ["跑步"]], [20], ["I like sports"])
        submit(["女", ["跑步", "游泳"]], [22], ["Great"])
        submit(["男", ["篮球"]], [19], ["Basketball fan"])

        return sid, StatisticsService(db=db)

    def test_single_choice_counts(self, db):
        sid, stats = self._setup_with_submissions(db)
        result = stats.single_choice_counts(sid)
        assert len(result) == 1
        r = result[0]
        assert r["title"] == "Gender"
        vals = {item["value"]: item["count"] for item in r["counts"]}
        assert vals["男"] == 2
        assert vals["女"] == 1
        assert r["total"] == 3

    def test_multi_choice_counts(self, db):
        sid, stats = self._setup_with_submissions(db)
        result = stats.multi_choice_counts(sid)
        assert len(result) == 1
        vals = {item["value"]: item["count"] for item in result[0]["counts"]}
        assert vals["跑步"] == 2
        assert vals["游泳"] == 1
        assert vals["篮球"] == 1

    def test_number_stats(self, db):
        sid, stats = self._setup_with_submissions(db)
        result = stats.number_stats(sid)
        assert len(result) == 1
        r = result[0]
        assert r["n"] == 3
        assert r["avg"] == pytest.approx(20.3333, rel=1e-3)
        assert r["min"] == 19
        assert r["max"] == 22

    def test_text_answers(self, db):
        sid, stats = self._setup_with_submissions(db)
        result = stats.text_answers(sid)
        assert len(result) == 1
        assert len(result[0]["values"]) == 3
        assert "I like sports" in result[0]["values"]

    def test_total_submissions(self, db):
        sid, stats = self._setup_with_submissions(db)
        assert stats.total_submissions(sid) == 3
