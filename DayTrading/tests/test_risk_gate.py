"""Tests for execution/risk_gate.py — no real API or DB calls."""

import time
import pytest
from unittest.mock import MagicMock, patch
from datetime import time as dtime

from execution.risk_gate import check


def _cfg(
    tz="America/New_York",
    start="09:30", pause_s="12:00", pause_e="13:00", end="16:00",
    max_pos_pct=0.02, max_daily_loss_pct=0.03, max_open=5, rr=2.0, blackout=2,
):
    cfg = MagicMock()
    cfg.trading_hours.timezone = tz
    cfg.trading_hours.start = start
    cfg.trading_hours.midday_pause_start = pause_s
    cfg.trading_hours.midday_pause_end = pause_e
    cfg.trading_hours.end = end
    cfg.risk.max_position_pct = max_pos_pct
    cfg.risk.max_daily_loss_pct = max_daily_loss_pct
    cfg.risk.max_open_positions = max_open
    cfg.risk.reward_risk_ratio = rr
    cfg.risk.news_blackout_minutes = blackout
    return cfg


def _db(daily_pnl=0.0, open_trades=None):
    db = MagicMock()
    db.get_daily_pnl.return_value = daily_pnl
    db.get_open_trades.return_value = open_trades or []
    return db


def _signal(ticker="AAPL"):
    return {"ticker": ticker, "direction": "long", "close": 150.0}


# Patch helpers for every test that reaches the loss limit check
_patch_equity = patch("execution.risk_gate._get_account_equity", return_value=100_000.0)
_patch_unreal = patch("execution.risk_gate._get_unrealized_pnl", return_value=0.0)


class TestTradingHours:
    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_allowed_during_trading_hours(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        allowed, reason = check(_signal(), _db(), _cfg(), {}, alpaca_client=MagicMock())
        assert allowed
        assert reason is None

    @patch("execution.risk_gate._market_time")
    def test_blocked_before_open(self, mock_time):
        mock_time.return_value = dtime(9, 0)
        allowed, reason = check(_signal(), _db(), _cfg(), {})
        assert not allowed
        assert "outside trading hours" in reason

    @patch("execution.risk_gate._market_time")
    def test_blocked_after_close(self, mock_time):
        mock_time.return_value = dtime(16, 30)
        allowed, reason = check(_signal(), _db(), _cfg(), {})
        assert not allowed
        assert "outside trading hours" in reason

    @patch("execution.risk_gate._market_time")
    def test_blocked_during_midday_pause(self, mock_time):
        mock_time.return_value = dtime(12, 30)
        allowed, reason = check(_signal(), _db(), _cfg(), {})
        assert not allowed
        assert "midday pause" in reason

    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_pause_end_boundary_is_allowed(self, mock_time, _u, _e):
        # Pause is 12:00–13:00; exact end time (13:00) should be allowed
        mock_time.return_value = dtime(13, 0)
        allowed, _ = check(_signal(), _db(), _cfg(), {}, alpaca_client=MagicMock())
        assert allowed


class TestDailyLossLimit:
    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_blocked_when_closed_pnl_exceeds_limit(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        allowed, reason = check(
            _signal(), _db(daily_pnl=-3_500.0), _cfg(), {}, alpaca_client=MagicMock()
        )
        assert not allowed
        assert "daily loss limit" in reason

    @patch("execution.risk_gate._get_unrealized_pnl", return_value=-2_000.0)
    @patch("execution.risk_gate._get_account_equity", return_value=100_000.0)
    @patch("execution.risk_gate._market_time")
    def test_unrealized_losses_counted_against_limit(self, mock_time, _e, _u):
        mock_time.return_value = dtime(10, 30)
        # closed -2k + unrealized -2k = -4k, limit = 3% of 100k = -3k
        allowed, reason = check(
            _signal(), _db(daily_pnl=-2_000.0), _cfg(), {}, alpaca_client=MagicMock()
        )
        assert not allowed
        assert "daily loss limit" in reason

    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_allowed_within_loss_limit(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        allowed, _ = check(
            _signal(), _db(daily_pnl=-500.0), _cfg(), {}, alpaca_client=MagicMock()
        )
        assert allowed


class TestPositionLimits:
    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_blocked_at_max_open_positions(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        trades = [{"ticker": f"T{i}"} for i in range(5)]
        allowed, reason = check(
            _signal(), _db(open_trades=trades), _cfg(), {}, alpaca_client=MagicMock()
        )
        assert not allowed
        assert "max open positions" in reason

    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_blocked_already_in_position_for_ticker(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        allowed, reason = check(
            _signal("AAPL"),
            _db(open_trades=[{"ticker": "AAPL"}]),
            _cfg(), {}, alpaca_client=MagicMock()
        )
        assert not allowed
        assert "already in a position" in reason

    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_different_ticker_position_does_not_block(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        allowed, _ = check(
            _signal("AAPL"),
            _db(open_trades=[{"ticker": "MSFT"}]),
            _cfg(), {}, alpaca_client=MagicMock()
        )
        assert allowed


class TestNewsBlackout:
    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_blocked_within_blackout_window(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        last_news = {"AAPL": time.monotonic() - 30}  # 30s ago, blackout=2min
        allowed, reason = check(
            _signal("AAPL"), _db(), _cfg(), last_news, alpaca_client=MagicMock()
        )
        assert not allowed
        assert "news blackout" in reason

    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_allowed_after_blackout_expires(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        last_news = {"AAPL": time.monotonic() - 300}  # 5min ago, blackout=2min
        allowed, _ = check(
            _signal("AAPL"), _db(), _cfg(), last_news, alpaca_client=MagicMock()
        )
        assert allowed

    @_patch_equity
    @_patch_unreal
    @patch("execution.risk_gate._market_time")
    def test_no_news_record_is_allowed(self, mock_time, _u, _e):
        mock_time.return_value = dtime(10, 30)
        allowed, _ = check(_signal("AAPL"), _db(), _cfg(), {}, alpaca_client=MagicMock())
        assert allowed
