"""Pydantic schemas for request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── auth ─────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=200)


class UserOut(BaseModel):
    id: str
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── surveys ───────────────────────────────────────────────────────────────────


class SurveyCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    allow_anonymous: bool = False


class SurveyUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    allow_anonymous: Optional[bool] = None
    deadline: Optional[datetime] = None


class SurveyOut(BaseModel):
    id: str
    title: str
    description: str
    allow_anonymous: bool
    owner_id: str
    status: str
    token: Optional[str]
    deadline: Optional[datetime]
    created_at: datetime
    published_at: Optional[datetime]


class SurveyListOut(BaseModel):
    items: list[SurveyOut]
    total: int


# ── questions ─────────────────────────────────────────────────────────────────


class QuestionCreate(BaseModel):
    type: str = Field(..., pattern="^(single|multi|text|number)$")
    title: str = Field(..., min_length=1)
    options: Optional[list[str]] = None
    required: bool = False
    validation: dict[str, Any] = Field(default_factory=dict)
    next_rule: dict[str, Any] = Field(
        default_factory=lambda: {"mode": "default", "fallback": "next"}
    )


class QuestionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    options: Optional[list[str]] = None
    required: Optional[bool] = None
    validation: Optional[dict[str, Any]] = None
    next_rule: Optional[dict[str, Any]] = None


class QuestionOut(BaseModel):
    id: str
    survey_id: str
    order: int
    type: str
    title: str
    required: bool
    options: Optional[list[str]]
    validation: dict[str, Any]
    next_rule: dict[str, Any]
    created_at: datetime


# ── responses (submissions) ───────────────────────────────────────────────────


class AnswerSubmit(BaseModel):
    question_order: int
    value: Any


class AnswerOut(BaseModel):
    question_order: int
    value: Any


class SubmissionStartOut(BaseModel):
    submission_id: str
    next_order: int


class SubmissionStepOut(BaseModel):
    submission_id: str
    answer_id: str
    next_order: Optional[int] = None
    is_end: bool = False


class SubmissionFinalOut(BaseModel):
    submission_id: str
    submitted_at: datetime


# ── statistics ───────────────────────────────────────────────────────────────


class ChoiceCountItem(BaseModel):
    value: str
    count: int


class SingleChoiceStats(BaseModel):
    question_id: str
    order: int
    title: str
    counts: list[ChoiceCountItem]
    total: int


class MultiChoiceStats(BaseModel):
    question_id: str
    order: int
    title: str
    counts: list[ChoiceCountItem]


class NumberStats(BaseModel):
    question_id: str
    order: int
    title: str
    avg: Optional[float]
    n: int
    min: Optional[float]
    max: Optional[float]


class TextStats(BaseModel):
    question_id: str
    order: int
    title: str
    values: list[str]


class RespondentItem(BaseModel):
    """One submitted response, optionally attributed to a user."""
    submission_id: str
    username: Optional[str] = None  # None if the survey is anonymous
    submitted_at: datetime


class SurveyStatsOut(BaseModel):
    total_submissions: int
    is_anonymous: bool
    respondents: list[RespondentItem]
    single_choice: list[SingleChoiceStats]
    multi_choice: list[MultiChoiceStats]
    number_stats: list[NumberStats]
    text_answers: list[TextStats]
