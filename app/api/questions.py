"""Question CRUD endpoints (nested under /api/surveys/{survey_id}/questions)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from bson import ObjectId

from ..models import BankQuestionRepo, SurveyRepo, QuestionRepo
from ..models.bank import BankError
from ..models.questions import QuestionValidationError
from .deps import CurrentUser, DbDep
from .schemas import QuestionCreate, QuestionOut, QuestionUpdate

router = APIRouter()


def _q_out(doc: dict) -> QuestionOut:
    ref = doc.get("bank_ref")
    if ref:
        ref = {
            "root_id": str(ref["root_id"]),
            "version_id": str(ref["version_id"]),
            "version": ref.get("version"),
            "title_snapshot": ref.get("title_snapshot"),
        }
    return QuestionOut(
        id=str(doc["_id"]),
        survey_id=str(doc["survey_id"]),
        order=doc["order"],
        type=doc["type"],
        title=doc["title"],
        required=doc.get("required", False),
        options=doc.get("options"),
        validation=doc.get("validation", {}),
        next_rule=doc.get("next_rule", {"mode": "default", "fallback": "next"}),
        bank_ref=ref,
        created_at=doc["created_at"],
    )


def _bank_ref(doc: dict) -> dict:
    """构造题库引用信息（记录来源版本，便于反查与跨问卷统计）。

    ``root_id`` / ``version_id`` 以 ObjectId 存储，便于按家族 / 版本反查。
    """
    return {
        "root_id": doc["root_id"],
        "version_id": doc["_id"],
        "version": doc["version"],
        "title_snapshot": doc["title"],
    }


@router.post("/{survey_id}/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def add_question(
    survey_id: str,
    body: QuestionCreate,
    current_user: CurrentUser,
    db: DbDep = None,
) -> QuestionOut:
    """Add a question to a draft survey (owner only)."""
    try:
        sid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if survey["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")
    if survey["status"] != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="questions can only be added to draft surveys",
        )

    repo = QuestionRepo(db=db)
    bank_ref = None
    qtype, qtitle, qoptions = body.type, body.title, body.options
    qrequired, qvalidation = body.required, body.validation

    if body.bank_question_id:
        # 从题库选题：以题库版本内容为准做一份快照（需求一/二/三）
        try:
            bid = ObjectId(body.bank_question_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid bank_question_id")
        bank_repo = BankQuestionRepo(db=db)
        bdoc = bank_repo.get(bid)
        if bdoc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题库题目不存在")
        if not BankQuestionRepo.can_read(bdoc, current_user["_id"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权使用该题库题目")
        qtype = bdoc["type"]
        qtitle = bdoc["title"]
        qoptions = bdoc.get("options")
        qrequired = bool(bdoc.get("required", False))
        qvalidation = bdoc.get("validation", {}) or {}
        bank_ref = _bank_ref(bdoc)

    if not qtype or not qtitle:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="type 与 title 必填，或者提供 bank_question_id 从题库选题",
        )

    try:
        qid = repo.add(
            sid,
            type=qtype,
            title=qtitle,
            options=qoptions,
            required=qrequired,
            validation=qvalidation,
            next_rule=body.next_rule,
            bank_ref=bank_ref,
        )
    except QuestionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # retrieve and return the newly created question
    all_q = repo.list_by_survey(sid)
    q = repo.find_by_order(sid, all_q[-1]["order"])
    return _q_out(q)


@router.get("/{survey_id}/questions", response_model=list[QuestionOut])
def list_questions(survey_id: str, db: DbDep = None) -> list[QuestionOut]:
    """List all questions in a survey, ordered by ``order``."""
    try:
        sid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")

    repo = QuestionRepo(db=db)
    return [_q_out(q) for q in repo.list_by_survey(sid)]


@router.delete("/{survey_id}/questions/{order}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    survey_id: str,
    order: int,
    current_user: CurrentUser,
    db: DbDep = None,
):
    """Delete a question by its order number (draft surveys only)."""
    try:
        sid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if survey["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")
    if survey["status"] != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="questions can only be deleted from draft surveys",
        )

    deleted = QuestionRepo(db=db).delete_by_order(sid, order)
    if deleted == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")


@router.put("/{survey_id}/questions/{order}", response_model=QuestionOut)
def update_question(
    survey_id: str,
    order: int,
    body: QuestionUpdate,
    current_user: CurrentUser,
    db: DbDep = None,
) -> QuestionOut:
    """Update a question's title, options, required, validation, or next_rule."""
    try:
        sid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if survey["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")
    if survey["status"] != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="questions can only be updated in draft surveys",
        )

    repo = QuestionRepo(db=db)
    bank_ref = None
    new_title, new_options = body.title, body.options
    new_required, new_validation = body.required, body.validation
    if body.bank_version_id:
        # 把问卷里的题目切换到题库的另一个版本（需求五）
        try:
            bid = ObjectId(body.bank_version_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid bank_version_id")
        bdoc = BankQuestionRepo(db=db).get(bid)
        if bdoc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题库题目不存在")
        if not BankQuestionRepo.can_read(bdoc, current_user["_id"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权使用该题库题目")
        existing = repo.find_by_order(sid, order)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")
        if existing.get("type") != bdoc["type"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="题型不一致，无法切换到该版本",
            )
        bank_ref = _bank_ref(bdoc)
        # 快照内容跟随新版本（调用方显式传入的字段优先）
        if new_title is None:
            new_title = bdoc["title"]
        if new_options is None and bdoc.get("options"):
            new_options = bdoc.get("options")
        if new_required is None:
            new_required = bool(bdoc.get("required", False))
        if new_validation is None:
            new_validation = bdoc.get("validation", {}) or {}

    try:
        updated = repo.update_question(
            sid,
            order,
            title=new_title,
            options=new_options,
            required=new_required,
            validation=new_validation,
            next_rule=body.next_rule,
            bank_ref=bank_ref,
        )
    except QuestionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    return _q_out(updated)
