"""Survey statistics endpoints (owner only)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from bson import ObjectId

from ..models import SurveyRepo, AnswerRepo
from ..models.answers import StatisticsService
from .deps import CurrentUser, DbDep
from .schemas import (
    SurveyStatsOut,
    SingleChoiceStats,
    MultiChoiceStats,
    NumberStats,
    TextStats,
    ChoiceCountItem,
    RespondentItem,
)

router = APIRouter()


@router.get("/{survey_id}/statistics", response_model=SurveyStatsOut)
def get_statistics(
    survey_id: str,
    current_user: CurrentUser,
    db: DbDep = None,
) -> SurveyStatsOut:
    """Get aggregated statistics for a survey (owner only)."""
    try:
        sid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    survey = SurveyRepo(db=db).get(sid)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if survey["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner access required")

    stats = StatisticsService(db=db)
    is_anonymous = bool(survey.get("allow_anonymous", False))

    single_raw = stats.single_choice_counts(sid)
    single_choice = [
        SingleChoiceStats(
            question_id=str(r["question_id"]),
            order=r["order"],
            title=r["title"],
            counts=[ChoiceCountItem(value=c["value"], count=c["count"]) for c in r["counts"]],
            total=r["total"],
        )
        for r in single_raw
    ]

    multi_raw = stats.multi_choice_counts(sid)
    multi_choice = [
        MultiChoiceStats(
            question_id=str(r["question_id"]),
            order=r["order"],
            title=r["title"],
            counts=[ChoiceCountItem(value=c["value"], count=c["count"]) for c in r["counts"]],
        )
        for r in multi_raw
    ]

    num_raw = stats.number_stats(sid)
    number_stats = [
        NumberStats(
            question_id=str(r["question_id"]),
            order=r["order"],
            title=r["title"],
            avg=r["avg"],
            n=r["n"],
            min=r["min"],
            max=r["max"],
        )
        for r in num_raw
    ]

    text_raw = stats.text_answers(sid)
    text_answers = [
        TextStats(
            question_id=str(r["question_id"]),
            order=r["order"],
            title=r["title"],
            values=r["values"],
        )
        for r in text_raw
    ]

    # Respondent list — only expose usernames when the survey is NOT anonymous.
    respondents_raw = stats.respondents(sid, include_usernames=not is_anonymous)
    respondents = [
        RespondentItem(
            submission_id=str(r["submission_id"]),
            username=r["username"],
            submitted_at=r["submitted_at"],
        )
        for r in respondents_raw
    ]

    return SurveyStatsOut(
        total_submissions=stats.total_submissions(sid),
        is_anonymous=is_anonymous,
        respondents=respondents,
        single_choice=single_choice,
        multi_choice=multi_choice,
        number_stats=number_stats,
        text_answers=text_answers,
    )
