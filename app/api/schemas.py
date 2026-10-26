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
    # 从题库选题时（只给 bank_question_id），type / title 由题库版本决定，可以省略
    type: Optional[str] = Field(None, pattern="^(single|multi|text|number)$")
    title: Optional[str] = Field(None, min_length=1)
    options: Optional[list[str]] = None
    required: bool = False
    validation: dict[str, Any] = Field(default_factory=dict)
    next_rule: dict[str, Any] = Field(
        default_factory=lambda: {"mode": "default", "fallback": "next"}
    )
    # 从题库选题（需求一/二）：给出题库版本 ID 时使用该版本的内容做快照
    bank_question_id: Optional[str] = None


class QuestionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    options: Optional[list[str]] = None
    required: Optional[bool] = None
    validation: Optional[dict[str, Any]] = None
    next_rule: Optional[dict[str, Any]] = None
    # 切换到题库的另一个版本（需求五：不同问卷可用不同版本）
    bank_version_id: Optional[str] = None


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
    bank_ref: Optional[dict[str, Any]] = None
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


# ── 题库 / 可复用题目（需求变更）────────────────────────────────────────────


class BankQuestionCreate(BaseModel):
    """保存一个常用题目（需求一）。"""

    type: str = Field(..., pattern="^(single|multi|text|number)$")
    title: str = Field(..., min_length=1)
    options: Optional[list[str]] = None
    required: bool = False
    validation: dict[str, Any] = Field(default_factory=dict)
    visibility: str = Field("private", pattern="^(private|public)$")
    tags: list[str] = Field(default_factory=list)
    in_bank: bool = True
    note: str = ""


class BankQuestionUpdate(BaseModel):
    """修改题目 → 后端会生成一个新版本，旧版本保留（需求三/四/五）。"""

    title: Optional[str] = Field(None, min_length=1)
    options: Optional[list[str]] = None
    required: Optional[bool] = None
    validation: Optional[dict[str, Any]] = None
    visibility: Optional[str] = Field(None, pattern="^(private|public)$")
    tags: Optional[list[str]] = None
    note: str = ""


class BankVersionCreate(BaseModel):
    """基于已有版本创建新版本（需求五）。"""

    title: Optional[str] = Field(None, min_length=1)
    options: Optional[list[str]] = None
    required: Optional[bool] = None
    validation: Optional[dict[str, Any]] = None
    note: str = ""


class BankShare(BaseModel):
    """共享题目给其他用户（需求二）。"""

    usernames: Optional[list[str]] = None
    visibility: Optional[str] = Field(None, pattern="^(private|public)$")
    add_usernames: Optional[list[str]] = None
    remove_usernames: Optional[list[str]] = None


class BankQuestionOut(BaseModel):
    id: str
    root_id: str
    version: int
    parent_id: Optional[str]
    title: str
    type: str
    options: Optional[list[str]]
    required: bool
    validation: dict[str, Any]
    owner_id: str
    owner_username: Optional[str] = None
    visibility: str
    shared_with: list[str]
    tags: list[str]
    in_bank: bool
    note: str
    created_at: datetime
    updated_at: datetime
    usage_count: int = 0
    can_edit: bool = False
    is_latest: bool = True
    derived_from_title: Optional[str] = None


class BankHistoryItem(BaseModel):
    id: str
    version: int
    title: str
    type: str
    options: Optional[list[str]]
    required: bool
    note: str
    parent_id: Optional[str]
    parent_version: Optional[int] = None
    parent_title: Optional[str] = None
    created_at: datetime
    usage_count: int = 0
    is_latest: bool = False
    is_current: bool = False


class BankHistoryOut(BaseModel):
    root_id: str
    current_id: str
    versions: list[BankHistoryItem]


class BankUsageItem(BaseModel):
    question_id: str
    survey_id: str
    survey_title: str
    survey_status: str
    order: Optional[int]
    title: Optional[str]
    version_id: Optional[str]
    version: Optional[int]
    is_current_version: bool = False


class BankUsageOut(BaseModel):
    root_id: str
    version_id: str
    total: int
    items: list[BankUsageItem]


class BankSurveyCount(BaseModel):
    survey_id: str
    title: str
    count: int


class BankVersionCount(BaseModel):
    version_id: str
    version: Optional[int]
    title: Optional[str]
    count: int


class BankStatsOut(BaseModel):
    """跨问卷统计（需求八）。"""

    root_id: str
    title: Optional[str] = None
    type: Optional[str] = None
    question_count: int
    survey_count: int
    total_answers: int
    counts: list[ChoiceCountItem] = Field(default_factory=list)
    avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    n: int = 0
    values: list[str] = Field(default_factory=list)
    by_survey: list[BankSurveyCount] = Field(default_factory=list)
    by_version: list[BankVersionCount] = Field(default_factory=list)
