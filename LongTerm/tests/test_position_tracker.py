"""Tests for portfolio/position_tracker.py — no real API calls."""

import pytest
from unittest.mock import MagicMock, patch

from portfolio.position_tracker import get_portfolio_summary


def _pos(ticker="AAPL", entry_price=150.0, shares=10.0, thesis_id=None):
    return {
        "id": 1, "ticker": ticker, "thesis_id": thesis_id,
        "entry_date": "2024-01-01T00:00:00+00:00",
        "entry_price": entry_price, "shares": shares,
        "status": "open", "exit_date": None, "exit_price": None,
        "pnl": None, "notes": None,
    }


def _quote(price=160.0):
    return {"price": price, "change_pct": 1.5, "market_cap": 1_000_000_000}


class TestGetPortfolioSummary:
    def test_empty_positions_returns_empty(self):
        db = MagicMock()
        db.get_open_positions.return_value = []
        assert get_portfolio_summary(db, "key") == []

    @patch("portfolio.position_tracker.financials.get_quote")
    def test_unrealized_pnl_calculated_correctly(self, mock_quote):
        mock_quote.return_value = _quote(price=160.0)
        db = MagicMock()
        db.get_open_positions.return_value = [_pos(entry_price=150.0, shares=10.0)]
        result = get_portfolio_summary(db, "key")
        assert result[0]["unrealized_pnl"] == 100.0  # (160-150)*10

    @patch("portfolio.position_tracker.financials.get_quote")
    def test_pnl_pct_calculated_correctly(self, mock_quote):
        mock_quote.return_value = _quote(price=165.0)
        db = MagicMock()
        db.get_open_positions.return_value = [_pos(entry_price=150.0, shares=10.0)]
        result = get_portfolio_summary(db, "key")
        assert result[0]["pnl_pct"] == pytest.approx(10.0)

    @patch("portfolio.position_tracker.financials.get_quote")
    def test_negative_pnl_for_losing_position(self, mock_quote):
        mock_quote.return_value = _quote(price=140.0)
        db = MagicMock()
        db.get_open_positions.return_value = [_pos(entry_price=150.0, shares=10.0)]
        result = get_portfolio_summary(db, "key")
        assert result[0]["unrealized_pnl"] == -100.0
        assert result[0]["pnl_pct"] < 0

    @patch("portfolio.position_tracker.financials.get_quote")
    def test_current_value_calculated(self, mock_quote):
        mock_quote.return_value = _quote(price=160.0)
        db = MagicMock()
        db.get_open_positions.return_value = [_pos(entry_price=150.0, shares=10.0)]
        result = get_portfolio_summary(db, "key")
        assert result[0]["current_value"] == 1600.0

    @patch("portfolio.position_tracker.financials.get_quote")
    def test_quote_failure_yields_none_fields(self, mock_quote):
        mock_quote.return_value = None
        db = MagicMock()
        db.get_open_positions.return_value = [_pos()]
        result = get_portfolio_summary(db, "key")
        assert result[0]["current_price"] is None
        assert result[0]["unrealized_pnl"] is None
        assert result[0]["pnl_pct"] is None

    @patch("portfolio.position_tracker.financials.get_quote")
    def test_multiple_positions_returned(self, mock_quote):
        mock_quote.return_value = _quote()
        db = MagicMock()
        db.get_open_positions.return_value = [
            _pos("AAPL"), _pos("MSFT"), _pos("NVDA"),
        ]
        result = get_portfolio_summary(db, "key")
        assert len(result) == 3

    @patch("portfolio.position_tracker.financials.get_quote")
    def test_original_fields_preserved(self, mock_quote):
        mock_quote.return_value = _quote()
        db = MagicMock()
        db.get_open_positions.return_value = [_pos("AAPL", thesis_id=42)]
        result = get_portfolio_summary(db, "key")
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["thesis_id"] == 42
