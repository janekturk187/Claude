"""Tests for portfolio/thesis_monitor.py — no real Claude API calls."""

import json
import pytest
from unittest.mock import MagicMock, patch

import anthropic
from portfolio.thesis_monitor import check_thesis, check_all


def _cfg():
    cfg = MagicMock()
    cfg.model = "claude-opus-4-6"
    cfg.max_tokens = 1024
    return cfg


def _thesis(ticker="AAPL", thesis_id=1, assumptions=None):
    return {
        "id": thesis_id,
        "ticker": ticker,
        "thesis_text": "Strong moat, growing cloud revenue",
        "assumptions": json.dumps(assumptions or ["Cloud revenue growing >15% YoY", "Margins stable"]),
        "status": "active",
    }


def _profile():
    return {
        "revenue_trend": "growing",
        "margin_trend": "stable",
        "management_tone": "confident",
        "guidance_direction": "raised",
        "thesis_score": 8,
        "thesis_summary": "Strong quarter.",
    }


def _earnings(n=2):
    return [
        {"period": f"Q{i}", "eps_beat": 1, "guidance_dir": "raised", "quality_score": 8, "trend": "improving"}
        for i in range(n)
    ]


def _claude_response(flag=False, status="intact", flag_reason=""):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps({
        "assumption_checks": [
            {"assumption": "Cloud revenue growing >15% YoY", "status": "valid", "reason": "on track"},
        ],
        "overall_status": status,
        "flag": flag,
        "flag_reason": flag_reason if flag else "",
    }))]
    return msg


class TestCheckThesis:
    def test_flags_immediately_when_no_data_available(self):
        result = check_thesis(_thesis(), profile=None, earnings_history=[], cfg=_cfg())
        assert result is not None
        assert result["flag"] is True
        assert "No company profile" in result["flag_reason"]
        assert result["ticker"] == "AAPL"
        assert result["thesis_id"] == 1

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_returns_structured_result_on_success(self, mock_create):
        mock_create.return_value = _claude_response(flag=False, status="intact")
        result = check_thesis(_thesis(), _profile(), _earnings(), _cfg())
        assert result is not None
        assert result["overall_status"] == "intact"
        assert result["flag"] is False
        assert result["ticker"] == "AAPL"
        assert result["thesis_id"] == 1

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_flag_true_when_claude_flags(self, mock_create):
        mock_create.return_value = _claude_response(flag=True, status="broken", flag_reason="margins collapsed")
        result = check_thesis(_thesis(), _profile(), _earnings(), _cfg())
        assert result["flag"] is True
        assert result["flag_reason"] == "margins collapsed"

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_returns_none_on_json_decode_error(self, mock_create):
        msg = MagicMock()
        msg.content = [MagicMock(text="this is not json")]
        mock_create.return_value = msg
        result = check_thesis(_thesis(), _profile(), _earnings(), _cfg())
        assert result is None

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_returns_none_on_api_error(self, mock_create):
        mock_create.side_effect = anthropic.APIError(
            message="api down", request=MagicMock(), body={}
        )
        result = check_thesis(_thesis(), _profile(), _earnings(), _cfg())
        assert result is None

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_invalid_assumptions_json_falls_back_gracefully(self, mock_create):
        mock_create.return_value = _claude_response()
        thesis = _thesis()
        thesis["assumptions"] = "not valid json {{ at all"
        result = check_thesis(thesis, _profile(), _earnings(), _cfg())
        assert result is not None  # should not raise, falls back to thesis_text

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_works_with_only_earnings_no_profile(self, mock_create):
        mock_create.return_value = _claude_response()
        result = check_thesis(_thesis(), profile=None, earnings_history=_earnings(), cfg=_cfg())
        # Has earnings data so should not early-return with flag
        assert result is not None
        assert "No company profile" not in result.get("flag_reason", "")


class TestCheckAll:
    def test_returns_empty_list_when_no_active_theses(self):
        db = MagicMock()
        db.get_active_theses.return_value = []
        assert check_all(db, _cfg()) == []

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_flags_thesis_in_db_when_flagged(self, mock_create):
        mock_create.return_value = _claude_response(flag=True, status="broken", flag_reason="thesis broken")
        db = MagicMock()
        db.get_active_theses.return_value = [_thesis(ticker="AAPL", thesis_id=1)]
        db.get_latest_profile.return_value = _profile()
        db.get_earnings_history.return_value = _earnings()

        check_all(db, _cfg())
        db.flag_thesis.assert_called_once_with(1, "thesis broken")

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_does_not_flag_db_when_thesis_is_ok(self, mock_create):
        mock_create.return_value = _claude_response(flag=False, status="intact")
        db = MagicMock()
        db.get_active_theses.return_value = [_thesis()]
        db.get_latest_profile.return_value = _profile()
        db.get_earnings_history.return_value = _earnings()

        check_all(db, _cfg())
        db.flag_thesis.assert_not_called()

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_skips_thesis_when_check_returns_none(self, mock_create):
        mock_create.side_effect = anthropic.APIError(
            message="api down", request=MagicMock(), body={}
        )
        db = MagicMock()
        db.get_active_theses.return_value = [_thesis()]
        db.get_latest_profile.return_value = _profile()
        db.get_earnings_history.return_value = _earnings()

        results = check_all(db, _cfg())
        assert results == []
        db.flag_thesis.assert_not_called()

    @patch("portfolio.thesis_monitor._claude.create_message")
    def test_all_theses_checked_independently(self, mock_create):
        mock_create.return_value = _claude_response(flag=False)
        db = MagicMock()
        db.get_active_theses.return_value = [
            _thesis("AAPL", thesis_id=1),
            _thesis("MSFT", thesis_id=2),
        ]
        db.get_latest_profile.return_value = _profile()
        db.get_earnings_history.return_value = _earnings()

        results = check_all(db, _cfg())
        assert len(results) == 2
        assert {r["ticker"] for r in results} == {"AAPL", "MSFT"}
