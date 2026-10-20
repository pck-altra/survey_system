#!/usr/bin/env python
"""Seed the database with sample data for development / manual testing.

Usage::

    python -m app.scripts.seed

Clears existing data from all collections before inserting so it is
safe to re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId
from app import get_db, ensure_indexes
from app.models import UserRepo, SurveyRepo, QuestionRepo


def _oid() -> ObjectId:
    return ObjectId()


def main() -> None:
    db = get_db()
    ensure_indexes(db)

    # wipe existing data
    for coll in ["answers", "responses", "questions", "surveys", "users"]:
        db[coll].delete_many({})
    print("[seed] cleared existing data.")

    users = UserRepo(db=db)
    surveys = SurveyRepo(db=db)
    questions = QuestionRepo(db=db)

    # ── user ──────────────────────────────────────────────────────────────
    uid_alice = users.create("alice", "password123")
    uid_bob = users.create("bob", "secret456")
    print(f"[seed] created users: alice={uid_alice}, bob={uid_bob}")

    # ── survey 1: published with deadline ─────────────────────────────────
    sid1 = surveys.create(
        title="大一新生调研",
        owner_id=uid_alice,
        description="了解大一新生的学习与生活习惯",
        allow_anonymous=False,
    )
    surveys.set_deadline(sid1, None)  # no deadline

    q1 = questions.add(
        sid1, type="single", title="你的性别",
        options=["男", "女", "其他"],
        required=True,
        next_rule={"mode": "by_option", "branches": [
            {"when": "男", "goto": 2},
            {"when": "女", "goto": 3},
        ], "fallback": "next"},
    )
    q2 = questions.add(
        sid1, type="number", title="你的年龄",
        required=True,
        validation={"min": 14, "max": 30, "integer_only": True},
        next_rule={"mode": "by_range", "branches": [
            {"when": {"op": ">=", "value": 18}, "goto": 4},
            {"when": {"op": "<", "value": 18}, "goto": 5},
        ], "fallback": "next"},
    )
    q3 = questions.add(
        sid1, type="multi", title="你喜欢的运动（可多选）",
        options=["跑步", "游泳", "篮球", "足球", "瑜伽"],
        required=False,
        validation={"min_count": 1, "max_count": 3},
        next_rule={"mode": "by_contains", "branches": [
            {"when_any": ["篮球", "足球"], "goto": 4},
        ], "fallback": "next"},
    )
    q4 = questions.add(
        sid1, type="text", title="请简单介绍一下你自己",
        required=True,
        validation={"min_len": 5, "max_len": 200},
    )
    q5 = questions.add(
        sid1, type="single", title="你是否满意当前的生活状态",
        options=["非常满意", "满意", "一般", "不满意"],
        required=True,
    )
    surveys.publish(sid1)
    print(f"[seed] created & published survey 1: {sid1} (token: {surveys.get(sid1)['token']})")

    # ── survey 2: draft ───────────────────────────────────────────────────
    sid2 = surveys.create(
        title="课程反馈问卷",
        owner_id=uid_bob,
        description="收集同学们对课程的意见与建议",
        allow_anonymous=True,
    )
    questions.add(
        sid2, type="single", title="你对本课程的总体评价",
        options=["非常好", "较好", "一般", "较差"],
        required=True,
    )
    questions.add(
        sid2, type="multi", title="你希望加强哪些教学内容（可多选）",
        options=["理论讲解", "案例分析", "实验操作", "课后作业"],
        required=False,
    )
    questions.add(
        sid2, type="number", title="你每周在本课程上花费的学习时间（小时）",
        required=True,
        validation={"min": 0, "max": 40, "integer_only": False},
    )
    questions.add(
        sid2, type="text", title="你对课程改进有什么建议？",
        required=False,
        validation={"max_len": 500},
    )
    print(f"[seed] created draft survey 2: {sid2}")

    # ── survey 3: closed ──────────────────────────────────────────────────
    sid3 = surveys.create(
        title="2024年度员工满意度调查",
        owner_id=uid_alice,
        allow_anonymous=False,
    )
    questions.add(
        sid3, type="single", title="你对公司整体满意吗",
        options=["非常满意", "满意", "一般", "不满意", "非常不满意"],
        required=True,
    )
    questions.add(sid3, type="text", title="请说明原因", required=False)
    surveys.publish(sid3)
    surveys.close(sid3)
    print(f"[seed] created & closed survey 3: {sid3}")

    print("\n[seed] ✓ seed complete")
    print(f"  Login: alice/password123  bob/secret456")
    for s in [surveys.get(sid1), surveys.get(sid2), surveys.get(sid3)]:
        print(f"  [{s['_id']}] {s['title']!r}  status={s['status']}  token={s.get('token')}")


if __name__ == "__main__":
    main()
