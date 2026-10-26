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

    # ------------------------------------------------------------------
    # 跨问卷统计（需求八）
    # ------------------------------------------------------------------

    def bank_statistics(
        self, root_id: ObjectId, *, version_ids: Optional[list[ObjectId]] = None
    ) -> dict:
        """统计某个题库题目（整个版本家族）在**所有问卷**中的回答情况。

        对应需求八："我希望能看某一道题在所有问卷中的回答情况"。

        Parameters
        ----------
        root_id:
            题库题目的家族 ID。
        version_ids:
            若给定，则只统计这些版本被引用的问卷题目；默认统计家族全部版本。

        Returns
        -------
        dict
            ``title`` / ``type`` / ``question_count`` / ``survey_count`` /
            ``total_answers`` / ``counts`` / ``avg`` / ``min`` / ``max`` /
            ``n`` / ``values`` / ``by_survey`` / ``by_version``。
        """
        query: dict[str, Any] = {"bank_ref.root_id": root_id}
        if version_ids is not None:
            query["bank_ref.version_id"] = {"$in": list(version_ids)}
        questions = list(self._questions.find(query))
        qids = [q["_id"] for q in questions]

        result: dict[str, Any] = {
            "question_count": len(questions),
            "survey_count": 0,
            "total_answers": 0,
            "counts": [],
            "avg": None,
            "min": None,
            "max": None,
            "n": 0,
            "values": [],
            "by_survey": [],
            "by_version": [],
        }
        if not qids:
            return result

        # 题干 / 题型：取该家族最新题目的类型
        latest = self._db["bank_questions"].find_one(
            {"root_id": root_id}, sort=[("version", -1)]
        )
        if latest:
            result["title"] = latest["title"]
            result["type"] = latest["type"]

        types = {q.get("type") for q in questions}
        qtype = next(iter(types)) if len(types) == 1 else "mixed"

        # 每个题目一行的原始计数
        per_question: dict[Any, int] = {}
        if qtype in ("single", "multi"):
            pipeline = [
                {"$match": {"question_id": {"$in": qids}}},
                {"$unwind": "$value"},
                {"$group": {"_id": {"q": "$question_id", "v": "$value"}, "count": {"$sum": 1}}},
            ]
            merged: dict[Any, int] = {}
            for item in self._answers.aggregate(pipeline):
                merged[item["_id"]["v"]] = merged.get(item["_id"]["v"], 0) + item["count"]
            result["counts"] = [
                {"value": v, "count": c} for v, c in sorted(merged.items(), key=lambda kv: (-kv[1], str(kv[0])))
            ]
            result["total_answers"] = sum(merged.values())
        elif qtype == "number":
            pipeline = [
                {"$match": {"question_id": {"$in": qids}}},
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
            if docs:
                result.update({k: v for k, v in docs[0].items() if k != "_id"})
            result["total_answers"] = result["n"]
        else:  # text / mixed
            cursor = self._answers.find({"question_id": {"$in": qids}}, projection={"value": 1})
            values = [d["value"] for d in cursor]
            result["values"] = values
            result["total_answers"] = len(values)

        # 每个问卷的作答次数
        survey_of_q = {q["_id"]: q["survey_id"] for q in questions}
        answer_counts = self._db["answers"].aggregate(
            [
                {"$match": {"question_id": {"$in": qids}}},
                {"$group": {"_id": "$question_id", "count": {"$sum": 1}}},
            ]
        )
        for item in answer_counts:
            per_question[item["_id"]] = item["count"]

        survey_counts: dict[Any, int] = {}
        version_counts: dict[Any, int] = {}
        questions_by_id = {q["_id"]: q for q in questions}
        for qid, count in per_question.items():
            sid = survey_of_q.get(qid)
            if sid is not None:
                survey_counts[sid] = survey_counts.get(sid, 0) + count
            ref = questions_by_id.get(qid, {}).get("bank_ref") or {}
            vid = ref.get("version_id")
            if vid is not None:
                version_counts[vid] = version_counts.get(vid, 0) + count

        survey_ids = list(survey_counts.keys())
        titles = {
            s["_id"]: s["title"]
            for s in self._db["surveys"].find({"_id": {"$in": survey_ids}}, projection={"title": 1})
        }
        result["survey_count"] = len(survey_ids)
        result["by_survey"] = [
            {"survey_id": sid, "title": titles.get(sid, "(问卷已删除)"), "count": c}
            for sid, c in sorted(survey_counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
        ]

        version_docs = {
            v["_id"]: v
            for v in self._db["bank_questions"].find({"root_id": root_id})
        }
        result["by_version"] = [
            {
                "version_id": vid,
                "version": (version_docs.get(vid) or {}).get("version"),
                "title": (version_docs.get(vid) or {}).get("title"),
                "count": c,
            }
            for vid, c in sorted(
                version_counts.items(),
                key=lambda kv: ((version_docs.get(kv[0]) or {}).get("version") or 0),
            )
        ]
        return result

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
