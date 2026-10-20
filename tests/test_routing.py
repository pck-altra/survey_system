"""Tests for app/routing.py."""
from __future__ import annotations

import pytest
from app.routing import resolve, collect_goto_targets, RoutingError


class TestRouting:
    # ── resolve ───────────────────────────────────────────────────────────────

    def test_default_next(self):
        assert resolve({"mode": "default", "fallback": "next"}, "anything") == "next"

    def test_default_end(self):
        assert resolve({"mode": "default", "fallback": "end"}, "anything") == "end"

    def test_default_goto_order(self):
        assert resolve({"mode": "default", "fallback": 5}, "anything") == 5

    def test_by_option_match(self):
        rule = {
            "mode": "by_option",
            "branches": [{"when": "A", "goto": 3}, {"when": "B", "goto": 5}],
            "fallback": "next",
        }
        assert resolve(rule, "A") == 3
        assert resolve(rule, "B") == 5

    def test_by_option_no_match(self):
        rule = {
            "mode": "by_option",
            "branches": [{"when": "A", "goto": 3}],
            "fallback": "next",
        }
        assert resolve(rule, "C") == "next"

    def test_by_contains_when_any(self):
        rule = {
            "mode": "by_contains",
            "branches": [{"when_any": ["篮球", "足球"], "goto": 4}],
            "fallback": "next",
        }
        assert resolve(rule, ["篮球", "游泳"]) == 4

    def test_by_contains_when_all(self):
        rule = {
            "mode": "by_contains",
            "branches": [{"when_all": ["A", "B"], "goto": 6}],
            "fallback": "next",
        }
        assert resolve(rule, ["A", "B", "C"]) == 6

    def test_by_contains_no_match(self):
        rule = {
            "mode": "by_contains",
            "branches": [{"when_any": ["A", "B"], "goto": 4}],
            "fallback": "end",
        }
        assert resolve(rule, ["C", "D"]) == "end"

    def test_by_range_gte(self):
        rule = {
            "mode": "by_range",
            "branches": [{"when": {"op": ">=", "value": 18}, "goto": 5}],
            "fallback": "next",
        }
        assert resolve(rule, 18) == 5
        assert resolve(rule, 25) == 5

    def test_by_range_lt(self):
        rule = {
            "mode": "by_range",
            "branches": [{"when": {"op": "<", "value": 18}, "goto": 7}],
            "fallback": "next",
        }
        assert resolve(rule, 17) == 7

    def test_by_range_non_numeric_fallback(self):
        rule = {
            "mode": "by_range",
            "branches": [{"when": {"op": ">=", "value": 18}, "goto": 5}],
            "fallback": "end",
        }
        assert resolve(rule, "not a number") == "end"

    def test_unknown_mode_raises(self):
        with pytest.raises(RoutingError):
            resolve({"mode": "by_jump", "fallback": "next"}, "val")

    def test_invalid_fallback_raises(self):
        with pytest.raises(RoutingError):
            resolve({"mode": "default", "fallback": {"bad": "type"}}, "val")

    # ── collect_goto_targets ─────────────────────────────────────────────────

    def test_collect_goto_targets_branches(self):
        rule = {
            "mode": "by_option",
            "branches": [{"when": "A", "goto": 3}, {"when": "B", "goto": 5}],
            "fallback": 2,
        }
        assert collect_goto_targets(rule) == {3, 5, 2}

    def test_collect_goto_targets_empty(self):
        assert collect_goto_targets({}) == set()
        assert collect_goto_targets({"mode": "default", "fallback": "next"}) == set()
