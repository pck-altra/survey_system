"""Tests for app/validation.py."""
from __future__ import annotations

import pytest
from app.validation import validate_answer, ValidationError


class TestValidation:
    # ── single ───────────────────────────────────────────────────────────────

    def test_single_valid(self):
        validate_answer("single", "男", options=["男", "女", "其他"])

    def test_single_invalid_option(self):
        with pytest.raises(ValidationError):
            validate_answer("single", "unknown", options=["男", "女"])

    def test_single_required_empty(self):
        with pytest.raises(ValidationError):
            validate_answer("single", None, validation={"required": True})

    def test_single_not_required_empty(self):
        validate_answer("single", None, validation={"required": False})

    # ── multi ────────────────────────────────────────────────────────────────

    def test_multi_valid(self):
        validate_answer("multi", ["苹果", "香蕉"], options=["苹果", "香蕉", "西瓜"])

    def test_multi_too_few(self):
        with pytest.raises(ValidationError):
            validate_answer("multi", [], validation={"required": True})

    def test_multi_min_count(self):
        with pytest.raises(ValidationError):
            validate_answer("multi", ["苹果"], validation={"min_count": 2})

    def test_multi_max_count(self):
        with pytest.raises(ValidationError):
            validate_answer(
                "multi", ["A", "B", "C", "D"],
                validation={"max_count": 3},
            )

    def test_multi_exact_count(self):
        with pytest.raises(ValidationError):
            validate_answer(
                "multi", ["A", "B", "C"],
                validation={"exact_count": 2},
            )
        validate_answer(
            "multi", ["A", "B"],
            validation={"exact_count": 2},
        )

    # ── text ─────────────────────────────────────────────────────────────────

    def test_text_valid(self):
        validate_answer("text", "我是一名大学生", validation={"min_len": 2, "max_len": 200})

    def test_text_too_short(self):
        with pytest.raises(ValidationError):
            validate_answer("text", "Hi", validation={"min_len": 10})

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            validate_answer("text", "x" * 201, validation={"max_len": 200})

    def test_text_not_required_empty(self):
        validate_answer("text", None, validation={"required": False})

    # ── number ───────────────────────────────────────────────────────────────

    def test_number_valid(self):
        validate_answer("number", 25, validation={"min": 0, "max": 120})

    def test_number_too_low(self):
        with pytest.raises(ValidationError):
            validate_answer("number", -1, validation={"min": 0})

    def test_number_too_high(self):
        with pytest.raises(ValidationError):
            validate_answer("number", 200, validation={"max": 120})

    def test_number_integer_only_float(self):
        with pytest.raises(ValidationError):
            validate_answer("number", 25.7, validation={"integer_only": True})

    def test_number_integer_only_whole_float(self):
        # 25.0 is integer in value; should pass integer_only check
        result = validate_answer("number", 25.0, validation={"integer_only": True})
        assert result == 25.0

    def test_number_non_numeric(self):
        with pytest.raises(ValidationError):
            validate_answer("number", "twenty")

    def test_number_bool_rejected(self):
        with pytest.raises(ValidationError):
            validate_answer("number", True)

    def test_number_not_required_empty(self):
        validate_answer("number", None, validation={"required": False})

    # ── unsupported type ─────────────────────────────────────────────────────

    def test_unsupported_type(self):
        with pytest.raises(ValidationError):
            validate_answer("ranking", "value")
