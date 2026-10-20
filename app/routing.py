"""`next_rule` interpreter (docs/数据库设计.md §6).

The engine is purely functional: given the question's ``next_rule``
document and the submitted value, return either:

* the integer ``order`` of the next question, or
* the string ``"end"`` to terminate the survey.

Decisions are persisted in `responses.answer_path`, which lets auditing
and replay work without re-running the engine.
"""
from __future__ import annotations

from typing import Any, Iterable


class RoutingError(ValueError):
    """Raised when the next_rule document is structurally invalid."""


_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def resolve_fallback(fallback: Any) -> Any:
    """Resolve ``fallback`` (str ``"next"`` / ``"end"`` or int ``order``)."""
    if fallback == "next":
        return "next"
    if fallback == "end":
        return "end"
    if isinstance(fallback, int):
        return fallback
    raise RoutingError(f"fallback must be 'next', 'end' or int, got {fallback!r}")


def resolve(rule: dict, value: Any) -> Any:
    """Resolve a ``next_rule`` document against a submitted ``value``.

    Returns one of:

    * an ``int`` order number, or
    * the string ``"next"`` (caller advances by 1), or
    * the string ``"end"`` to terminate.
    """
    if not isinstance(rule, dict):
        raise RoutingError("next_rule must be a document")
    mode = rule.get("mode", "default")
    fallback = resolve_fallback(rule.get("fallback", "next"))

    if mode == "default":
        return fallback

    if mode == "by_option":
        # single-choice branch: value is the selected option text
        for branch in rule.get("branches", []):
            if branch.get("when") == value:
                return branch.get("goto", fallback)
        return fallback

    if mode == "by_contains":
        # multi-choice branches; value is a list of selected option texts
        if not isinstance(value, (list, tuple, set)):
            return fallback
        selected = set(value)
        for branch in rule.get("branches", []):
            when_any = branch.get("when_any")
            when_all = branch.get("when_all")
            matched = False
            if when_any is not None:
                matched = matched or bool(selected & set(when_any))
            if when_all is not None:
                wanted = set(when_all)
                matched = matched or (wanted and wanted.issubset(selected))
            if matched:
                return branch.get("goto", fallback)
        return fallback

    if mode == "by_range":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return fallback
        for branch in rule.get("branches", []):
            cond = branch.get("when") or {}
            op = cond.get("op")
            threshold = cond.get("value")
            if op not in _OPS:
                continue
            try:
                if _OPS[op](value, threshold):
                    return branch.get("goto", fallback)
            except TypeError:
                continue
        return fallback

    raise RoutingError(f"unknown next_rule.mode: {mode!r}")


def reachable_orders(orders: Iterable[int], rule: dict, value: Any) -> set[int]:
    """Helper used by the QuestionRepo to verify ``goto`` references.

    Returns the set of order numbers that *could* be reached from ``rule``
    given the supplied value. ``orders`` is the full set of existing
    order numbers in the survey; any ``goto`` outside this set is invalid.
    """
    target = resolve(rule, value)
    if target in ("next", "end"):
        return set()
    if isinstance(target, int):
        return {target}
    return set()


def collect_goto_targets(rule: Any) -> set[int]:
    """Return every integer ``goto`` reference inside a ``next_rule``.

    Used at write-time to ensure no ``goto`` points outside the survey.
    Branches that conditionally fire are still considered: every possible
    target must exist at save time.
    """
    targets: set[int] = set()
    if not isinstance(rule, dict):
        return targets
    if isinstance(rule.get("fallback"), int):
        targets.add(rule["fallback"])
    for branch in rule.get("branches", []) or []:
        target = branch.get("goto")
        if isinstance(target, int):
            targets.add(target)
    return targets
