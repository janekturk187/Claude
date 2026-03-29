"""Tests for signal/confluence.py — no external dependencies."""

import pytest
from unittest.mock import MagicMock
from signals.confluence import evaluate, _strength


def _cfg(min_sentiment=7, min_rvol=1.5):
    cfg = MagicMock()
    cfg.min_sentiment_score = min_sentiment
    cfg.min_relative_volume = min_rvol
    return cfg


def _tech(breakout_high=False, breakdown_low=False, above_vwap=True,
          rvol=2.0, momentum=1.0, close=100.0, local_high=99.0, local_low=95.0):
    return {
        "ticker": "AAPL",
        "close": close,
        "vwap": 98.0,
        "above_vwap": above_vwap,
        "relative_volume": rvol,
        "momentum": momentum,
        "breakout_high": breakout_high,
        "breakdown_low": breakdown_low,
        "local_high": local_high,
        "local_low": local_low,
        "breakout_bar_low": local_low,
    }


class TestStrength:
    def test_long_strong(self):
        tech = _tech(rvol=2.0, momentum=1.0)
        assert _strength(tech, 9, 3.0, "long", _cfg()) == "strong"

    def test_long_moderate(self):
        tech = _tech(rvol=2.0, momentum=0.3)
        assert _strength(tech, 7, None, "long", _cfg()) in ("moderate", "strong")

    def test_long_weak_low_rvol(self):
        tech = _tech(rvol=1.0, momentum=0.3)
        result = _strength(tech, 7, None, "long", _cfg())
        assert result in ("weak", "none")

    def test_short_strong_bearish_sentiment(self):
        tech = _tech(rvol=2.0, momentum=-1.0)
        assert _strength(tech, 1, -3.0, "short", _cfg()) == "strong"

    def test_short_bearish_sentiment_scores_points(self):
        tech = _tech(rvol=2.0, momentum=0.0)
        # score=1 is very bearish — should add 2 points for short
        result_short = _strength(tech, 1, None, "short", _cfg())
        # A bullish score of 1 should add 0 points for long
        result_long = _strength(tech, 1, None, "long", _cfg())
        assert result_short != "none"  # bearish sentiment helps short
        assert result_long in ("none", "weak")  # doesn't help long


class TestEvaluate:
    def test_long_signal_generated(self):
        tech = _tech(breakout_high=True, above_vwap=True, rvol=2.0, momentum=1.0)
        sig = evaluate("AAPL", tech, 8.0, 2.0, _cfg())
        assert sig is not None
        assert sig["direction"] == "long"
        assert sig["signal_strength"] in ("strong", "moderate")

    def test_short_signal_generated(self):
        tech = _tech(breakdown_low=True, above_vwap=False, rvol=2.0, momentum=-1.0)
        sig = evaluate("AAPL", tech, 2.0, -2.0, _cfg())
        assert sig is not None
        assert sig["direction"] == "short"

    def test_no_signal_when_no_structure_break(self):
        tech = _tech(breakout_high=False, breakdown_low=False)
        assert evaluate("AAPL", tech, 8.0, 2.0, _cfg()) is None

    def test_no_signal_when_neutral_sentiment(self):
        tech = _tech(breakout_high=True, above_vwap=True)
        # Score 5 is neutral with min=7 (bearish_threshold=3, bullish=7, neutral is 4-6)
        assert evaluate("AAPL", tech, 5.0, 0.0, _cfg()) is None

    def test_no_signal_when_no_sentiment(self):
        tech = _tech(breakout_high=True, above_vwap=True)
        assert evaluate("AAPL", tech, None, None, _cfg()) is None

    def test_no_signal_empty_technical(self):
        assert evaluate("AAPL", {}, 8.0, 2.0, _cfg()) is None

    def test_long_blocked_below_vwap(self):
        tech = _tech(breakout_high=True, above_vwap=False)
        assert evaluate("AAPL", tech, 8.0, 2.0, _cfg()) is None

    def test_short_blocked_above_vwap(self):
        tech = _tech(breakdown_low=True, above_vwap=True)
        assert evaluate("AAPL", tech, 2.0, -2.0, _cfg()) is None

    def test_weak_signal_returns_none(self):
        tech = _tech(breakout_high=True, above_vwap=True, rvol=0.5, momentum=0.1)
        sig = evaluate("AAPL", tech, 7.0, 0.0, _cfg())
        assert sig is None  # weak signal blocked

    def test_signal_contains_expected_fields(self):
        tech = _tech(breakout_high=True, above_vwap=True, rvol=2.0, momentum=1.0)
        sig = evaluate("AAPL", tech, 8.0, 2.0, _cfg())
        assert sig is not None
        for field in ("ticker", "direction", "close", "sentiment_score",
                      "signal_strength", "relative_volume", "momentum"):
            assert field in sig
