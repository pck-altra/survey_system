"""Repository classes for each MongoDB collection.

Each submodule maps a business entity to its CRUD + domain operations.
Callers (web layer, scripts, tests) should go through these instead of
touching the collections directly so that invariants live in one place.
"""

from .users import UserRepo  # noqa: F401
from .surveys import SurveyRepo, SurveyStateError  # noqa: F401
from .questions import QuestionRepo, QuestionValidationError  # noqa: F401
from .responses import ResponseRepo, SubmissionError  # noqa: F401
from .answers import AnswerRepo, StatisticsService  # noqa: F401
