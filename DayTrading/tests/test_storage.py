"""Tests for storage.py using a temporary database."""

import pytest
from datetime import datetime, timezone, timedelta
from storage import Storage


@pytest.fixture
def db(tmp_path):
    return Storage(str(tmp_path / "test.db"))


_SIGNAL = {
    "ticker": "AAPL", "direction": "long", "close": 150.0,
    "sentiment_score": 8.0, "sentiment_delta": 2.0,
    "near_gap": False, "signal_strength": "strong",
}


class TestBars:
    def test_save_bar(self, db):
        db.save_bar("AAPL", "2026-03-28T10:00:00Z", "1min", 149, 150, 148, 150, 1000, 149.5)
        # No exception means success

    def test_bar_upsert_on_same_key(self, db):
        db.save_bar("AAPL", "2026-03-28T10:00:00Z", "1min", 149, 150, 148, 150, 1000)
        db.save_bar("AAPL", "2026-03-28T10:00:00Z", "1min", 149, 151, 148, 151, 2000)
        with db._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]
        assert count == 1


class TestNewsEvents:
    def test_save_news_event(self, db):
        db.save_news_event("AAPL", "Apple beats earnings", 8, 9, "earnings")
        with db._connect() as conn:
            rows = conn.execute("SELECT * FROM news_events").fetchall()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["sentiment_score"] == 8

    def test_get_recent_news(self, db):
        db.save_news_event("AAPL", "headline 1", 8, 9, "earnings")
        news = db.get_recent_news("AAPL", minutes=30)
        assert len(news) == 1


class TestSignals:
    def test_save_signal(self, db):
        db.save_signal(_SIGNAL)
        with db._connect() as conn:
            rows = conn.execute("SELECT * FROM signals").fetchall()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["direction"] == "long"


class TestTrades:
    def test_open_trade(self, db):
        trade_id = db.open_trade("AAPL", "long", 150.0, 148.0, 154.0, 10)
        assert trade_id is not None
        trades = db.get_open_trades()
        assert len(trades) == 1
        assert trades[0]["ticker"] == "AAPL"
        assert trades[0]["status"] == "open"

    def test_close_trade(self, db):
        trade_id = db.open_trade("AAPL", "long", 150.0, 148.0, 154.0, 10)
        db.close_trade(trade_id, 154.0, 40.0)
        assert db.get_open_trades() == []

    def test_get_daily_pnl_empty(self, db):
        assert db.get_daily_pnl() == 0.0

    def test_get_daily_pnl_closed_today(self, db):
        trade_id = db.open_trade("AAPL", "long", 150.0, 148.0, 154.0, 10)
        db.close_trade(trade_id, 154.0, 40.0)
        assert db.get_daily_pnl() == pytest.approx(40.0, abs=0.01)

    def test_get_daily_pnl_excludes_open_trades(self, db):
        db.open_trade("AAPL", "long", 150.0, 148.0, 154.0, 10)
        assert db.get_daily_pnl() == 0.0

    def test_multiple_closed_trades_summed(self, db):
        t1 = db.open_trade("AAPL", "long", 150.0, 148.0, 154.0, 10)
        t2 = db.open_trade("MSFT", "long", 200.0, 198.0, 204.0, 5)
        db.close_trade(t1, 154.0, 40.0)
        db.close_trade(t2, 198.0, -10.0)
        assert db.get_daily_pnl() == pytest.approx(30.0, abs=0.01)


class TestPruneBars:
    def test_prune_removes_old_bars(self, db):
        # Insert a "old" bar with timestamp in the past
        old_ts = "2020-01-01T10:00:00Z"
        db.save_bar("AAPL", old_ts, "1min", 100, 101, 99, 100, 1000)
        db.prune_bars(keep_days=5)
        with db._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]
        assert count == 0

    def test_prune_keeps_recent_bars(self, db):
        recent_ts = datetime.now(timezone.utc).isoformat()
        db.save_bar("AAPL", recent_ts, "1min", 100, 101, 99, 100, 1000)
        db.prune_bars(keep_days=5)
        with db._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]
        assert count == 1
