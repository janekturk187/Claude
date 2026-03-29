"""Tests for data/news_stream.py — no real websocket connections."""

import json
import pytest
from unittest.mock import MagicMock, patch

from data.news_stream import NewsStream


def _stream(tickers=None, callback=None):
    cb = callback or MagicMock()
    return NewsStream("api-key", tickers or ["AAPL", "MSFT"], on_headline=cb), cb


class TestOnMessage:
    def test_valid_news_event_is_queued(self):
        stream, _ = _stream()
        msg = json.dumps([{"ev": "N", "title": "AAPL earnings beat", "tickers": ["AAPL"]}])
        stream._on_message(None, msg)
        assert not stream._queue.empty()
        ticker, headline = stream._queue.get_nowait()
        assert ticker == "AAPL"
        assert headline == "AAPL earnings beat"

    def test_json_decode_error_is_logged_not_raised(self):
        stream, _ = _stream()
        stream._on_message(None, "{{not valid json")
        assert stream._queue.empty()

    def test_ticker_not_in_watchlist_is_ignored(self):
        stream, _ = _stream(tickers=["AAPL"])
        msg = json.dumps([{"ev": "N", "title": "TSLA news", "tickers": ["TSLA"]}])
        stream._on_message(None, msg)
        assert stream._queue.empty()

    def test_auth_success_sends_subscribe(self):
        stream, _ = _stream()
        ws = MagicMock()
        stream._on_message(ws, json.dumps([{"ev": "auth_success"}]))
        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["action"] == "subscribe"

    def test_multiple_watched_tickers_in_one_article_queues_each(self):
        stream, _ = _stream(tickers=["AAPL", "MSFT"])
        msg = json.dumps([{"ev": "N", "title": "Big tech news", "tickers": ["AAPL", "MSFT", "GOOG"]}])
        stream._on_message(None, msg)
        assert stream._queue.qsize() == 2

    def test_ticker_matching_is_case_insensitive(self):
        stream, _ = _stream(tickers=["AAPL"])
        msg = json.dumps([{"ev": "N", "title": "Apple news", "tickers": ["aapl"]}])
        stream._on_message(None, msg)
        assert not stream._queue.empty()


class TestProcessQueue:
    def test_callback_fired_for_queued_item(self):
        cb = MagicMock()
        stream, _ = _stream(callback=cb)
        stream._queue.put(("AAPL", "big earnings beat"))
        stream._stop.set()
        stream._process_queue()
        cb.assert_called_once_with("AAPL", "big earnings beat")

    def test_callback_exception_does_not_crash_worker(self):
        cb = MagicMock(side_effect=RuntimeError("boom"))
        stream, _ = _stream(callback=cb)
        stream._queue.put(("AAPL", "headline"))
        stream._stop.set()
        stream._process_queue()  # must not raise
        cb.assert_called_once()

    def test_multiple_items_all_processed(self):
        cb = MagicMock()
        stream, _ = _stream(callback=cb)
        for i in range(3):
            stream._queue.put(("AAPL", f"headline {i}"))
        stream._stop.set()
        stream._process_queue()
        assert cb.call_count == 3

    def test_queue_is_empty_after_processing(self):
        cb = MagicMock()
        stream, _ = _stream(callback=cb)
        stream._queue.put(("AAPL", "headline"))
        stream._stop.set()
        stream._process_queue()
        assert stream._queue.empty()


class TestNewsStreamLifecycle:
    @patch("data.news_stream.websocket.WebSocketApp")
    def test_start_launches_worker_and_websocket_threads(self, _mock_ws):
        stream, _ = _stream()
        stream._run_with_reconnect = MagicMock()  # prevent actual WS loop
        stream.start()
        assert stream._worker is not None
        assert stream._worker.is_alive()
        stream._stop.set()

    def test_stop_sets_stop_event(self):
        stream, _ = _stream()
        stream._ws = MagicMock()
        stream.stop()
        assert stream._stop.is_set()
