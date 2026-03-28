"""
price_stream.py — Alpaca websocket price stream.

Subscribes to real-time trades and quotes for the watchlist.
Aggregates ticks into 1-minute and 5-minute OHLCV bars in memory,
persists completed bars to SQLite, and notifies the signal engine
on each bar close.
"""

import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Callable, Optional

from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar

logger = logging.getLogger(__name__)

_MAX_BARS = 390  # one full trading day at 1-min resolution


class BarAggregator:
    """Aggregates a stream of 1-minute bars into higher resolutions in memory."""

    def __init__(self):
        # {ticker: deque(maxlen=390)} — O(1) append and auto-eviction
        self._bars: dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX_BARS))
        self._lock = threading.Lock()

    def add(self, ticker: str, bar: dict):
        """Add a completed 1-minute bar."""
        with self._lock:
            self._bars[ticker].append(bar)

    def get_bars(self, ticker: str, n: int = 20) -> list:
        with self._lock:
            bars = self._bars[ticker]
            return list(bars)[-n:] if len(bars) >= n else list(bars)

    def build_5min_bar(self, ticker: str) -> Optional[dict]:
        """Aggregate the last 5 one-minute bars into a single 5-minute bar."""
        with self._lock:
            recent = list(self._bars[ticker])[-5:]
        if len(recent) < 5:
            return None
        return {
            "ticker": ticker,
            "open":   recent[0]["open"],
            "high":   max(b["high"] for b in recent),
            "low":    min(b["low"] for b in recent),
            "close":  recent[-1]["close"],
            "volume": sum(b["volume"] for b in recent),
            "vwap":   recent[-1].get("vwap"),
            "timestamp": recent[-1]["timestamp"],
            "resolution": "5min",
        }


class PriceStream:
    """
    Wraps the Alpaca websocket stream. On each bar close it calls
    the registered on_bar callback with a normalized bar dict.
    """

    def __init__(self, api_key: str, secret_key: str, tickers: list,
                 on_bar: Callable[[dict], None]):
        self._tickers = tickers
        self._on_bar = on_bar
        self._stream = StockDataStream(api_key, secret_key)
        self.aggregator = BarAggregator()

    def _handle_bar(self, bar: Bar):
        normalized = {
            "ticker":     bar.symbol,
            "timestamp":  bar.timestamp.isoformat(),
            "resolution": "1min",
            "open":       float(bar.open),
            "high":       float(bar.high),
            "low":        float(bar.low),
            "close":      float(bar.close),
            "volume":     int(bar.volume),
            "vwap":       float(bar.vwap) if bar.vwap else None,
        }
        self.aggregator.add(bar.symbol, normalized)

        try:
            self._on_bar(normalized)
        except Exception as e:
            logger.warning("on_bar callback error for %s: %s", bar.symbol, e)

    def start(self):
        logger.info("Subscribing to bars for: %s", self._tickers)
        self._stream.subscribe_bars(self._handle_bar, *self._tickers)
        # Runs blocking — call from a background thread
        self._stream.run()

    def stop(self):
        self._stream.stop()
