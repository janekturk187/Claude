"""Tests for SessionSentiment — no API calls required."""

import time
import pytest
from analysis.sentiment import SessionSentiment


class TestSessionSentiment:
    def test_score_single_event(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 8, 9)
        score = ss.score("AAPL")
        assert score == pytest.approx(8.0, abs=0.1)

    def test_score_weighted_by_confidence(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 3, 1)   # low confidence bearish
        ss.add("AAPL", 9, 10)  # high confidence bullish
        score = ss.score("AAPL")
        assert score > 7.0  # high confidence bullish should dominate

    def test_score_empty_returns_none(self):
        ss = SessionSentiment(window=5)
        assert ss.score("AAPL") is None

    def test_score_unknown_ticker_returns_none(self):
        ss = SessionSentiment(window=5)
        ss.add("MSFT", 8, 9)
        assert ss.score("AAPL") is None

    def test_window_limit_evicts_oldest(self):
        ss = SessionSentiment(window=3)
        ss.add("AAPL", 9, 10)  # will be evicted
        ss.add("AAPL", 5, 10)
        ss.add("AAPL", 5, 10)
        ss.add("AAPL", 5, 10)  # this evicts the 9
        score = ss.score("AAPL")
        assert score == pytest.approx(5.0, abs=0.5)

    def test_delta_positive_on_improving_sentiment(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 5, 8)
        ss.add("AAPL", 8, 8)
        assert ss.delta("AAPL") == pytest.approx(3.0, abs=0.01)

    def test_delta_negative_on_deteriorating_sentiment(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 8, 8)
        ss.add("AAPL", 3, 8)
        assert ss.delta("AAPL") == pytest.approx(-5.0, abs=0.01)

    def test_delta_none_with_single_event(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 7, 8)
        assert ss.delta("AAPL") is None

    def test_delta_none_when_empty(self):
        ss = SessionSentiment(window=5)
        assert ss.delta("AAPL") is None

    def test_reset_clears_ticker(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 8, 9)
        ss.reset("AAPL")
        assert ss.score("AAPL") is None

    def test_reset_all_clears_everything(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 8, 9)
        ss.add("MSFT", 6, 7)
        ss.reset_all()
        assert ss.score("AAPL") is None
        assert ss.score("MSFT") is None

    def test_independent_tickers(self):
        ss = SessionSentiment(window=5)
        ss.add("AAPL", 9, 10)
        ss.add("MSFT", 2, 10)
        assert ss.score("AAPL") > 7
        assert ss.score("MSFT") < 4
