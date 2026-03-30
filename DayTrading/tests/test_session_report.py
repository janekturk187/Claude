"""Tests for reports/session_report.py."""

import os
import tempfile
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from reports.session_report import generate


def _db(signals=None, trades=None, news=None):
    db = MagicMock()
    db.get_today_signals.return_value = signals or []
    db.get_today_trades.return_value = trades or []
    db.get_today_news_events.return_value = news or []
    return db


def _signal(ticker="AAPL", direction="long", strength="strong", sentiment=8.0, close=150.0):
    return {
        "ticker": ticker,
        "direction": direction,
        "signal_strength": strength,
        "sentiment_score": sentiment,
        "sentiment_delta": 0.5,
        "close": close,
        "generated_at": "2024-01-15T10:30:00+00:00",
    }


def _trade(ticker="AAPL", direction="long", entry=150.0, exit_=155.0,
           stop=148.0, target=156.0, qty=10, status="closed", pnl=50.0):
    return {
        "ticker": ticker,
        "direction": direction,
        "entry_price": entry,
        "exit_price": exit_,
        "stop_price": stop,
        "target_price": target,
        "qty": qty,
        "status": status,
        "pnl": pnl,
        "opened_at": "2024-01-15T10:31:00+00:00",
        "closed_at": "2024-01-15T11:00:00+00:00" if status == "closed" else None,
    }


def _news(ticker="AAPL", headline="Earnings beat estimates", sentiment=8, confidence=9):
    return {
        "ticker": ticker,
        "headline": headline,
        "sentiment_score": sentiment,
        "confidence": confidence,
        "event_type": "earnings",
        "received_at": "2024-01-15T09:00:00+00:00",
    }


class TestGenerate:
    def test_creates_file_in_output_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir)
            assert os.path.exists(path)

    def test_report_contains_date_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir)
            content = open(path).read()
            assert "Session Report" in content

    def test_paper_mode_label_in_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir, paper=True)
            content = open(path).read()
            assert "PAPER" in content

    def test_live_mode_label_in_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir, paper=False)
            content = open(path).read()
            assert "LIVE" in content

    def test_no_signals_shows_placeholder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir)
            assert "No signals generated today" in open(path).read()

    def test_signals_appear_in_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = _db(signals=[_signal("AAPL", "long", "strong")])
            path = generate(db, tickers=["AAPL"], output_dir=tmpdir)
            content = open(path).read()
            assert "AAPL" in content
            assert "long" in content
            assert "strong" in content

    def test_no_trades_shows_placeholder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir)
            assert "No trades placed today" in open(path).read()

    def test_trades_appear_in_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = _db(trades=[_trade("MSFT", pnl=75.0)])
            path = generate(db, tickers=["MSFT"], output_dir=tmpdir)
            content = open(path).read()
            assert "MSFT" in content
            assert "+75.00" in content

    def test_summary_win_rate_calculated(self):
        trades = [
            _trade(pnl=50.0, status="closed"),
            _trade(pnl=-20.0, status="closed"),
            _trade(pnl=30.0, status="closed"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            db = _db(trades=trades)
            path = generate(db, tickers=["AAPL"], output_dir=tmpdir)
            content = open(path).read()
            assert "67%" in content  # 2/3 winners

    def test_summary_total_pnl(self):
        trades = [_trade(pnl=50.0), _trade(pnl=-20.0)]
        with tempfile.TemporaryDirectory() as tmpdir:
            db = _db(trades=trades)
            path = generate(db, tickers=["AAPL"], output_dir=tmpdir)
            content = open(path).read()
            assert "+30.00" in content

    def test_open_trade_has_no_exit_price(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = _db(trades=[_trade(status="open", exit_=None, pnl=None)])
            path = generate(db, tickers=["AAPL"], output_dir=tmpdir)
            content = open(path).read()
            assert "open" in content

    def test_news_events_appear_in_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = _db(news=[_news("AAPL", "Earnings beat estimates")])
            path = generate(db, tickers=["AAPL"], output_dir=tmpdir)
            content = open(path).read()
            assert "Earnings beat estimates" in content

    def test_no_news_shows_placeholder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir)
            assert "No news events today" in open(path).read()

    def test_news_capped_at_20(self):
        news = [_news(headline=f"headline {i}") for i in range(25)]
        with tempfile.TemporaryDirectory() as tmpdir:
            db = _db(news=news)
            path = generate(db, tickers=["AAPL"], output_dir=tmpdir)
            content = open(path).read()
            assert "5 more events" in content

    def test_output_dir_created_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "nested", "reports")
            path = generate(_db(), tickers=["AAPL"], output_dir=new_dir)
            assert os.path.exists(path)

    def test_disclaimer_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate(_db(), tickers=["AAPL"], output_dir=tmpdir)
            assert "Not financial advice" in open(path).read()
