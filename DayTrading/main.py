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
import os
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
from signals.confluence import evaluate as evaluate_signal
from execution.risk_gate import check as risk_check
from execution.order_manager import OrderManager
from reports import session_report, plots
from backtest import engine as bt_engine, metrics as bt_metrics, report as bt_report
from data import historical

logger = logging.getLogger(__name__)

_PID_FILE = "trading.pid"


def _write_pid():
    with open(_PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _remove_pid():
    try:
        os.remove(_PID_FILE)
    except FileNotFoundError:
        pass


# Monotonic timestamp of the last headline received per ticker
_last_news_time: dict[str, float] = {}

# Monotonic timestamp of the last bar received per ticker — used for health checks
_last_bar_time: dict[str, float] = {}
_STALE_BAR_SECONDS = 5 * 60  # warn if no bar in 5 minutes


def _check_stream_health(tickers: list) -> None:
    """Warn if any watched ticker has gone stale mid-session."""
    threshold = time.monotonic() - _STALE_BAR_SECONDS
    for ticker in tickers:
        last = _last_bar_time.get(ticker)
        if last is not None and last < threshold:
            logger.warning(
                "HEALTH: %s — no bar received in >%dm, price stream may be stale",
                ticker, _STALE_BAR_SECONDS // 60,
            )


def run():
    import argparse
    parser = argparse.ArgumentParser(description="Day Trading System")
    parser.add_argument("--paper", action="store_true",
                        help="Force paper trading mode (overrides config)")
    parser.add_argument("--report", action="store_true",
                        help="Generate session report for today and exit")
    parser.add_argument("--plot", action="store_true",
                        help="Generate session review plots for today and exit")
    parser.add_argument("--backtest", action="store_true",
                        help="Run backtest on historical data and exit")
    parser.add_argument("--start", default=None,
                        help="Backtest start date YYYY-MM-DD (required with --backtest)")
    parser.add_argument("--end", default=None,
                        help="Backtest end date YYYY-MM-DD (required with --backtest)")
    parser.add_argument("--sentiment", type=float, default=None,
                        help="Fixed sentiment score for backtest (default: min_sentiment_score)")
    parser.add_argument("--equity", type=float, default=100_000.0,
                        help="Starting equity for backtest position sizing (default: 100000)")
    args = parser.parse_args()

    cfg = load_config("config.json")

    if args.paper:
        cfg.alpaca.paper = True

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    if cfg.alpaca.paper:
        logger.warning("=" * 60)
        logger.warning("PAPER TRADING MODE — no real orders will be placed")
        logger.warning("=" * 60)
    else:
        logger.warning("=" * 60)
        logger.warning("LIVE TRADING MODE — real orders WILL be placed")
        logger.warning("=" * 60)

    db = Storage(cfg.db_path)

    if args.report:
        path = session_report.generate(db, cfg.tickers, cfg.reports_dir, paper=cfg.alpaca.paper)
        logger.info("Session report: %s", path)
        return

    if args.plot:
        saved = plots.generate(db, cfg.tickers, cfg.reports_dir, paper=cfg.alpaca.paper)
        logger.info("Plots generated: %d file(s)", len(saved))
        for p in saved:
            logger.info("  %s", p)
        return

    if args.backtest:
        if not args.start or not args.end:
            logger.error("--backtest requires --start YYYY-MM-DD and --end YYYY-MM-DD")
            return
        from datetime import datetime, timezone as tz
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=tz.utc)
        end_dt   = datetime.strptime(args.end,   "%Y-%m-%d").replace(tzinfo=tz.utc)
        logger.info("Running backtest %s → %s for: %s", args.start, args.end, cfg.tickers)
        bars_by_ticker = {}
        for ticker in cfg.tickers:
            bars_by_ticker[ticker] = historical.fetch_bars(
                ticker, cfg.alpaca.api_key, cfg.alpaca.secret_key, start_dt, end_dt
            )
        trades  = bt_engine.run(bars_by_ticker, cfg,
                                sentiment_score=args.sentiment,
                                starting_equity=args.equity)
        m       = bt_metrics.calculate(trades)
        path    = bt_report.generate(m, trades, cfg.tickers, cfg.reports_dir,
                                     args.start, args.end,
                                     args.sentiment or cfg.signal.min_sentiment_score,
                                     args.equity)
        logger.info("Backtest complete — %d trade(s), P&L: $%+.2f", m["total_trades"], m["total_pnl"])
        logger.info("Backtest report: %s", path)
        return
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
        _last_bar_time[ticker] = time.monotonic()

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

    _write_pid()

    def shutdown(signum, frame):
        logger.info("Shutting down — cancelling open orders...")
        order_manager.cancel_all_open()
        news_stream.stop()
        price_stream.stop()
        try:
            path = session_report.generate(db, cfg.tickers, cfg.reports_dir, paper=cfg.alpaca.paper)
            logger.info("Session report: %s", path)
        except Exception as e:
            logger.error("Failed to generate session report: %s", e)
        try:
            saved = plots.generate(db, cfg.tickers, cfg.reports_dir, paper=cfg.alpaca.paper)
            logger.info("Plots generated: %d file(s)", len(saved))
        except Exception as e:
            logger.error("Failed to generate plots: %s", e)
        _remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Day trading system running. Watching: %s", cfg.tickers)

    # Keep main thread alive — check stream health each minute
    while True:
        time.sleep(60)
        logger.debug("Heartbeat — session running")
        _check_stream_health(cfg.tickers)


if __name__ == "__main__":
    run()
