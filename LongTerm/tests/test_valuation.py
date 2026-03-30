"""Tests for analysis/valuation.py — no real Claude API calls."""

import json
import pytest
from unittest.mock import MagicMock, patch

import anthropic
from analysis.valuation import assess, _fmt


def _cfg():
    cfg = MagicMock()
    cfg.model = "claude-opus-4-6"
    cfg.max_tokens = 512
    return cfg


def _metrics(pe=20.0, peg=1.5, pfcf=25.0, ev_ebitda=15.0):
    return {"pe_ratio": pe, "peg_ratio": peg, "pfcf": pfcf, "ev_ebitda": ev_ebitda}


def _claude_response(grade="fair", summary="Fairly valued."):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps({
        "valuation_grade": grade,
        "valuation_summary": summary,
    }))]
    return msg


class TestFmt:
    def test_none_returns_na(self):
        assert _fmt(None) == "n/a"

    def test_float_formatted_with_x(self):
        assert _fmt(20.5) == "20.5x"

    def test_integer_formatted(self):
        assert _fmt(15) == "15.0x"

    def test_non_numeric_returns_na(self):
        assert _fmt("bad") == "n/a"


class TestAssess:
    @patch("analysis.valuation._claude.create_message")
    def test_returns_structured_result(self, mock_create):
        mock_create.return_value = _claude_response("cheap", "Good value here.")
        result = assess("AAPL", _metrics(), _cfg())
        assert result is not None
        assert result["valuation_grade"] == "cheap"
        assert result["valuation_summary"] == "Good value here."

    @patch("analysis.valuation._claude.create_message")
    def test_metrics_passed_through_to_result(self, mock_create):
        mock_create.return_value = _claude_response()
        metrics = _metrics(pe=18.0, peg=1.2, pfcf=22.0, ev_ebitda=12.0)
        result = assess("AAPL", metrics, _cfg())
        assert result["pe_ratio"] == 18.0
        assert result["peg_ratio"] == 1.2
        assert result["pfcf_ratio"] == 22.0
        assert result["ev_ebitda"] == 12.0

    @patch("analysis.valuation._claude.create_message")
    def test_invalid_grade_defaults_to_unknown(self, mock_create):
        msg = MagicMock()
        msg.content = [MagicMock(text=json.dumps({
            "valuation_grade": "overvalued",  # not in allowed set
            "valuation_summary": "Some text.",
        }))]
        mock_create.return_value = msg
        result = assess("AAPL", _metrics(), _cfg())
        assert result["valuation_grade"] == "unknown"

    @patch("analysis.valuation._claude.create_message")
    def test_returns_none_on_json_error(self, mock_create):
        msg = MagicMock()
        msg.content = [MagicMock(text="not json at all")]
        mock_create.return_value = msg
        assert assess("AAPL", _metrics(), _cfg()) is None

    @patch("analysis.valuation._claude.create_message")
    def test_returns_none_on_api_error(self, mock_create):
        mock_create.side_effect = anthropic.APIError(
            message="down", request=MagicMock(), body={}
        )
        assert assess("AAPL", _metrics(), _cfg()) is None

    @patch("analysis.valuation._claude.create_message")
    def test_handles_none_metrics_gracefully(self, mock_create):
        mock_create.return_value = _claude_response()
        result = assess("AAPL", {"pe_ratio": None, "peg_ratio": None,
                                  "pfcf": None, "ev_ebitda": None}, _cfg())
        assert result is not None  # should not raise

    @patch("analysis.valuation._claude.create_message")
    def test_all_valid_grades_accepted(self, mock_create):
        for grade in ("cheap", "fair", "expensive", "unknown"):
            mock_create.return_value = _claude_response(grade)
            result = assess("AAPL", _metrics(), _cfg())
            assert result["valuation_grade"] == grade
