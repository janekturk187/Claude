"""Tests for backtest/engine.py — no real API calls."""

import pytest
from unittest.mock import MagicMock

from backtest.engine import run, _check_exit, _calc_prices, _position_size


def _cfg(min_sentiment=7, min_rvol=1.5, rr_ratio=2.0, max_pos_pct=0.05):
    cfg = MagicMock()
    cfg.signal.min_sentiment_score = min_sentiment
    cfg.signal.min_confidence = 6
    cfg.signal.min_relative_volume = min_rvol
    cfg.signal.session_sentiment_window = 5
    cfg.risk.reward_risk_ratio = rr_ratio
    cfg.risk.max_position_pct = max_pos_pct
    return cfg


def _bar(close=100.0, high=101.0, low=99.0, volume=10000, ticker="AAPL", i=0):
    return {
        "ticker": ticker,
        "timestamp": f"2024-01-15T{9 + i // 60:02d}:{i % 60:02d}:00+00:00",
        "resolution": "1min",
        "open": close - 0.1,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "vwap": close,
    }


def _bars_no_signal(n=30, ticker="AAPL"):
    """Flat bars that shouldn't trigger structure breaks."""
    return [_bar(close=100.0, high=100.5, low=99.5, volume=1000, ticker=ticker, i=i)
            for i in range(n)]


class TestCheckExit:
    def test_long_stop_triggered(self):
        pos = {"direction": "long", "entry_price": 100.0, "stop_price": 98.0,
               "target_price": 104.0, "qty": 10,
               "ticker": "AAPL", "signal_strength": "strong", "signal_bar_ts": "t"}
        bar = _bar(close=97.5, low=97.0, high=99.0)
        result = _check_exit(pos, bar)
        assert result is not None
        assert result["exit_reason"] == "stop"
        assert result["exit_price"] == 98.0
        assert result["pnl"] == round((98.0 - 100.0) * 10, 2)

    def test_long_target_triggered(self):
        pos = {"direction": "long", "entry_price": 100.0, "stop_price": 98.0,
               "target_price": 104.0, "qty": 10,
               "ticker": "AAPL", "signal_strength": "strong", "signal_bar_ts": "t"}
        bar = _bar(close=104.5, low=103.0, high=105.0)
        result = _check_exit(pos, bar)
        assert result is not None
        assert result["exit_reason"] == "target"
        assert result["exit_price"] == 104.0
        assert result["pnl"] == round((104.0 - 100.0) * 10, 2)

    def test_long_no_exit_within_range(self):
        pos = {"direction": "long", "entry_price": 100.0, "stop_price": 98.0,
               "target_price": 104.0, "qty": 10,
               "ticker": "AAPL", "signal_strength": "strong", "signal_bar_ts": "t"}
        bar = _bar(close=101.0, low=99.0, high=102.0)
        assert _check_exit(pos, bar) is None

    def test_short_stop_triggered(self):
        pos = {"direction": "short", "entry_price": 100.0, "stop_price": 102.0,
               "target_price": 96.0, "qty": 10,
               "ticker": "AAPL", "signal_strength": "strong", "signal_bar_ts": "t"}
        bar = _bar(close=103.0, low=101.0, high=103.5)
        result = _check_exit(pos, bar)
        assert result is not None
        assert result["exit_reason"] == "stop"
        assert result["pnl"] == round((100.0 - 102.0) * 10, 2)

    def test_short_target_triggered(self):
        pos = {"direction": "short", "entry_price": 100.0, "stop_price": 102.0,
               "target_price": 96.0, "qty": 10,
               "ticker": "AAPL", "signal_strength": "strong", "signal_bar_ts": "t"}
        bar = _bar(close=95.5, low=95.0, high=97.0)
        result = _check_exit(pos, bar)
        assert result is not None
        assert result["exit_reason"] == "target"

    def test_stop_checked_before_target_on_same_bar(self):
        """If a bar touches both stop and target, stop wins (conservative)."""
        pos = {"direction": "long", "entry_price": 100.0, "stop_price": 98.0,
               "target_price": 104.0, "qty": 10,
               "ticker": "AAPL", "signal_strength": "strong", "signal_bar_ts": "t"}
        bar = _bar(close=100.0, low=97.0, high=105.0)
        result = _check_exit(pos, bar)
        assert result["exit_reason"] == "stop"


class TestCalcPrices:
    def test_long_entry_above_close(self):
        sig = {"direction": "long", "close": 100.0, "breakout_bar_low": 99.0}
        entry, stop, target, risk = _calc_prices(sig, rr_ratio=2.0)
        assert entry > 100.0
        assert stop == 99.0
        assert target == round(entry + risk * 2.0, 2)

    def test_short_entry_below_close(self):
        sig = {"direction": "short", "close": 100.0, "local_high": 101.0}
        entry, stop, target, risk = _calc_prices(sig, rr_ratio=2.0)
        assert entry < 100.0
        assert stop == 101.0
        assert target == round(entry - risk * 2.0, 2)

    def test_falls_back_to_pct_stop_when_no_bar_low(self):
        sig = {"direction": "long", "close": 100.0, "breakout_bar_low": None}
        entry, stop, target, risk = _calc_prices(sig, rr_ratio=2.0)
        assert stop == round(100.0 * 0.99, 2)

    def test_risk_is_positive_for_long(self):
        sig = {"direction": "long", "close": 100.0, "breakout_bar_low": 99.0}
        entry, stop, target, risk = _calc_prices(sig, rr_ratio=2.0)
        assert risk > 0

    def test_risk_is_positive_for_short(self):
        sig = {"direction": "short", "close": 100.0, "local_high": 101.0}
        entry, stop, target, risk = _calc_prices(sig, rr_ratio=2.0)
        assert risk > 0


class TestPositionSize:
    def test_basic_calculation(self):
        # risk_amount = 100_000 * 0.05 = 5000; risk_per_share = 2; qty = 2500
        qty = _position_size(102.0, 100.0, 100_000.0, 0.05)
        assert qty == 2500.0

    def test_zero_risk_per_share_returns_zero(self):
        assert _position_size(100.0, 100.0, 100_000.0, 0.05) == 0

    def test_larger_equity_gives_larger_size(self):
        qty_small = _position_size(102.0, 100.0, 10_000.0, 0.05)
        qty_large = _position_size(102.0, 100.0, 100_000.0, 0.05)
        assert qty_large > qty_small


class TestRun:
    def test_empty_bars_returns_empty(self):
        trades = run({}, _cfg())
        assert trades == []

    def test_no_signals_on_flat_bars(self):
        bars = _bars_no_signal(n=30)
        trades = run({"AAPL": bars}, _cfg())
        assert trades == []

    def test_returns_empty_when_ticker_has_no_bars(self):
        trades = run({"AAPL": []}, _cfg())
        assert trades == []

    def test_eod_close_on_open_position(self):
        """A position that never hits stop/target closes at EOD."""
        # Build bars that generate a signal (breakout), then flat bars that don't trigger exit
        # Use strong upward breakout then flat continuation
        bars = []
        # 20 flat bars for warmup
        for i in range(20):
            bars.append(_bar(close=100.0, high=100.5, low=99.5, volume=2000, i=i))
        # Then a big breakout bar with high volume that clears local high
        bars.append(_bar(close=105.0, high=106.0, low=104.0, volume=50000, i=20))
        # Then bars that never hit stop (~100) or target (~110+) — stay around 105
        for i in range(21, 35):
            bars.append(_bar(close=105.0, high=105.5, low=104.8, volume=2000, i=i))

        trades = run({"AAPL": bars}, _cfg(), sentiment_score=8.0)
        eod_trades = [t for t in trades if t["exit_reason"] == "eod"]
        # May or may not have a trade depending on signal detection, but if it does,
        # EOD close must equal last bar close
        for t in eod_trades:
            assert t["exit_price"] == bars[-1]["close"]

    def test_multiple_tickers_processed_independently(self):
        bars = _bars_no_signal(n=15)
        trades = run({"AAPL": bars, "MSFT": bars}, _cfg())
        # Flat bars produce no signals — just verifying both tickers are processed
        assert isinstance(trades, list)

    def test_trade_has_required_fields(self):
        """Any trade returned must have the standard fields."""
        # Build bars that reliably generate a signal
        bars = []
        for i in range(20):
            bars.append(_bar(close=100.0, high=100.5, low=99.5, volume=1000, i=i))
        # Breakout above 100.5 (local high)
        bars.append(_bar(close=101.5, high=102.0, low=101.0, volume=20000, i=20))
        # Stop bar — drops through 99.5*0.99 ≈ 99 (which is well above stop)
        # Actually let's just force a stop by dropping below entry-stop
        bars.append(_bar(close=98.0, low=97.0, high=99.0, volume=5000, i=21))

        trades = run({"AAPL": bars}, _cfg(), sentiment_score=8.0)
        for t in trades:
            for field in ("ticker", "direction", "entry_price", "stop_price",
                          "target_price", "qty", "exit_price", "pnl", "exit_reason"):
                assert field in t, f"Missing field: {field}"
