"""Question CRUD endpoints (nested under /api/surveys/{survey_id}/questions)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from bson import ObjectId

from ..models import SurveyRepo, QuestionRepo
from ..models.questions import QuestionValidationError
from .deps import CurrentUser, DbDep
from .schemas import QuestionCreate, QuestionOut, QuestionUpdate

router = APIRouter()


def _q_out(doc: dict) -> QuestionOut:
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
        created_at=doc["created_at"],
    )


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
    try:
        qid = repo.add(
            sid,
            type=body.type,
            title=body.title,
            options=body.options,
            required=body.required,
            validation=body.validation,
            next_rule=body.next_rule,
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
    try:
        updated = repo.update_question(
            sid,
            order,
            title=body.title,
            options=body.options,
            required=body.required,
            validation=body.validation,
            next_rule=body.next_rule,
        )
    except QuestionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    return _q_out(updated)
