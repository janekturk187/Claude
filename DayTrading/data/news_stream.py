"""
news_stream.py — Polygon.io real-time news websocket.

Connects to Polygon's news feed, filters headlines that mention
watched tickers, and fires the on_headline callback with each match.
"""

import json
import logging
import threading
import time
from typing import Callable

import websocket

logger = logging.getLogger(__name__)

_POLYGON_NEWS_URL = "wss://delayed.polygon.io/stocks"


class NewsStream:
    """
    Subscribes to Polygon.io's websocket news feed.
    Calls on_headline(ticker, headline) for each relevant article.
    """

    def __init__(self, api_key: str, tickers: list,
                 on_headline: Callable[[str, str], None]):
        self._api_key = api_key
        self._tickers = [t.upper() for t in tickers]
        self._on_headline = on_headline
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _on_open(self, ws):
        logger.info("Polygon news websocket connected")
        ws.send(json.dumps({"action": "auth", "params": self._api_key}))

    def _on_message(self, ws, message: str):
        try:
            events = json.loads(message)
        except json.JSONDecodeError:
            return

        for event in events:
            ev_type = event.get("ev")

            if ev_type == "auth_success":
                logger.info("Polygon auth successful — subscribing to news")
                ws.send(json.dumps({"action": "subscribe", "params": "N.*"}))

            elif ev_type == "N":
                self._handle_news(event)

    def _handle_news(self, event: dict):
        headline = event.get("title", "")
        tickers_in_article = [t.upper() for t in event.get("tickers", [])]

        for ticker in self._tickers:
            if ticker in tickers_in_article:
                logger.debug("News hit for %s: %s", ticker, headline[:80])
                try:
                    self._on_headline(ticker, headline)
                except Exception as e:
                    logger.warning("on_headline callback error for %s: %s", ticker, e)

    def _on_error(self, ws, error):
        logger.error("Polygon websocket error: %s", error)

    def _on_close(self, ws, code, msg):
        logger.warning("Polygon websocket closed (code=%s) — will reconnect", code)
        if not self._stop.is_set():
            time.sleep(5)
            self.start()

    def start(self):
        self._stop.clear()
        self._ws = websocket.WebSocketApp(
            _POLYGON_NEWS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever, daemon=True
        )
        self._thread.start()
        logger.info("News stream started")

    def stop(self):
        self._stop.set()
        if self._ws:
            self._ws.close()
