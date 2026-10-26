"""`questions` collection repository.

Implements docs/数据库设计.md §4.3, §5, §6.

* ``order`` is unique within a survey and starts at 1.
* ``options`` is mandatory for ``single``/``multi``.
* Save-time checks reject ``goto`` targets outside the survey and reject
  ``next_rule`` documents that form cycles through other questions.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Optional

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from ..db import get_db
from ..routing import collect_goto_targets, RoutingError
from ..validation import SUPPORTED_TYPES, validate_answer, ValidationError

# sentinel "goto" meaning "skip to next order" — stored as integer order
# ``+ 1`` at write time so the document remains self-describing.


class QuestionValidationError(ValueError):
    """Question-level validation error (schema or goto consistency)."""


class QuestionRepo:
    """Data-access object for the ``questions`` collection."""

    def __init__(self, db=None):
        self._db = db if db is not None else get_db()
        self._coll: Collection = self._db["questions"]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, survey_id: ObjectId, *, type: str, title: str, **fields) -> ObjectId:
        """Insert a question into ``survey_id``.

        ``type`` is one of ``"single"``, ``"multi"``, ``"text"``, ``"number"``.
        Optional ``fields``:

        * ``options``     : list[str] (required for single/multi)
        * ``required``    : bool
        * ``validation``  : dict — per-type rule document
        * ``next_rule``   : dict — branching document
        * ``bank_ref``    : dict — 参考题库题目的快照信息（需求一/二/三）
        """
        if type not in SUPPORTED_TYPES:
            raise QuestionValidationError(
                f"unsupported question type: {type!r}; expected one of {SUPPORTED_TYPES}"
            )
        if not isinstance(title, str) or not title.strip():
            raise QuestionValidationError("title is required")

        options = fields.get("options")
        required = bool(fields.get("required", False))
        validation = fields.get("validation") or {}
        next_rule = fields.get("next_rule") or {"mode": "default", "fallback": "next"}
        bank_ref = fields.get("bank_ref")

        # ---- inline structural checks ----
        if type in ("single", "multi"):
            if not options or not isinstance(options, list) or not all(
                isinstance(o, str) for o in options
            ):
                raise QuestionValidationError(
                    f"{type} question requires a non-empty list of string options"
                )
        else:
            if options:
                # text/number shouldn't carry options — ignore silently
                options = None

        # ---- order assignment (1-based, gap-tolerant) ----
        existing = list(self._coll.find({"survey_id": survey_id}, projection={"order": 1}))
        next_order = max((q["order"] for q in existing), default=0) + 1

        # ---- goto consistency check ----
        self._ensure_goto_targets_exist(survey_id, type, options, next_rule, ignore_order=next_order)
        self._ensure_no_cycle(survey_id, next_order, next_rule)

        doc: dict[str, Any] = {
            "survey_id": survey_id,
            "order": next_order,
            "type": type,
            "title": title.strip(),
            "required": required,
            "options": options,
            "validation": validation,
            "next_rule": next_rule,
            "bank_ref": bank_ref,
            "created_at": dt.datetime.now(dt.timezone.utc),
        }
        try:
            return self._coll.insert_one(doc).inserted_id
        except DuplicateKeyError:
            # extremely unlikely given server-side $max logic; surface a clean error
            raise QuestionValidationError("order conflict; retry the insertion")

    def list_by_survey(self, survey_id: ObjectId) -> list[dict]:
        """Return all questions ordered ascending by ``order``."""
        cursor = self._coll.find({"survey_id": survey_id}).sort("order", 1)
        return list(cursor)

    def find_by_order(self, survey_id: ObjectId, order: int) -> Optional[dict]:
        return self._coll.find_one({"survey_id": survey_id, "order": order})

    def delete_by_order(self, survey_id: ObjectId, order: int) -> int:
        res = self._coll.delete_one({"survey_id": survey_id, "order": order})
        return res.deleted_count

    def update_question(
        self,
        survey_id: ObjectId,
        order: int,
        *,
        title: Optional[str] = None,
        options: Optional[list[str]] = None,
        required: Optional[bool] = None,
        validation: Optional[dict] = None,
        next_rule: Optional[dict] = None,
        bank_ref: Optional[dict] = None,
    ) -> Optional[dict]:
        """Update a question's fields by order, returning the updated document."""
        existing = self.find_by_order(survey_id, order)
        if not existing:
            return None

        # resolve defaults from existing doc
        qtype   = existing["type"]
        new_title = title if title is not None else existing["title"]
        new_opts  = options if options is not None else existing.get("options")
        new_req   = required if required is not None else existing.get("required", False)
        new_val   = validation if validation is not None else existing.get("validation", {})
        new_rule  = next_rule if next_rule is not None else existing.get("next_rule", {"mode": "default", "fallback": "next"})

        # validate title
        if not isinstance(new_title, str) or not new_title.strip():
            raise QuestionValidationError("title is required")

        # validate options for single/multi
        if qtype in ("single", "multi"):
            if not new_opts or not isinstance(new_opts, list) or not all(
                isinstance(o, str) for o in new_opts
            ):
                raise QuestionValidationError(
                    f"{qtype} question requires a non-empty list of string options"
                )
        else:
            new_opts = None

        # validate goto targets
        self._ensure_goto_targets_exist(survey_id, qtype, new_opts, new_rule, ignore_order=order)
        self._ensure_no_cycle(survey_id, order, new_rule)

        update: dict[str, Any] = {
            "$set": {
                "title": new_title.strip(),
                "required": bool(new_req),
                "options": new_opts,
                "validation": new_val,
                "next_rule": new_rule,
            }
        }
        if bank_ref is not None:
            update["$set"]["bank_ref"] = bank_ref
        result = self._coll.find_one_and_update(
            {"survey_id": survey_id, "order": order},
            update,
            return_document=True,
        )
        return result

    def count_by_survey(self, survey_id: ObjectId) -> int:
        return self._coll.count_documents({"survey_id": survey_id})

    # ------------------------------------------------------------------
    # invariants
    # ------------------------------------------------------------------

    def _existing_orders(self, survey_id: ObjectId, *, ignore_order: Optional[int] = None) -> set[int]:
        query: dict = {"survey_id": survey_id}
        if ignore_order is not None:
            query["order"] = {"$ne": ignore_order}
        return {q["order"] for q in self._coll.find(query, projection={"order": 1})}

    def _ensure_goto_targets_exist(
        self,
        survey_id: ObjectId,
        type: str,
        options: list | None,
        next_rule: dict,
        *,
        ignore_order: Optional[int] = None,
    ) -> None:
        """Validate that every explicit goto target is a valid order in the survey.

        Forward references (goto → a question not yet added) are allowed at
        insert time; the cycle-detection pass in ``_ensure_no_cycle`` will
        catch any cycles once all questions exist.
        """
        targets = collect_goto_targets(next_rule)
        # a question may not goto itself (trivial self-loop guard)
        self_loop = targets & {ignore_order}
        if self_loop:
            raise QuestionValidationError(
                f"next_rule may not goto its own order ({sorted(self_loop)})"
            )

        # Reject explicit goto targets that are self-loops.
        # Forward references (goto → a question not yet added) are intentionally
        # allowed here; _ensure_no_cycle will catch typos in goto targets once
        # all questions exist in the graph, so no dangling references survive.
        self_loop = targets & {ignore_order}
        if self_loop:
            raise QuestionValidationError(
                f"next_rule may not goto its own order ({sorted(self_loop)})"
            )

    def _ensure_no_cycle(
        self,
        survey_id: ObjectId,
        new_order: int,
        next_rule: dict,
    ) -> None:
        """Reject ``next_rule`` configs that introduce cycles (per §6.5).

        Builds a directed graph of (existing + new) questions where an edge
        X → Y exists if:
        1. X has an explicit integer ``goto`` to Y, or
        2. X has ``fallback: "next"`` and Y = X.order + 1 (implicit advance).

        Detects cycles via DFS. The new question's implicit edge to
        ``new_order + 1`` is included so that a ``fallback: "next"`` on the
        new question does not slip past the check.
        """
        graph: dict[int, set[int]] = {}

        # add all existing questions
        for q in self._coll.find(
            {"survey_id": survey_id}, projection={"order": 1, "next_rule": 1}
        ):
            rule = q.get("next_rule") or {}
            targets = collect_goto_targets(rule)
            fallback = rule.get("fallback", "next")
            if fallback == "next":
                targets.add(q["order"] + 1)
            elif isinstance(fallback, int):
                targets.add(fallback)
            graph[q["order"]] = targets

        # add the new question
        targets = collect_goto_targets(next_rule)
        fallback = next_rule.get("fallback", "next")
        if fallback == "next":
            targets.add(new_order + 1)
        elif isinstance(fallback, int):
            targets.add(fallback)
        graph[new_order] = targets

        # all orders that will exist after the insert
        all_orders = sorted(graph.keys())
        # cap "next" edges that point past the last question → "end" (no node)
        for o in list(graph.keys()):
            targets = {t for t in graph[o] if t in graph}
            graph[o] = targets

        # Reject explicit goto targets of the NEW question that point to
        # orders LESS THAN the new order but that do not exist yet
        # (backward or cross jumping to a question that will never exist).
        # Forward references (goto → a higher order not yet added) are
        # intentionally allowed here so questions can be built incrementally;
        # the cycle-detection DFS below catches dangling forward references
        # that would form unreachable nodes, and the survey publish gate
        # validates all targets at the end.
        new_explicit = collect_goto_targets(next_rule)
        below_new = {t for t in new_explicit if isinstance(t, int) and t < new_order}
        invalid_backward = below_new - set(graph.keys())
        if invalid_backward:
            raise QuestionValidationError(
                f"next_rule references unknown order(s): {sorted(invalid_backward)}"
            )

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {o: WHITE for o in graph}

        def dfs(node: int) -> bool:
            color[node] = GRAY
            for nxt in graph.get(node, ()):
                if nxt == node:
                    # self-loop: a question can goto itself; not a cycle
                    continue
                if nxt not in color:
                    continue
                if color[nxt] == GRAY:
                    return True
                if color[nxt] == WHITE and dfs(nxt):
                    return True
            color[node] = BLACK
            return False

        for order in list(color.keys()):
            if color[order] == WHITE and dfs(order):
                raise QuestionValidationError(
                    f"next_rule introduces a cycle at order {order} in survey {survey_id}"
                )

    # ------------------------------------------------------------------
    # validation pass-through
    # ------------------------------------------------------------------

    def validate_answer_for_question(self, question: dict, value: Any) -> None:
        """Validate an answer against a single question document.

        Raises :class:`ValidationError` on failure.
        """
        v = dict(question.get("validation") or {})
        # promote top-level `required` into validation so _validate_* sees it
        if "required" in question:
            v.setdefault("required", question["required"])
        try:
            validate_answer(
                question["type"],
                value,
                v,
                options=question.get("options"),
            )
        except ValidationError as exc:
            # attach question context for downstream error messages
            raise ValidationError(
                f"question order={question.get('order')} ({question.get('type')}): {exc}"
            ) from exc


# re-export for convenience
__all__ = ["QuestionRepo", "QuestionValidationError"]
from ..validation import ValidationError  # noqa: E402  (re-export)
