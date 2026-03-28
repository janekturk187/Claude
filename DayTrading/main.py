"""
main.py — Day Trading System entry point.

Wires together:
  - Alpaca price stream (websocket bar feed)
  - Polygon news stream (websocket headlines)
  - Claude sentiment classifier
  - Technical analyzer
  - Confluence signal filter
  - Risk gate
  - Order manager

Usage:
    ANTHROPIC_API_KEY=<key> python main.py
"""

import logging
import signal
import sys
import threading
import time

from loadconfig import load_config
from storage import Storage
from data.price_stream import PriceStream
from data.news_stream import NewsStream
from analysis import technical as tech
from analysis.sentiment import classify_headline, SessionSentiment
from signal.confluence import evaluate as evaluate_signal
from execution.risk_gate import check as risk_check
from execution.order_manager import OrderManager

logger = logging.getLogger(__name__)

# Monotonic timestamp of the last headline received per ticker
_last_news_time: dict[str, float] = {}


def run():
    cfg = load_config("config.json")

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    db = Storage(cfg.db_path)
    db.prune_bars()
    session_sentiment = SessionSentiment(window=cfg.signal.session_sentiment_window)
    order_manager = OrderManager(cfg)

    # --- News handler ---
    def on_headline(ticker: str, headline: str):
        _last_news_time[ticker] = time.monotonic()
        result = classify_headline(ticker, headline, cfg.claude)
        if result is None:
            return
        score = result.get("sentiment_score", 5)
        confidence = result.get("confidence", 5)
        if confidence < cfg.signal.min_confidence:
            logger.debug("%s: low confidence (%d) — skipping sentiment update", ticker, confidence)
            return
        session_sentiment.add(ticker, score, confidence)
        db.save_news_event(ticker, headline, score, confidence, result.get("event_type", "other"))
        logger.info(
            "News | %s sentiment=%d confidence=%d type=%s | %s",
            ticker, score, confidence, result.get("event_type", "?"), headline[:80],
        )

    # --- Price bar handler ---
    def on_bar(bar: dict):
        ticker = bar["ticker"]

        # Persist bar
        db.save_bar(
            ticker, bar["timestamp"], bar["resolution"],
            bar["open"], bar["high"], bar["low"], bar["close"],
            bar["volume"], bar.get("vwap"),
        )

        # Get recent bars for technical analysis
        # price_stream is bound by the time on_bar is first called (after start())
        if price_stream is None:
            return
        recent_bars = price_stream.aggregator.get_bars(ticker, n=30)
        if len(recent_bars) < 10:
            return  # not enough data yet

        technical = tech.analyze(recent_bars)
        sentiment_score = session_sentiment.score(ticker)
        sentiment_delta = session_sentiment.delta(ticker)

        sig = evaluate_signal(ticker, technical, sentiment_score, sentiment_delta, cfg.signal)
        if sig is None:
            return

        db.save_signal(sig)

        allowed, reason = risk_check(sig, db, cfg, _last_news_time,
                                     alpaca_client=order_manager.client)
        if not allowed:
            logger.info("Signal blocked by risk gate for %s: %s", ticker, reason)
            return

        order_manager.submit(sig, db)

    # --- Start streams ---
    # price_stream is declared before start() so on_bar's guard check is never None
    price_stream = None
    news_stream = NewsStream(cfg.polygon.api_key, cfg.tickers, on_headline=on_headline)
    price_stream = PriceStream(cfg.alpaca.api_key, cfg.alpaca.secret_key,
                               cfg.tickers, on_bar=on_bar)

    news_stream.start()

    # Price stream runs blocking — start in background thread
    price_thread = threading.Thread(target=price_stream.start, daemon=True)
    price_thread.start()

    def shutdown(signum, frame):
        logger.info("Shutting down — cancelling open orders...")
        order_manager.cancel_all_open()
        news_stream.stop()
        price_stream.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Day trading system running. Watching: %s", cfg.tickers)

    # Keep main thread alive
    while True:
        time.sleep(60)
        logger.debug("Heartbeat — session running")


if __name__ == "__main__":
    run()
