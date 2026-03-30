"""Tests for reports/plots.py — data-prep functions only (no matplotlib required)."""

from datetime import datetime, timezone
import pytest

from reports.plots import prep_ticker_data, build_pnl_curve, build_summary


def _bar(ts="2024-01-15T10:00:00+00:00", close=150.0, vwap=149.5):
    return {"timestamp": ts, "open": 149.0, "high": 151.0,
            "low": 148.5, "close": close, "volume": 10000, "vwap": vwap}


def _signal(ticker="AAPL", direction="long", price=150.0,
            ts="2024-01-15T10:05:00+00:00"):
    return {"ticker": ticker, "direction": direction, "close": price,
            "generated_at": ts, "signal_strength": "strong"}


def _trade(ticker="AAPL", direction="long", entry=150.0, exit_=155.0,
           pnl=50.0, status="closed",
           opened="2024-01-15T10:06:00+00:00",
           closed="2024-01-15T10:45:00+00:00"):
    return {"ticker": ticker, "direction": direction,
            "entry_price": entry, "exit_price": exit_,
            "pnl": pnl, "status": status,
            "opened_at": opened, "closed_at": closed}


def _news(ticker="AAPL", sentiment=8, ts="2024-01-15T09:00:00+00:00"):
    return {"ticker": ticker, "headline": "Big news", "sentiment_score": sentiment,
            "confidence": 9, "event_type": "earnings", "received_at": ts}


class TestPrepTickerData:
    def test_bars_parsed_into_timestamps_and_closes(self):
        bars = [_bar("2024-01-15T10:00:00+00:00", 150.0),
                _bar("2024-01-15T10:01:00+00:00", 151.0)]
        data = prep_ticker_data("AAPL", bars, [], [], [])
        assert len(data["timestamps"]) == 2
        assert len(data["closes"]) == 2
        assert data["closes"][1] == 151.0

    def test_timestamps_are_datetime_objects(self):
        data = prep_ticker_data("AAPL", [_bar()], [], [], [])
        assert isinstance(data["timestamps"][0], datetime)

    def test_vwaps_extracted(self):
        data = prep_ticker_data("AAPL", [_bar(vwap=149.5)], [], [], [])
        assert data["vwaps"][0] == 149.5

    def test_none_vwap_preserved(self):
        bar = _bar()
        bar["vwap"] = None
        data = prep_ticker_data("AAPL", [bar], [], [], [])
        assert data["vwaps"][0] is None

    def test_long_signal_categorised_correctly(self):
        data = prep_ticker_data("AAPL", [], [_signal(direction="long")], [], [])
        assert len(data["long_signals"]) == 1
        assert len(data["short_signals"]) == 0

    def test_short_signal_categorised_correctly(self):
        data = prep_ticker_data("AAPL", [], [_signal(direction="short")], [], [])
        assert len(data["short_signals"]) == 1
        assert len(data["long_signals"]) == 0

    def test_signal_for_other_ticker_excluded(self):
        data = prep_ticker_data("AAPL", [], [_signal(ticker="MSFT")], [], [])
        assert len(data["long_signals"]) == 0
        assert len(data["short_signals"]) == 0

    def test_trade_entry_and_exit_captured(self):
        data = prep_ticker_data("AAPL", [], [], [_trade()], [])
        assert len(data["trade_entries"]) == 1
        assert len(data["trade_exits"]) == 1

    def test_open_trade_has_entry_but_no_exit(self):
        t = _trade(status="open", exit_=None, pnl=None, closed=None)
        data = prep_ticker_data("AAPL", [], [], [t], [])
        assert len(data["trade_entries"]) == 1
        assert len(data["trade_exits"]) == 0

    def test_trade_for_other_ticker_excluded(self):
        data = prep_ticker_data("AAPL", [], [], [_trade(ticker="MSFT")], [])
        assert len(data["trade_entries"]) == 0

    def test_winning_trade_exit_reason_is_target(self):
        data = prep_ticker_data("AAPL", [], [], [_trade(pnl=50.0)], [])
        _, _, reason = data["trade_exits"][0]
        assert reason == "target"

    def test_losing_trade_exit_reason_is_stop(self):
        data = prep_ticker_data("AAPL", [], [], [_trade(pnl=-20.0)], [])
        _, _, reason = data["trade_exits"][0]
        assert reason == "stop"

    def test_news_events_captured(self):
        data = prep_ticker_data("AAPL", [], [], [], [_news(sentiment=8)])
        assert len(data["news_events"]) == 1
        _, sentiment = data["news_events"][0]
        assert sentiment == 8

    def test_news_for_other_ticker_excluded(self):
        data = prep_ticker_data("AAPL", [], [], [], [_news(ticker="MSFT")])
        assert len(data["news_events"]) == 0

    def test_invalid_timestamp_skipped_gracefully(self):
        bar = _bar(ts="not-a-timestamp")
        data = prep_ticker_data("AAPL", [bar], [], [], [])
        assert len(data["timestamps"]) == 0

    def test_empty_inputs_return_empty_lists(self):
        data = prep_ticker_data("AAPL", [], [], [], [])
        assert data["timestamps"] == []
        assert data["closes"] == []
        assert data["long_signals"] == []


class TestBuildPnlCurve:
    def test_empty_trades_returns_empty(self):
        times, values = build_pnl_curve([])
        assert times == [] and values == []

    def test_open_trades_excluded(self):
        times, values = build_pnl_curve([_trade(status="open")])
        assert times == []

    def test_cumulative_pnl_accumulates(self):
        trades = [
            _trade(pnl=50.0,  closed="2024-01-15T10:30:00+00:00"),
            _trade(pnl=-20.0, closed="2024-01-15T11:00:00+00:00"),
            _trade(pnl=30.0,  closed="2024-01-15T11:30:00+00:00"),
        ]
        times, values = build_pnl_curve(trades)
        assert values == [50.0, 30.0, 60.0]

    def test_sorted_by_close_time(self):
        trades = [
            _trade(pnl=30.0, closed="2024-01-15T11:30:00+00:00"),
            _trade(pnl=50.0, closed="2024-01-15T10:30:00+00:00"),
        ]
        times, values = build_pnl_curve(trades)
        assert values[0] == 50.0  # earlier trade first
        assert values[1] == 80.0

    def test_timestamps_are_datetime_objects(self):
        times, _ = build_pnl_curve([_trade()])
        assert isinstance(times[0], datetime)


class TestBuildSummary:
    def test_returns_labels_and_values(self):
        labels, values = build_summary([_trade("AAPL", pnl=50.0)], ["AAPL"])
        assert "AAPL" in labels
        assert values[labels.index("AAPL")] == 50.0

    def test_tickers_not_traded_have_zero_pnl(self):
        labels, values = build_summary([], ["AAPL", "MSFT"])
        assert values[labels.index("AAPL")] == 0.0
        assert values[labels.index("MSFT")] == 0.0

    def test_multiple_trades_same_ticker_summed(self):
        trades = [_trade("AAPL", pnl=50.0), _trade("AAPL", pnl=-20.0)]
        labels, values = build_summary(trades, ["AAPL"])
        assert values[labels.index("AAPL")] == 30.0

    def test_trade_for_unlisted_ticker_ignored(self):
        trades = [_trade("GOOG", pnl=100.0)]
        labels, values = build_summary(trades, ["AAPL"])
        assert values[labels.index("AAPL")] == 0.0

    def test_preserves_ticker_order(self):
        tickers = ["AAPL", "MSFT", "NVDA"]
        labels, _ = build_summary([], tickers)
        assert labels == tickers
