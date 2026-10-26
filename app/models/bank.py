"""`bank_questions` collection repository — 可复用题目库（需求变更功能）.

本模块实现《需求变更说明》中的八条需求对应的数据层能力：

1. 保存常用题目            → :meth:`BankQuestionRepo.create`
2. 新建问卷时选用已有题目   → :meth:`BankQuestionRepo.get` + 问卷题目"快照"机制
3. 修改题目不影响已发布问卷 → 问卷题目存快照（title/type/options），题库改动不回写
4. 记录题目修改历史        → :meth:`BankQuestionRepo.history`
5. 同一题目的不同版本共存  → 一个版本一个文档，`root_id` 标识题目家族
6. 查看题目被哪些问卷使用  → :meth:`BankQuestionRepo.usage`
7. 建立题目库              → ``in_bank`` 标记 + 题库视图
8. 单个题目的跨问卷统计    → :meth:`StatisticsService.bank_statistics`（见 answers.py）

数据模型
--------
一个文档 = 一个**版本**::

    {
      "_id":        ObjectId,   # 版本 ID
      "root_id":    ObjectId,   # 题目家族 ID（同一题的所有版本共享）
      "version":    int,        # 版本号，家族内从 1 递增
      "parent_id":  ObjectId,   # 本版本派生自哪个版本（None = 初始版本）
      "title":      str,
      "type":       "single|multi|text|number",
      "options":    list|None,
      "required":   bool,
      "validation": dict,
      "owner_id":   ObjectId,   # 创建者（版本归属者）
      "visibility": "private|public",
      "shared_with": [ObjectId],
      "tags":       [str],
      "in_bank":    bool,       # 是否已加入题库
      "note":       str,        # 本次改动的说明
      "created_at": ISODate,
      "updated_at": ISODate,
      "deleted_at": ISODate|None
    }
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from bson import ObjectId
from pymongo.collection import Collection

from ..db import get_db
from ..validation import SUPPORTED_TYPES

VISIBILITIES = ("private", "public")


class BankError(RuntimeError):
    """题库操作的基础异常。"""


class BankPermissionError(BankError):
    """当前用户无权执行该操作。"""


class BankNotFoundError(BankError):
    """题库题目 / 版本不存在。"""


class BankValidationError(BankError):
    """题库题目内容不合法。"""


class BankQuestionRepo:
    """``bank_questions`` 集合的数据访问对象。"""

    def __init__(self, db=None):
        self._db = db if db is not None else get_db()
        self._coll: Collection = self._db["bank_questions"]

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        owner_id: ObjectId,
        type: str,
        title: str,
        options: Optional[list[str]] = None,
        required: bool = False,
        validation: Optional[dict] = None,
        visibility: str = "private",
        tags: Optional[list[str]] = None,
        in_bank: bool = True,
        note: str = "",
    ) -> dict:
        """保存一个新题目（版本 1）。

        对应需求一："用户可以创建题目并保存"。
        """
        type, title, options = self._check_content(type, title, options)

        now = dt.datetime.now(dt.timezone.utc)
        oid = ObjectId()
        doc: dict[str, Any] = {
            "_id": oid,
            "root_id": oid,          # 初始版本：家族 ID 即自身
            "version": 1,
            "parent_id": None,
            "title": title,
            "type": type,
            "options": options,
            "required": bool(required),
            "validation": validation or {},
            "owner_id": owner_id,
            "visibility": visibility if visibility in VISIBILITIES else "private",
            "shared_with": [],
            "tags": self._clean_tags(tags),
            "in_bank": bool(in_bank),
            "note": note or "",
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self._coll.insert_one(doc)
        return doc

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get(self, version_id: ObjectId, *, include_deleted: bool = False) -> Optional[dict]:
        doc = self._coll.find_one({"_id": version_id})
        if doc is None:
            return None
        if doc.get("deleted_at") and not include_deleted:
            return None
        return doc

    def get_or_raise(self, version_id: ObjectId, *, include_deleted: bool = False) -> dict:
        doc = self.get(version_id, include_deleted=include_deleted)
        if doc is None:
            raise BankNotFoundError(f"bank question version not found: {version_id}")
        return doc

    def latest(self, root_id: ObjectId, *, include_deleted: bool = False) -> Optional[dict]:
        """返回某个题目家族中版本号最高（最新）的版本。"""
        query: dict = {"root_id": root_id}
        if not include_deleted:
            query["deleted_at"] = None
        return self._coll.find_one(query, sort=[("version", -1)])

    def history(self, root_id: ObjectId) -> list[dict]:
        """返回某个题目家族的全部版本，按版本号升序（需求四 / 需求五）。"""
        cursor = self._coll.find({"root_id": root_id}).sort("version", 1)
        return list(cursor)

    def list_visible(
        self,
        user_id: ObjectId,
        *,
        keyword: str = "",
        tag: str = "",
        only_bank: bool = False,
        scope: str = "all",
        limit: int = 200,
    ) -> list[dict]:
        """列出当前用户可见的题目。

        可见范围 = 自己创建的 ∪ 别人共享给我的 ∪ 公开的。
        ``scope`` 可取 ``all`` / ``mine`` / ``shared``。
        """
        query: dict[str, Any] = {"deleted_at": None}
        if scope == "mine":
            query["owner_id"] = user_id
        elif scope == "shared":
            query["$or"] = [
                {"shared_with": user_id},
                {"visibility": "public", "owner_id": {"$ne": user_id}},
            ]
        else:
            query["$or"] = [
                {"owner_id": user_id},
                {"shared_with": user_id},
                {"visibility": "public"},
            ]
        if only_bank:
            query["in_bank"] = True
        if keyword:
            query["title"] = {"$regex": keyword, "$options": "i"}
        if tag:
            query["tags"] = tag

        docs = list(self._coll.find(query).sort("updated_at", -1).limit(limit))
        # 同一题目家族只保留最新版本，避免列表里出现 v1/v2/v3 重复条目
        seen: set = set()
        out: list[dict] = []
        for d in docs:
            if d["root_id"] in seen:
                continue
            seen.add(d["root_id"])
            out.append(d)
        return out

    # ------------------------------------------------------------------
    # 版本
    # ------------------------------------------------------------------

    def create_version(
        self,
        base_version_id: ObjectId,
        *,
        owner_id: ObjectId,
        title: Optional[str] = None,
        options: Optional[list[str]] = None,
        required: Optional[bool] = None,
        validation: Optional[dict] = None,
        note: str = "",
        tags: Optional[list[str]] = None,
        visibility: Optional[str] = None,
    ) -> dict:
        """基于某个版本创建一个新版本（需求五）。

        新版本与旧版本**同时存在**，互不影响；旧版本可继续被历史问卷引用。
        """
        base = self.get_or_raise(base_version_id)
        if base["owner_id"] != owner_id:
            raise BankPermissionError("only the owner can create a new version")

        new_title = title if title is not None else base["title"]
        new_options = options if options is not None else base.get("options")
        qtype, new_title, new_options = self._check_content(
            base["type"], new_title, new_options
        )

        root_id = base["root_id"]
        next_version = self._next_version_number(root_id)
        now = dt.datetime.now(dt.timezone.utc)

        doc: dict[str, Any] = {
            "_id": ObjectId(),
            "root_id": root_id,
            "version": next_version,
            "parent_id": base["_id"],
            "title": new_title,
            "type": qtype,
            "options": new_options,
            "required": base.get("required", False) if required is None else bool(required),
            "validation": base.get("validation", {}) if validation is None else validation,
            "owner_id": owner_id,
            "visibility": base.get("visibility", "private") if visibility is None else visibility,
            "shared_with": list(base.get("shared_with", [])),
            "tags": base.get("tags", []) if tags is None else self._clean_tags(tags),
            "in_bank": base.get("in_bank", True),
            "note": note or "",
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self._coll.insert_one(doc)
        return doc

    def restore(self, version_id: ObjectId, target_version_id: ObjectId, *, owner_id: ObjectId) -> dict:
        """把旧版本的内容恢复为一个新版本（需求四："可以恢复旧版本"）。"""
        target = self.get_or_raise(target_version_id)
        if target["owner_id"] != owner_id:
            raise BankPermissionError("only the owner can restore a version")
        return self.create_version(
            target_version_id,
            owner_id=owner_id,
            title=target["title"],
            options=target.get("options"),
            required=target.get("required", False),
            validation=target.get("validation", {}),
            note=f"恢复自 v{target['version']}",
        )

    def update(
        self,
        version_id: ObjectId,
        *,
        owner_id: ObjectId,
        title: Optional[str] = None,
        options: Optional[list[str]] = None,
        required: Optional[bool] = None,
        validation: Optional[dict] = None,
        note: str = "",
        tags: Optional[list[str]] = None,
        visibility: Optional[str] = None,
    ) -> dict:
        """"修改"题目。

        修改不会就地覆盖旧版本，而是**生成新版本**（需求三 / 需求五）：
        已经引用了旧版本的问卷保持原样。
        """
        return self.create_version(
            version_id,
            owner_id=owner_id,
            title=title,
            options=options,
            required=required,
            validation=validation,
            note=note,
            tags=tags,
            visibility=visibility,
        )

    def fork(self, version_id: ObjectId, *, user_id: ObjectId, note: str = "") -> dict:
        """把别人共享的题目复制到自己的题目库（自己成为新家族的拥有者）。"""
        base = self.get_or_raise(version_id)
        doc = self.create(
            owner_id=user_id,
            type=base["type"],
            title=base["title"],
            options=base.get("options"),
            required=base.get("required", False),
            validation=base.get("validation", {}),
            visibility="private",
            tags=base.get("tags", []),
            in_bank=True,
            note=note or f"复制自 v{base['version']}",
        )
        return doc

    # ------------------------------------------------------------------
    # 共享 / 题库
    # ------------------------------------------------------------------

    def share(
        self,
        version_id: ObjectId,
        *,
        owner_id: ObjectId,
        usernames: Optional[list[str]] = None,
        visibility: Optional[str] = None,
        add_usernames: Optional[list[str]] = None,
        remove_usernames: Optional[list[str]] = None,
    ) -> dict:
        """把题目共享给其他用户（需求二）。

        * ``visibility="public"``：所有用户可见
        * ``usernames``：覆盖式设置共享名单
        * ``add_usernames`` / ``remove_usernames``：增量调整共享名单
        """
        doc = self.get_or_raise(version_id)
        if doc["owner_id"] != owner_id:
            raise BankPermissionError("only the owner can share a question")

        update: dict[str, Any] = {}
        if visibility is not None:
            if visibility not in VISIBILITIES:
                raise BankValidationError(f"visibility must be one of {VISIBILITIES}")
            update["visibility"] = visibility

        shared = list(doc.get("shared_with", []))
        if usernames is not None:
            shared = self._resolve_usernames(usernames, replace=True)
        if add_usernames:
            for uid in self._resolve_usernames(add_usernames, replace=False):
                if uid not in shared:
                    shared.append(uid)
        if remove_usernames:
            removed = set(self._resolve_usernames(remove_usernames, replace=False))
            shared = [uid for uid in shared if uid not in removed]
        if usernames is not None or add_usernames or remove_usernames:
            update["shared_with"] = shared

        update["updated_at"] = dt.datetime.now(dt.timezone.utc)
        self._coll.update_one({"_id": version_id}, {"$set": update})
        return self.get_or_raise(version_id)

    def set_in_bank(self, version_id: ObjectId, *, owner_id: ObjectId, in_bank: bool) -> dict:
        """加入 / 移出题库（需求七）。"""
        doc = self.get_or_raise(version_id)
        if doc["owner_id"] != owner_id:
            raise BankPermissionError("only the owner can change the bank flag")
        self._coll.update_one(
            {"_id": version_id},
            {"$set": {"in_bank": bool(in_bank), "updated_at": dt.datetime.now(dt.timezone.utc)}},
        )
        return self.get_or_raise(version_id)

    def delete(self, version_id: ObjectId, *, owner_id: ObjectId) -> bool:
        """软删除一个版本。

        已被问卷使用的版本不允许删除（否则问卷里的题目会失去来源）。
        """
        doc = self.get_or_raise(version_id)
        if doc["owner_id"] != owner_id:
            raise BankPermissionError("only the owner can delete a question")
        if self.usage_count(version_id) > 0:
            raise BankValidationError("该题目已被问卷使用，无法删除")
        self._coll.update_one(
            {"_id": version_id},
            {"$set": {"deleted_at": dt.datetime.now(dt.timezone.utc), "in_bank": False}},
        )
        return True

    # ------------------------------------------------------------------
    # 使用情况（需求六）
    # ------------------------------------------------------------------

    def usage_count(self, version_id: ObjectId) -> int:
        return self._db["questions"].count_documents({"bank_ref.version_id": version_id})

    def family_usage_count(self, root_id: ObjectId) -> int:
        return self._db["questions"].count_documents({"bank_ref.root_id": root_id})

    def usage(self, version_id: ObjectId, *, root_id: Optional[ObjectId] = None) -> list[dict]:
        """返回引用了该题目（整个家族）的问卷列表（需求六）。

        返回字段：``survey_id`` / ``survey_title`` / ``survey_status`` /
        ``order`` / ``version`` / ``question_id`` / ``owner``。
        """
        doc = self.get(version_id)
        if doc is None:
            raise BankNotFoundError(f"bank question version not found: {version_id}")
        rid = root_id if root_id is not None else doc["root_id"]

        questions = list(
            self._db["questions"].find({"bank_ref.root_id": rid})
        )
        if not questions:
            return []

        survey_ids = {q["survey_id"] for q in questions}
        surveys = {
            s["_id"]: s
            for s in self._db["surveys"].find({"_id": {"$in": list(survey_ids)}})
        }

        version_by_id = {v["_id"]: v for v in self.history(rid)}

        out: list[dict] = []
        for q in questions:
            survey = surveys.get(q["survey_id"])
            ref = q.get("bank_ref") or {}
            vdoc = version_by_id.get(ref.get("version_id"))
            out.append(
                {
                    "question_id": q["_id"],
                    "survey_id": q["survey_id"],
                    "survey_title": survey["title"] if survey else "(问卷已删除)",
                    "survey_status": survey["status"] if survey else "deleted",
                    "order": q.get("order"),
                    "title": q.get("title"),
                    "version_id": ref.get("version_id"),
                    "version": (vdoc or {}).get("version"),
                    "is_current_version": ref.get("version_id") == version_id,
                }
            )
        out.sort(key=lambda r: (str(r["survey_title"]), r.get("order") or 0))
        return out

    # ------------------------------------------------------------------
    # 权限
    # ------------------------------------------------------------------

    @staticmethod
    def can_read(doc: dict, user_id: ObjectId) -> bool:
        """能否查看（并在自己的问卷中使用）该题目。"""
        if doc.get("owner_id") == user_id:
            return True
        if doc.get("visibility") == "public":
            return True
        return user_id in (doc.get("shared_with") or [])

    @staticmethod
    def can_write(doc: dict, user_id: ObjectId) -> bool:
        """能否修改 / 共享 / 删除该题目（仅拥有者）。"""
        return doc.get("owner_id") == user_id

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _next_version_number(self, root_id: ObjectId) -> int:
        latest = self._coll.find_one({"root_id": root_id}, sort=[("version", -1)])
        return (latest["version"] + 1) if latest else 1

    def _resolve_usernames(self, usernames: list[str], *, replace: bool) -> list[ObjectId]:
        """把用户名列表解析成用户 ID 列表。"""
        names = [u.strip() for u in usernames if u and u.strip()]
        if not names:
            return []
        found = list(self._db["users"].find({"username": {"$in": names}}, projection={"username": 1}))
        found_map = {u["username"]: u["_id"] for u in found}
        missing = [n for n in names if n not in found_map]
        if missing:
            raise BankValidationError(f"用户不存在: {', '.join(missing)}")
        return [found_map[n] for n in names]

    @staticmethod
    def _clean_tags(tags: Optional[list[str]]) -> list[str]:
        if not tags:
            return []
        out: list[str] = []
        for t in tags:
            t = (t or "").strip()
            if t and t not in out:
                out.append(t)
        return out

    @staticmethod
    def _check_content(
        type: str, title: str, options: Optional[list[str]]
    ) -> tuple[str, str, Optional[list[str]]]:
        """校验题型 / 题干 / 选项，返回规范化后的三元组。"""
        if type not in SUPPORTED_TYPES:
            raise BankValidationError(
                f"unsupported question type: {type!r}; expected one of {SUPPORTED_TYPES}"
            )
        if not isinstance(title, str) or not title.strip():
            raise BankValidationError("title is required")
        title = title.strip()
        if type in ("single", "multi"):
            if not options or not isinstance(options, list) or not all(
                isinstance(o, str) for o in options
            ):
                raise BankValidationError(
                    f"{type} question requires a non-empty list of string options"
                )
            options = [o.strip() for o in options]
        else:
            options = None
        return type, title, options


__all__ = [
    "BankQuestionRepo",
    "BankError",
    "BankPermissionError",
    "BankNotFoundError",
    "BankValidationError",
]
