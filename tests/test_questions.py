"""Tests for app/models/questions.py."""
from __future__ import annotations

import pytest
from bson import ObjectId
from app.models import QuestionRepo, SurveyRepo, UserRepo
from app.models.questions import QuestionValidationError


class TestQuestionRepo:
    def _make_survey(self, db):
        uid = UserRepo(db=db).create("alice", "password123")
        return SurveyRepo(db=db).create(title="S", owner_id=uid)

    def test_add_single_question(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        qid = repo.add(sid, type="single", title="Gender", options=["M", "F"])
        assert qid is not None
        questions = repo.list_by_survey(sid)
        assert len(questions) == 1
        assert questions[0]["type"] == "single"
        assert questions[0]["options"] == ["M", "F"]

    def test_add_question_increments_order(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        repo.add(sid, type="single", title="Q1", options=["A"])
        repo.add(sid, type="single", title="Q2", options=["B"])
        questions = repo.list_by_survey(sid)
        assert [q["order"] for q in questions] == [1, 2]

    def test_add_multi_question(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        qid = repo.add(
            sid, type="multi", title="Fruits",
            options=["苹果", "香蕉", "西瓜"],
            validation={"min_count": 1, "max_count": 2},
        )
        q = repo.list_by_survey(sid)[0]
        assert q["type"] == "multi"
        assert q["validation"]["min_count"] == 1

    def test_add_text_question(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        repo.add(sid, type="text", title="自我介绍", validation={"min_len": 5, "max_len": 200})
        q = repo.list_by_survey(sid)[0]
        assert q["type"] == "text"
        assert q["validation"]["max_len"] == 200

    def test_add_number_question(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        repo.add(
            sid, type="number", title="年龄",
            validation={"min": 0, "max": 120, "integer_only": True},
        )
        q = repo.list_by_survey(sid)[0]
        assert q["type"] == "number"
        assert q["validation"]["integer_only"] is True

    def test_add_requires_options_for_single(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        with pytest.raises(QuestionValidationError):
            repo.add(sid, type="single", title="No options")

    def test_add_requires_options_for_multi(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        with pytest.raises(QuestionValidationError):
            repo.add(sid, type="multi", title="No options")

    def test_add_unsupported_type(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        with pytest.raises(QuestionValidationError):
            repo.add(sid, type="ranking", title="Rankings")

    def test_goto_valid_target(self, db):
        """goto to an existing order is allowed (no cycle)."""
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        # Q1→Q2, Q2→Q3, Q3→end  →  no cycle
        repo.add(sid, type="single", title="Q1", options=["A"])
        repo.add(sid, type="single", title="Q2", options=["B"])
        repo.add(sid, type="single", title="Q3", options=["C"],
                 next_rule={"mode": "default", "fallback": "end"})

    def test_goto_invalid_target_rejected(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        repo.add(sid, type="single", title="Q1", options=["A"])
        with pytest.raises(QuestionValidationError) as exc_info:
            repo.add(
                sid, type="single", title="Q2", options=["B"],
                # backward reference to order 0 (does not exist, never will)
                next_rule={"mode": "default", "fallback": 0},
            )
        assert "unknown order" in str(exc_info.value)

    def test_cycle_detection(self, db):
        """Q1→Q2 (forward), Q2→Q1 (back) = cycle detected when Q2 is added.

        Q1 uses ``fallback: 2`` which is a forward reference (Q2 doesn't exist
        yet). This passes the goto-existence check because we exclude
        ``ignore_order`` from the missing set, but the cycle is caught by the
        DFS once Q2 (order 2) is also in the graph.
        """
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        # Q1: fallback → 2 (forward reference; valid at this stage since we
        # only exclude the new node's own order from the missing-set check)
        repo.add(sid, type="single", title="Q1", options=["A"],
                 next_rule={"mode": "default", "fallback": 2})
        # Q2: fallback → 1; graph = {1:{2}, 2:{1}} → DFS 1→2→1 = cycle
        with pytest.raises(QuestionValidationError) as exc_info:
            repo.add(
                sid, type="single", title="Q2", options=["B"],
                next_rule={"mode": "default", "fallback": 1},
            )
        assert "cycle" in str(exc_info.value).lower()

    def test_delete_by_order(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        repo.add(sid, type="single", title="Q1", options=["A"])
        repo.add(sid, type="single", title="Q2", options=["B"])
        repo.delete_by_order(sid, 1)
        remaining = repo.list_by_survey(sid)
        assert len(remaining) == 1
        assert remaining[0]["order"] == 2

    def test_count_by_survey(self, db):
        sid = self._make_survey(db)
        repo = QuestionRepo(db=db)
        for _ in range(5):
            repo.add(sid, type="text", title="t")
        assert repo.count_by_survey(sid) == 5
