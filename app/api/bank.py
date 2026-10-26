"""题库 / 可复用题目 API（需求变更）。

前缀 ``/api/bank``。覆盖《需求变更说明》的八条需求：

===========  ==========================================================
需求          端点
===========  ==========================================================
一 保存题目    ``POST   /api/bank/questions``
二 分享题目    ``POST   /api/bank/questions/{id}/share``
三 不影响旧问卷  ``PUT    /api/bank/questions/{id}``（生成新版本）
四 修改历史    ``GET    /api/bank/questions/{id}/versions``
              ``POST   /api/bank/questions/{id}/versions/{vid}/restore``
五 版本共存    ``POST   /api/bank/questions/{id}/versions``
六 使用情况    ``GET    /api/bank/questions/{id}/usage``
七 题库管理    ``POST   /api/bank/questions/{id}/bank`` + ``GET /questions?only_bank=true``
八 跨问卷统计  ``GET    /api/bank/questions/{id}/statistics``
===========  ==========================================================
"""
from __future__ import annotations

from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..models import BankQuestionRepo, StatisticsService
from ..models.bank import (
    BankError,
    BankNotFoundError,
    BankPermissionError,
    BankValidationError,
)
from .deps import CurrentUser, DbDep
from .schemas import (
    BankHistoryItem,
    BankHistoryOut,
    BankQuestionCreate,
    BankQuestionOut,
    BankQuestionUpdate,
    BankShare,
    BankStatsOut,
    BankUsageItem,
    BankUsageOut,
    BankVersionCreate,
    BankVersionCount,
    BankSurveyCount,
    ChoiceCountItem,
)

router = APIRouter()


# ── helpers ───────────────────────────────────────────────────────────────────


def _oid(value: str, field: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid {field}")


def _username_map(db, user_ids: list[ObjectId]) -> dict[ObjectId, str]:
    if not user_ids:
        return {}
    return {
        u["_id"]: u["username"]
        for u in db["users"].find({"_id": {"$in": user_ids}}, projection={"username": 1})
    }


def _bank_out(repo: BankQuestionRepo, doc: dict, user: dict, db) -> BankQuestionOut:
    """把题库文档转换成响应模型。"""
    uid = user["_id"]
    shared_ids = list(doc.get("shared_with") or [])
    names = _username_map(db, shared_ids + [doc["owner_id"]])
    latest = repo.latest(doc["root_id"])
    parent = None
    if doc.get("parent_id"):
        parent = repo.get(doc["parent_id"], include_deleted=True)
    return BankQuestionOut(
        id=str(doc["_id"]),
        root_id=str(doc["root_id"]),
        version=doc["version"],
        parent_id=str(doc["parent_id"]) if doc.get("parent_id") else None,
        title=doc["title"],
        type=doc["type"],
        options=doc.get("options"),
        required=bool(doc.get("required", False)),
        validation=doc.get("validation", {}) or {},
        owner_id=str(doc["owner_id"]),
        owner_username=names.get(doc["owner_id"]),
        visibility=doc.get("visibility", "private"),
        shared_with=[names.get(i, str(i)) for i in shared_ids],
        tags=list(doc.get("tags") or []),
        in_bank=bool(doc.get("in_bank", False)),
        note=doc.get("note", ""),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        usage_count=repo.usage_count(doc["_id"]),
        can_edit=BankQuestionRepo.can_write(doc, uid),
        is_latest=bool(latest and latest["_id"] == doc["_id"]),
        derived_from_title=(parent or {}).get("title"),
    )


def _handle_bank_error(exc: BankError) -> HTTPException:
    if isinstance(exc, BankNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, BankPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.post("/questions", response_model=BankQuestionOut, status_code=status.HTTP_201_CREATED)
def create_bank_question(
    body: BankQuestionCreate,
    current_user: CurrentUser,
    db: DbDep = None,
) -> BankQuestionOut:
    """保存一个常用题目（需求一）。"""
    repo = BankQuestionRepo(db=db)
    try:
        doc = repo.create(
            owner_id=current_user["_id"],
            type=body.type,
            title=body.title,
            options=body.options,
            required=body.required,
            validation=body.validation,
            visibility=body.visibility,
            tags=body.tags,
            in_bank=body.in_bank,
            note=body.note,
        )
    except BankError as exc:
        raise _handle_bank_error(exc)
    return _bank_out(repo, doc, current_user, db)


@router.get("/questions", response_model=list[BankQuestionOut])
def list_bank_questions(
    current_user: CurrentUser,
    db: DbDep = None,
    keyword: str = "",
    tag: str = "",
    only_bank: bool = False,
    scope: str = "all",
) -> list[BankQuestionOut]:
    """列出可见的题目：自己的 + 共享给我的 + 公开的（需求一/二/七）。"""
    repo = BankQuestionRepo(db=db)
    docs = repo.list_visible(
        current_user["_id"],
        keyword=keyword,
        tag=tag,
        only_bank=only_bank,
        scope=scope,
    )
    return [_bank_out(repo, d, current_user, db) for d in docs]


@router.get("/questions/{version_id}", response_model=BankQuestionOut)
def get_bank_question(version_id: str, current_user: CurrentUser, db: DbDep = None) -> BankQuestionOut:
    """查看某个题目版本的详情。"""
    repo = BankQuestionRepo(db=db)
    doc = repo.get(_oid(version_id, "version_id"))
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    if not BankQuestionRepo.can_read(doc, current_user["_id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该题目")
    return _bank_out(repo, doc, current_user, db)


@router.put("/questions/{version_id}", response_model=BankQuestionOut)
def update_bank_question(
    version_id: str,
    body: BankQuestionUpdate,
    current_user: CurrentUser,
    db: DbDep = None,
) -> BankQuestionOut:
    """修改题目 → 生成新版本，旧版本与旧问卷保持不变（需求三/四/五）。"""
    repo = BankQuestionRepo(db=db)
    vid = _oid(version_id, "version_id")
    try:
        new_doc = repo.update(
            vid,
            owner_id=current_user["_id"],
            title=body.title,
            options=body.options,
            required=body.required,
            validation=body.validation,
            note=body.note,
            tags=body.tags,
            visibility=body.visibility,
        )
    except BankError as exc:
        raise _handle_bank_error(exc)
    return _bank_out(repo, new_doc, current_user, db)


@router.delete("/questions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_question(
    version_id: str, current_user: CurrentUser, db: DbDep = None
):
    """删除题目版本（已被问卷使用的版本不可删除）。"""
    repo = BankQuestionRepo(db=db)
    try:
        repo.delete(_oid(version_id, "version_id"), owner_id=current_user["_id"])
    except BankError as exc:
        raise _handle_bank_error(exc)


# ── 版本历史 ──────────────────────────────────────────────────────────────────


@router.get("/questions/{version_id}/versions", response_model=BankHistoryOut)
def list_versions(version_id: str, current_user: CurrentUser, db: DbDep = None) -> BankHistoryOut:
    """查看题目的历史版本（需求四：v1 → v2 → v3 的关系）。"""
    repo = BankQuestionRepo(db=db)
    doc = repo.get(_oid(version_id, "version_id"))
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    if not BankQuestionRepo.can_read(doc, current_user["_id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该题目")

    history = repo.history(doc["root_id"])
    by_id = {h["_id"]: h for h in history}
    latest = repo.latest(doc["root_id"])

    items = []
    for h in history:
        parent = by_id.get(h.get("parent_id"))
        items.append(
            BankHistoryItem(
                id=str(h["_id"]),
                version=h["version"],
                title=h["title"],
                type=h["type"],
                options=h.get("options"),
                required=bool(h.get("required", False)),
                note=h.get("note", ""),
                parent_id=str(h["parent_id"]) if h.get("parent_id") else None,
                parent_version=(parent or {}).get("version"),
                parent_title=(parent or {}).get("title"),
                created_at=h["created_at"],
                usage_count=repo.usage_count(h["_id"]),
                is_latest=bool(latest and latest["_id"] == h["_id"]),
                is_current=h["_id"] == doc["_id"],
            )
        )
    return BankHistoryOut(
        root_id=str(doc["root_id"]),
        current_id=str(doc["_id"]),
        versions=items,
    )


@router.post("/questions/{version_id}/versions", response_model=BankQuestionOut, status_code=201)
def create_version(
    version_id: str,
    body: BankVersionCreate,
    current_user: CurrentUser,
    db: DbDep = None,
) -> BankQuestionOut:
    """基于某个版本创建新版本（需求五）。"""
    repo = BankQuestionRepo(db=db)
    try:
        doc = repo.create_version(
            _oid(version_id, "version_id"),
            owner_id=current_user["_id"],
            title=body.title,
            options=body.options,
            required=body.required,
            validation=body.validation,
            note=body.note,
        )
    except BankError as exc:
        raise _handle_bank_error(exc)
    return _bank_out(repo, doc, current_user, db)


@router.post(
    "/questions/{version_id}/versions/{target_id}/restore",
    response_model=BankQuestionOut,
    status_code=201,
)
def restore_version(
    version_id: str,
    target_id: str,
    current_user: CurrentUser,
    db: DbDep = None,
) -> BankQuestionOut:
    """恢复旧版本：以旧版本内容生成一个新版本（需求四）。"""
    repo = BankQuestionRepo(db=db)
    try:
        doc = repo.restore(
            _oid(version_id, "version_id"),
            _oid(target_id, "target_id"),
            owner_id=current_user["_id"],
        )
    except BankError as exc:
        raise _handle_bank_error(exc)
    return _bank_out(repo, doc, current_user, db)


# ── 共享 / 题库 ───────────────────────────────────────────────────────────────


@router.post("/questions/{version_id}/share", response_model=BankQuestionOut)
def share_question(
    version_id: str,
    body: BankShare,
    current_user: CurrentUser,
    db: DbDep = None,
) -> BankQuestionOut:
    """把题目共享给其他用户 / 设为公开（需求二）。"""
    repo = BankQuestionRepo(db=db)
    try:
        doc = repo.share(
            _oid(version_id, "version_id"),
            owner_id=current_user["_id"],
            usernames=body.usernames,
            visibility=body.visibility,
            add_usernames=body.add_usernames,
            remove_usernames=body.remove_usernames,
        )
    except BankError as exc:
        raise _handle_bank_error(exc)
    return _bank_out(repo, doc, current_user, db)


@router.post("/questions/{version_id}/fork", response_model=BankQuestionOut, status_code=201)
def fork_question(
    version_id: str, current_user: CurrentUser, db: DbDep = None
) -> BankQuestionOut:
    """把共享给我的题目复制到我的题目库（自己成为拥有者）。"""
    repo = BankQuestionRepo(db=db)
    vid = _oid(version_id, "version_id")
    doc = repo.get(vid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    if not BankQuestionRepo.can_read(doc, current_user["_id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权使用该题目")
    try:
        new_doc = repo.fork(vid, user_id=current_user["_id"])
    except BankError as exc:
        raise _handle_bank_error(exc)
    return _bank_out(repo, new_doc, current_user, db)


class BankToggle(BaseModel):
    in_bank: bool


@router.post("/questions/{version_id}/bank", response_model=BankQuestionOut)
def toggle_bank(
    version_id: str,
    body: BankToggle,
    current_user: CurrentUser,
    db: DbDep = None,
) -> BankQuestionOut:
    """加入 / 移出题库（需求七）。"""
    repo = BankQuestionRepo(db=db)
    try:
        doc = repo.set_in_bank(
            _oid(version_id, "version_id"),
            owner_id=current_user["_id"],
            in_bank=body.in_bank,
        )
    except BankError as exc:
        raise _handle_bank_error(exc)
    return _bank_out(repo, doc, current_user, db)


# ── 使用情况 / 统计 ───────────────────────────────────────────────────────────


@router.get("/questions/{version_id}/usage", response_model=BankUsageOut)
def question_usage(
    version_id: str, current_user: CurrentUser, db: DbDep = None
) -> BankUsageOut:
    """查看该题目被哪些问卷使用（需求六）。"""
    repo = BankQuestionRepo(db=db)
    vid = _oid(version_id, "version_id")
    doc = repo.get(vid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    if not BankQuestionRepo.can_read(doc, current_user["_id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该题目")

    items = [
        BankUsageItem(
            question_id=str(r["question_id"]),
            survey_id=str(r["survey_id"]),
            survey_title=r["survey_title"],
            survey_status=r["survey_status"],
            order=r.get("order"),
            title=r.get("title"),
            version_id=str(r["version_id"]) if r.get("version_id") else None,
            version=r.get("version"),
            is_current_version=bool(r.get("is_current_version")),
        )
        for r in repo.usage(vid)
    ]
    return BankUsageOut(
        root_id=str(doc["root_id"]),
        version_id=str(vid),
        total=len(items),
        items=items,
    )


@router.get("/questions/{version_id}/statistics", response_model=BankStatsOut)
def question_statistics(
    version_id: str, current_user: CurrentUser, db: DbDep = None
) -> BankStatsOut:
    """跨问卷统计：该题在所有问卷中的回答分布（需求八）。"""
    repo = BankQuestionRepo(db=db)
    vid = _oid(version_id, "version_id")
    doc = repo.get(vid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    if not BankQuestionRepo.can_read(doc, current_user["_id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该题目")

    stats = StatisticsService(db=db).bank_statistics(doc["root_id"])
    return BankStatsOut(
        root_id=str(doc["root_id"]),
        title=stats.get("title"),
        type=stats.get("type"),
        question_count=stats["question_count"],
        survey_count=stats["survey_count"],
        total_answers=stats["total_answers"],
        counts=[ChoiceCountItem(value=c["value"], count=c["count"]) for c in stats["counts"]],
        avg=stats.get("avg"),
        min=stats.get("min"),
        max=stats.get("max"),
        n=stats.get("n", 0),
        values=stats.get("values", []),
        by_survey=[
            BankSurveyCount(survey_id=str(s["survey_id"]), title=s["title"], count=s["count"])
            for s in stats["by_survey"]
        ],
        by_version=[
            BankVersionCount(
                version_id=str(v["version_id"]),
                version=v.get("version"),
                title=v.get("title"),
                count=v["count"],
            )
            for v in stats["by_version"]
        ],
    )
