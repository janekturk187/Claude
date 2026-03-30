"""Tests for backtest/metrics.py."""

import pytest
from backtest.metrics import calculate


def _trade(pnl, exit_reason="target"):
    return {
        "ticker": "AAPL", "direction": "long",
        "entry_price": 150.0, "exit_price": 155.0,
        "stop_price": 148.0, "target_price": 156.0,
        "qty": 10, "pnl": pnl, "exit_reason": exit_reason,
    }


class TestCalculate:
    def test_empty_trades_returns_zeros(self):
        m = calculate([])
        assert m["total_trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["total_pnl"] == 0.0

    def test_counts_winners_and_losers(self):
        trades = [_trade(50), _trade(-20), _trade(30)]
        m = calculate(trades)
        assert m["winners"] == 2
        assert m["losers"] == 1
        assert m["total_trades"] == 3

    def test_win_rate_calculation(self):
        trades = [_trade(50), _trade(-20), _trade(30), _trade(-10)]
        m = calculate(trades)
        assert m["win_rate"] == 50.0

    def test_total_pnl(self):
        trades = [_trade(50), _trade(-20), _trade(30)]
        m = calculate(trades)
        assert m["total_pnl"] == 60.0

    def test_avg_win_and_avg_loss(self):
        trades = [_trade(40), _trade(60), _trade(-30), _trade(-10)]
        m = calculate(trades)
        assert m["avg_win"] == 50.0
        assert m["avg_loss"] == -20.0

    def test_profit_factor(self):
        trades = [_trade(100), _trade(-50)]
        m = calculate(trades)
        assert m["profit_factor"] == 2.0

    def test_profit_factor_none_when_no_losers(self):
        trades = [_trade(100), _trade(50)]
        m = calculate(trades)
        assert m["profit_factor"] is None  # infinite

    def test_profit_factor_zero_when_no_winners(self):
        trades = [_trade(-50), _trade(-30)]
        m = calculate(trades)
        assert m["profit_factor"] == 0.0

    def test_max_drawdown(self):
        # +100, -150 = trough of -50 from peak of 100 → drawdown of 150
        trades = [_trade(100), _trade(-150)]
        m = calculate(trades)
        assert m["max_drawdown"] == 150.0

    def test_max_drawdown_zero_when_monotonically_increasing(self):
        trades = [_trade(10), _trade(20), _trade(30)]
        m = calculate(trades)
        assert m["max_drawdown"] == 0.0

    def test_exits_by_reason(self):
        trades = [
            _trade(50, "target"),
            _trade(-20, "stop"),
            _trade(10, "eod"),
            _trade(-5, "stop"),
        ]
        m = calculate(trades)
        assert m["exits_by_reason"]["target"] == 1
        assert m["exits_by_reason"]["stop"] == 2
        assert m["exits_by_reason"]["eod"] == 1

    def test_zero_pnl_trade_counted_as_loser(self):
        trades = [_trade(0)]
        m = calculate(trades)
        assert m["losers"] == 1
        assert m["winners"] == 0
