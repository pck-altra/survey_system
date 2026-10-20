"""`answers` collection repository + statistics aggregations.

The repository methods cover CRUD over a single submission. Aggregations
required by the assignment (统计测试) live in :class:`StatisticsService`.
"""
from __future__ import annotations

from typing import Any, Optional

from bson import ObjectId
from pymongo.collection import Collection

from ..db import get_db


class AnswerRepo:
    """Data-access object for the ``answers`` collection."""

    def __init__(self, db=None):
        self._db = db if db is not None else get_db()
        self._coll: Collection = self._db["answers"]

    def insert(self, *, response_id: ObjectId, question_id: ObjectId, value: Any) -> ObjectId:
        return self._coll.insert_one(
            {"response_id": response_id, "question_id": question_id, "value": value}
        ).inserted_id

    def list_by_response(self, response_id: ObjectId) -> list[dict]:
        return list(self._coll.find({"response_id": response_id}))

    def list_by_question(self, question_id: ObjectId) -> list[dict]:
        return list(self._coll.find({"question_id": question_id}))


class StatisticsService:
    """Aggregations across ``answers`` for a given ``survey_id``.

    Implements the queries from docs/数据库设计.md §8.
    """

    def __init__(self, db=None):
        self._db = db if db is not None else get_db()
        self._answers: Collection = self._db["answers"]
        self._questions: Collection = self._db["questions"]

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _questions_in_survey(self, survey_id: ObjectId, type: Optional[str] = None) -> dict:
        query: dict[str, Any] = {"survey_id": survey_id}
        if type is not None:
            query["type"] = type
        return {q["_id"]: q for q in self._questions.find(query)}

    # ------------------------------------------------------------------
    # aggregate queries
    # ------------------------------------------------------------------

    def single_choice_counts(self, survey_id: ObjectId) -> list[dict]:
        """每道单选题：每个选项有多少人选择。

        Returns ``[{question_id, order, title, counts: [{value, count}]}]``
        ordered by ``order``.
        """
        result = []
        for qid, q in self._questions_in_survey(survey_id, "single").items():
            pipeline = [
                {"$match": {"question_id": qid}},
                {"$group": {"_id": "$value", "count": {"$sum": 1}}},
                {"$sort": {"count": -1, "_id": 1}},
            ]
            counts = [
                {"value": item["_id"], "count": item["count"]}
                for item in self._answers.aggregate(pipeline)
            ]
            result.append(
                {
                    "question_id": qid,
                    "order": q["order"],
                    "title": q["title"],
                    "counts": counts,
                    "total": sum(c["count"] for c in counts),
                }
            )
        result.sort(key=lambda r: r["order"])
        return result

    def multi_choice_counts(self, survey_id: ObjectId) -> list[dict]:
        """每道多选题：每个选项被选多少次。

        Returns ``[{question_id, order, title, counts}]`` ordered by order.
        """
        result = []
        for qid, q in self._questions_in_survey(survey_id, "multi").items():
            pipeline = [
                {"$match": {"question_id": qid}},
                {"$unwind": "$value"},
                {"$group": {"_id": "$value", "count": {"$sum": 1}}},
                {"$sort": {"count": -1, "_id": 1}},
            ]
            counts = [
                {"value": item["_id"], "count": item["count"]}
                for item in self._answers.aggregate(pipeline)
            ]
            result.append(
                {
                    "question_id": qid,
                    "order": q["order"],
                    "title": q["title"],
                    "counts": counts,
                }
            )
        result.sort(key=lambda r: r["order"])
        return result

    def number_stats(self, survey_id: ObjectId) -> list[dict]:
        """每道数字题：平均值 / 中位数信息。

        Returns ``[{question_id, order, title, avg, n, min, max}]``.
        """
        result = []
        for qid, q in self._questions_in_survey(survey_id, "number").items():
            pipeline = [
                {"$match": {"question_id": qid}},
                {
                    "$group": {
                        "_id": None,
                        "avg": {"$avg": "$value"},
                        "n": {"$sum": 1},
                        "min": {"$min": "$value"},
                        "max": {"$max": "$value"},
                    }
                },
            ]
            docs = list(self._answers.aggregate(pipeline))
            if not docs:
                agg = {"avg": None, "n": 0, "min": None, "max": None}
            else:
                agg = {k: v for k, v in docs[0].items() if k != "_id"}
            result.append(
                {
                    "question_id": qid,
                    "order": q["order"],
                    "title": q["title"],
                    **agg,
                }
            )
        result.sort(key=lambda r: r["order"])
        return result

    def text_answers(self, survey_id: ObjectId) -> list[dict]:
        """每道文本题：所有填写内容列表。"""
        result = []
        for qid, q in self._questions_in_survey(survey_id, "text").items():
            cursor = self._answers.find({"question_id": qid}, projection={"value": 1})
            result.append(
                {
                    "question_id": qid,
                    "order": q["order"],
                    "title": q["title"],
                    "values": [doc["value"] for doc in cursor],
                }
            )
        result.sort(key=lambda r: r["order"])
        return result

    def total_submissions(self, survey_id: ObjectId) -> int:
        return self._db["responses"].count_documents(
            {"survey_id": survey_id, "submitted_at": {"$ne": None}}
        )

    def respondents(
        self, survey_id: ObjectId, *, include_usernames: bool
    ) -> list[dict]:
        """List submitted responses for a survey, newest first.

        When ``include_usernames`` is False (i.e. the survey is
        ``allow_anonymous``), usernames are returned as ``None`` so the
        caller cannot accidentally expose the attribution.
        """
        cursor = (
            self._db["responses"]
            .find(
                {"survey_id": survey_id, "submitted_at": {"$ne": None}},
                projection={"user_id": 1, "submitted_at": 1},
            )
            .sort("submitted_at", -1)
        )
        # Pre-load usernames in one query when attribution is allowed.
        user_map: dict = {}
        if include_usernames:
            user_ids = [
                r["user_id"] for r in cursor if r.get("user_id") is not None
            ]
            if user_ids:
                for u in self._db["users"].find(
                    {"_id": {"$in": user_ids}}, projection={"username": 1}
                ):
                    user_map[u["_id"]] = u["username"]
            # Re-execute cursor (we consumed it above) — small N so cheap.
            cursor = (
                self._db["responses"]
                .find(
                    {"survey_id": survey_id, "submitted_at": {"$ne": None}},
                    projection={"user_id": 1, "submitted_at": 1},
                )
                .sort("submitted_at", -1)
            )

        out: list[dict] = []
        for r in cursor:
            username = None
            if include_usernames:
                username = user_map.get(r.get("user_id"))
            out.append(
                {
                    "submission_id": r["_id"],
                    "username": username,
                    "submitted_at": r.get("submitted_at"),
                }
            )
        return out
