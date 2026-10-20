"""Survey submission (fill-out) endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from bson import ObjectId

from ..models import SurveyRepo, QuestionRepo, ResponseRepo
from ..models.responses import SubmissionError
from .deps import CurrentUser, DbDep
from .schemas import (
    AnswerSubmit,
    SubmissionStartOut,
    SubmissionStepOut,
    SubmissionFinalOut,
)

router = APIRouter()


@router.post("/{survey_id}/submit/start", response_model=SubmissionStartOut)
def start_submission(
    survey_id: str,
    current_user: CurrentUser,
    db: DbDep = None,
) -> SubmissionStartOut:
    """Begin filling out a survey.

    The respondent must be logged in. The submission is always attributed
    to ``current_user``; the survey's ``allow_anonymous`` flag only
    controls whether the respondent's username is exposed in the
    owner's statistics view.
    """
    try:
        sid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")

    if not SurveyRepo(db=db).is_open_for_submission(survey):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="survey is not accepting submissions")

    uid = ObjectId(current_user["_id"])

    try:
        rid = ResponseRepo(db=db).start(sid, user_id=uid)
    except SubmissionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # find first question
    questions = {q["order"]: q for q in QuestionRepo(db=db).list_by_survey(sid)}
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="survey has no questions",
        )
    first_order = sorted(questions.keys())[0]
    return SubmissionStartOut(submission_id=str(rid), next_order=first_order)


@router.post("/{survey_id}/submit/{submission_id}/answer", response_model=SubmissionStepOut)
def submit_answer(
    survey_id: str,
    submission_id: str,
    body: AnswerSubmit,
    db: DbDep = None,
) -> SubmissionStepOut:
    """Submit an answer for a question and get the next question's order."""
    try:
        sid = ObjectId(survey_id)
        rid = ObjectId(submission_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid ids")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if not SurveyRepo(db=db).is_open_for_submission(survey):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="survey is not accepting submissions")

    resp_doc = ResponseRepo(db=db).find_by_id(rid)
    if resp_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="submission not found")

    questions = {q["order"]: q for q in QuestionRepo(db=db).list_by_survey(sid)}
    if body.question_order not in questions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="question not found")

    q = questions[body.question_order]

    try:
        _, nxt = ResponseRepo(db=db).record_step(
            rid,
            order=body.question_order,
            value=body.value,
            next_rule=q.get("next_rule", {"mode": "default", "fallback": "next"}),
            questions_by_order=questions,
        )
    except SubmissionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if nxt == "end":
        return SubmissionStepOut(submission_id=str(rid), answer_id="", is_end=True)
    return SubmissionStepOut(
        submission_id=str(rid),
        answer_id="",
        next_order=nxt,
        is_end=False,
    )


@router.post("/{survey_id}/submit/{submission_id}/finalize", response_model=SubmissionFinalOut)
def finalize_submission(
    survey_id: str,
    submission_id: str,
    current_user: CurrentUser,
    db: DbDep = None,
) -> SubmissionFinalOut:
    """Finalize and submit a survey (stamp submitted_at).

    The caller must be the same user that started the submission.
    """
    try:
        sid = ObjectId(survey_id)
        rid = ObjectId(submission_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid ids")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")

    resp_doc = ResponseRepo(db=db).find_by_id(rid)
    if resp_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="submission not found")
    if resp_doc.get("user_id") != ObjectId(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="submission belongs to a different user",
        )
    if resp_doc.get("submitted_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="submission already finalized",
        )

    doc = ResponseRepo(db=db).finalize(rid)
    return SubmissionFinalOut(submission_id=str(rid), submitted_at=doc["submitted_at"])


@router.get("/{survey_id}/my-submissions", response_model=list[dict])
def my_submissions(
    survey_id: str,
    current_user: CurrentUser,
    db: DbDep = None,
) -> list[dict]:
    """List all submissions by the current user for a survey."""
    try:
        sid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    uid = ObjectId(current_user["_id"])
    results = ResponseRepo(db=db).list_by_survey(sid, submitted_only=True)
    return [
        {
            "submission_id": str(r["_id"]),
            "submitted_at": r["submitted_at"].isoformat() if r.get("submitted_at") else None,
            "answer_path": r.get("answer_path", []),
        }
        for r in results
        if r.get("user_id") == uid
    ]
