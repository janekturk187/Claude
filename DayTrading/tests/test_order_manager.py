"""Tests for execution/order_manager.py — no real Alpaca API calls."""

import pytest
from unittest.mock import MagicMock, patch

from execution.order_manager import OrderManager


def _cfg(max_position_pct=0.02, rr=2.0):
    cfg = MagicMock()
    cfg.alpaca.api_key = "key"
    cfg.alpaca.secret_key = "secret"
    cfg.alpaca.paper = True
    cfg.risk.max_position_pct = max_position_pct
    cfg.risk.reward_risk_ratio = rr
    return cfg


def _long_signal(close=100.0, breakout_bar_low=98.0):
    return {
        "ticker": "AAPL",
        "direction": "long",
        "close": close,
        "breakout_bar_low": breakout_bar_low,
        "local_high": None,
        "signal_strength": "strong",
    }


def _short_signal(close=100.0, local_high=102.0):
    return {
        "ticker": "AAPL",
        "direction": "short",
        "close": close,
        "breakout_bar_low": None,
        "local_high": local_high,
        "signal_strength": "strong",
    }


@patch("execution.order_manager.TradingClient")
class TestPositionSize:
    def test_basic_calculation(self, _mock_client):
        om = OrderManager(_cfg(max_position_pct=0.02))
        # risk_amount = 10_000 * 0.02 = 200; risk_per_share = 2.1
        size = om._position_size(entry=100.1, stop=98.0, equity=10_000.0)
        assert size == round(200.0 / 2.1, 2)

    def test_zero_risk_per_share_returns_zero(self, _mock_client):
        om = OrderManager(_cfg())
        assert om._position_size(100.0, 100.0, 10_000.0) == 0

    def test_larger_equity_scales_size(self, _mock_client):
        om = OrderManager(_cfg())
        small = om._position_size(100.0, 98.0, 10_000.0)
        large = om._position_size(100.0, 98.0, 100_000.0)
        assert large == small * 10


@patch("execution.order_manager.TradingClient")
class TestSubmit:
    def _setup_om(self, mock_client_class, equity="100000"):
        om = OrderManager(_cfg())
        om.client.get_account.return_value.equity = equity
        om.client.submit_order.return_value.id = "order-123"
        return om

    def test_successful_long_order_returns_trade_id(self, mock_client_class):
        om = self._setup_om(mock_client_class)
        db = MagicMock()
        db.open_trade.return_value = 42

        trade_id = om.submit(_long_signal(), db)

        assert trade_id == 42
        om.client.submit_order.assert_called_once()
        db.open_trade.assert_called_once()

    def test_successful_short_order_returns_trade_id(self, mock_client_class):
        om = self._setup_om(mock_client_class)
        db = MagicMock()
        db.open_trade.return_value = 7

        trade_id = om.submit(_short_signal(), db)
        assert trade_id == 7

    def test_long_entry_is_above_close(self, mock_client_class):
        om = self._setup_om(mock_client_class)
        db = MagicMock()
        db.open_trade.return_value = 1
        om.submit(_long_signal(close=100.0), db)

        call_kwargs = om.client.submit_order.call_args[0][0]
        assert call_kwargs.limit_price > 100.0

    def test_short_entry_is_below_close(self, mock_client_class):
        om = self._setup_om(mock_client_class)
        db = MagicMock()
        db.open_trade.return_value = 1
        om.submit(_short_signal(close=100.0), db)

        call_kwargs = om.client.submit_order.call_args[0][0]
        assert call_kwargs.limit_price < 100.0

    def test_returns_none_when_equity_unavailable(self, mock_client_class):
        om = OrderManager(_cfg())
        om.client.get_account.side_effect = Exception("network error")
        assert om.submit(_long_signal(), MagicMock()) is None

    def test_returns_none_on_submission_failure(self, mock_client_class):
        om = self._setup_om(mock_client_class)
        om.client.submit_order.side_effect = Exception("rejected by broker")
        assert om.submit(_long_signal(), MagicMock()) is None

    def test_returns_none_when_risk_is_negative(self, mock_client_class):
        om = self._setup_om(mock_client_class)
        # stop above entry for a long → negative risk
        sig = _long_signal(close=100.0, breakout_bar_low=101.0)
        assert om.submit(sig, MagicMock()) is None

    def test_db_failure_after_order_returns_none_without_raising(self, mock_client_class):
        om = self._setup_om(mock_client_class)
        db = MagicMock()
        db.open_trade.side_effect = Exception("db locked")

        result = om.submit(_long_signal(), db)
        assert result is None
        # Order was submitted — verify it was not silently skipped
        om.client.submit_order.assert_called_once()
