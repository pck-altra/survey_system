"""`validation` interpreter (docs/数据库设计.md §5).

The engine validates a single submitted ``value`` against a question's
``validation`` document. It is purely functional and raises
:class:`ValidationError` carrying a human-readable message when the value
fails any rule.

The rule shape varies by ``type`` — see the design doc for the four
per-type snippets. Missing fields fall back to the per-type defaults
(``required = False`` by default).
"""
from __future__ import annotations

import math
from typing import Any


class ValidationError(ValueError):
    """Raised when a submitted value fails a question's validation rules."""


SUPPORTED_TYPES = ("single", "multi", "text", "number")
SUPPORTED_OPS = (">=", "<=", ">", "<", "==", "!=")


# ---------------------------------------------------------------------------
# per-type validators
# ---------------------------------------------------------------------------


def _validate_single(value: Any, validation: dict) -> None:
    required = bool(validation.get("required", False))
    options: list = validation.get("options") or []

    if value is None or (isinstance(value, str) and value.strip() == ""):
        if required:
            raise ValidationError("single choice is required")
        return

    if not isinstance(value, str):
        raise ValidationError("single value must be a string")

    if options and value not in options:
        raise ValidationError(
            f"value {value!r} is not one of the declared options"
        )


def _validate_multi(value: Any, validation: dict) -> None:
    options: list = validation.get("options") or []
    min_count = validation.get("min_count")
    max_count = validation.get("max_count")
    exact_count = validation.get("exact_count")
    required = bool(validation.get("required", False))

    if value is None:
        if required:
            raise ValidationError("multi choice is required")
        value = []

    if not isinstance(value, list):
        raise ValidationError("multi value must be a list")

    if options:
        unknown = [v for v in value if v not in options]
        if unknown:
            raise ValidationError(f"unknown multi options: {unknown!r}")

    n = len(value)

    if required and n == 0:
        raise ValidationError("multi choice is required")

    if exact_count is not None:
        if n != exact_count:
            raise ValidationError(
                f"multi choice must contain exactly {exact_count} option(s); got {n}"
            )
    else:
        if min_count is not None and n < min_count:
            raise ValidationError(
                f"multi choice needs at least {min_count} option(s); got {n}"
            )
        if max_count is not None and n > max_count:
            raise ValidationError(
                f"multi choice allows at most {max_count} option(s); got {n}"
            )


def _validate_text(value: Any, validation: dict) -> None:
    required = bool(validation.get("required", False))
    min_len = validation.get("min_len")
    max_len = validation.get("max_len")

    if value is None:
        if required:
            raise ValidationError("text answer is required")
        return

    if not isinstance(value, str):
        raise ValidationError("text value must be a string")

    n = len(value)
    if min_len is not None and n < min_len:
        raise ValidationError(
            f"text must be at least {min_len} character(s); got {n}"
        )
    if max_len is not None and n > max_len:
        raise ValidationError(
            f"text must be at most {max_len} character(s); got {n}"
        )


def _validate_number(value: Any, validation: dict) -> None:
    required = bool(validation.get("required", False))
    min_v = validation.get("min")
    max_v = validation.get("max")
    integer_only = bool(validation.get("integer_only", False))

    if value is None or (isinstance(value, str) and value.strip() == ""):
        if required:
            raise ValidationError("number answer is required")
        return

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("number value must be numeric")
    if isinstance(value, float) and math.isnan(value):
        raise ValidationError("number value is NaN")

    if integer_only and isinstance(value, float) and not value.is_integer():
        raise ValidationError("number value must be an integer")
    if integer_only and isinstance(value, float):
        # canonicalise e.g. 5.0 → 5 for storage
        value = int(value)
    if isinstance(value, bool):
        raise ValidationError("number value must be numeric")

    if min_v is not None and value < min_v:
        raise ValidationError(f"number must be ≥ {min_v}; got {value}")
    if max_v is not None and value > max_v:
        raise ValidationError(f"number must be ≤ {max_v}; got {value}")


_VALIDATORS = {
    "single": _validate_single,
    "multi": _validate_multi,
    "text": _validate_text,
    "number": _validate_number,
}


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------


def validate_answer(
    question_type: str,
    value: Any,
    validation: dict | None = None,
    options: list | None = None,
) -> Any:
    """Validate ``value`` against the question's rules.

    ``options`` is merged into the validation document for ``single``/
    ``multi`` so that callers can pass the option list from the question
    document instead of duplicating it inside ``validation``.

    Returns the (possibly coerced) value on success. Raises
    :class:`ValidationError` on failure.
    """
    if question_type not in SUPPORTED_TYPES:
        raise ValidationError(f"unsupported question type: {question_type!r}")

    v = dict(validation or {})
    if options is not None and question_type in ("single", "multi"):
        v.setdefault("options", list(options))

    _VALIDATORS[question_type](value, v)
    return value
