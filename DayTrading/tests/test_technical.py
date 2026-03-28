"""Tests for technical.py — pure functions, no external dependencies."""

import pytest
from analysis.technical import (
    compute_vwap,
    compute_relative_volume,
    compute_momentum,
    find_structure_break,
    analyze,
)


def _bar(close, high=None, low=None, volume=100, ticker="AAPL"):
    return {
        "ticker": ticker,
        "open": close,
        "high": high if high is not None else close + 0.10,
        "low": low if low is not None else close - 0.10,
        "close": close,
        "volume": volume,
        "vwap": close,
        "timestamp": "2026-03-28T10:00:00Z",
        "resolution": "1min",
    }


class TestComputeVWAP:
    def test_basic(self):
        bars = [_bar(100, high=101, low=99, volume=100),
                _bar(102, high=103, low=101, volume=200)]
        vwap = compute_vwap(bars)
        assert vwap is not None
        assert 100 < vwap < 103

    def test_zero_volume_returns_none(self):
        bars = [_bar(100, volume=0)]
        assert compute_vwap(bars) is None

    def test_single_bar(self):
        bars = [_bar(100, high=101, low=99, volume=100)]
        vwap = compute_vwap(bars)
        assert vwap == pytest.approx((101 + 99 + 100) / 3, abs=0.01)

    def test_bars_with_zero_volume_ignored(self):
        bars = [_bar(100, volume=100), _bar(200, volume=0)]
        vwap = compute_vwap(bars)
        assert vwap == pytest.approx((100.1 + 99.9 + 100) / 3, abs=0.1)


class TestComputeRelativeVolume:
    def test_above_average(self):
        bars = [_bar(100, volume=100)] * 20 + [_bar(100, volume=300)]
        rvol = compute_relative_volume(bars)
        assert rvol == pytest.approx(3.0, abs=0.1)

    def test_equal_to_average(self):
        bars = [_bar(100, volume=100)] * 21
        rvol = compute_relative_volume(bars)
        assert rvol == pytest.approx(1.0, abs=0.01)

    def test_insufficient_bars_returns_none(self):
        bars = [_bar(100, volume=100)]
        assert compute_relative_volume(bars) is None

    def test_zero_average_volume_returns_none(self):
        bars = [_bar(100, volume=0)] * 21
        assert compute_relative_volume(bars) is None


class TestComputeMomentum:
    def test_positive_momentum(self):
        bars = [_bar(100)] * 4 + [_bar(105)]
        mom = compute_momentum(bars, period=4)
        assert mom == pytest.approx(5.0, abs=0.01)

    def test_negative_momentum(self):
        bars = [_bar(100)] * 4 + [_bar(95)]
        mom = compute_momentum(bars, period=4)
        assert mom == pytest.approx(-5.0, abs=0.01)

    def test_insufficient_bars_returns_none(self):
        bars = [_bar(100)] * 3
        assert compute_momentum(bars, period=5) is None

    def test_zero_base_returns_none(self):
        bars = [_bar(0)] * 4 + [_bar(100)]
        assert compute_momentum(bars, period=4) is None


class TestFindStructureBreak:
    def test_breakout_above_high(self):
        window = [_bar(100, high=100)] * 10
        current = _bar(101, high=102, low=100)
        result = find_structure_break(window + [current], lookback=10)
        assert result["breakout_high"] is True
        assert result["breakdown_low"] is False

    def test_breakdown_below_low(self):
        window = [_bar(100, low=100)] * 10
        current = _bar(98, high=99, low=97)
        result = find_structure_break(window + [current], lookback=10)
        assert result["breakdown_low"] is True
        assert result["breakout_high"] is False

    def test_no_break(self):
        window = [_bar(100)] * 10
        current = _bar(100)
        result = find_structure_break(window + [current], lookback=10)
        assert result["breakout_high"] is False
        assert result["breakdown_low"] is False

    def test_insufficient_bars(self):
        bars = [_bar(100)] * 5
        result = find_structure_break(bars, lookback=10)
        assert result["breakout_high"] is False
        assert result["breakdown_low"] is False

    def test_returns_local_high_and_low(self):
        bars = [_bar(100, high=105, low=95)] * 10 + [_bar(100)]
        result = find_structure_break(bars, lookback=10)
        assert result["local_high"] == pytest.approx(105.1, abs=0.2)
        assert result["local_low"] == pytest.approx(94.9, abs=0.2)

    def test_returns_breakout_bar_low(self):
        bars = [_bar(100)] * 10 + [_bar(101, low=99.5)]
        result = find_structure_break(bars, lookback=10)
        assert result["breakout_bar_low"] == pytest.approx(99.5, abs=0.01)


class TestAnalyze:
    def test_returns_all_expected_keys(self):
        bars = [_bar(100 + i) for i in range(25)]
        result = analyze(bars)
        for key in ("ticker", "close", "vwap", "above_vwap", "relative_volume",
                    "momentum", "breakout_high", "breakdown_low", "local_high", "local_low"):
            assert key in result

    def test_empty_bars_returns_empty_dict(self):
        assert analyze([]) == {}

    def test_above_vwap_flag(self):
        bars = [_bar(100)] * 24 + [_bar(110)]
        result = analyze(bars)
        assert result["above_vwap"] is True
