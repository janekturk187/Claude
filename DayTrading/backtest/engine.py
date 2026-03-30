"""
engine.py — backtesting engine.

Replays historical bars through the existing technical analysis and
confluence signal pipeline to simulate trade performance.

Assumptions:
- Entry fills at the calculated limit price (close * 1.001 for longs) on the bar
  after the signal fires. This is a simplification; real limit fills depend on
  whether the next bar's range includes the entry price.
- Exit triggers are checked bar-by-bar against high/low:
    stop triggered if bar.low <= stop (long) or bar.high >= stop (short)
    target triggered if bar.high >= target (long) or bar.low <= target (short)
    stop checked before target (conservative — stop wins on same bar)
- One open position per ticker at a time; no cross-ticker position cap.
- Sentiment is fixed (no real-time news). Pass a score >= min_sentiment_score
  to allow long signals; pass <= (10 - min_sentiment_score) for shorts.
  The default (min_sentiment_score) enables both directions at minimum confidence.
"""

import logging
from collections import deque
from typing import Optional

from analysis import technical as tech
from signals.confluence import evaluate as evaluate_signal

logger = logging.getLogger(__name__)

_WARMUP_BARS = 10  # minimum bars before signal evaluation begins


def run(
    bars_by_ticker: dict,
    cfg,
    sentiment_score: Optional[float] = None,
    starting_equity: float = 100_000.0,
) -> list:
    """
    Replay bars for all tickers and return a list of simulated trades.

    Args:
        bars_by_ticker: {ticker: [bar_dict, ...]} oldest-first
        cfg: full Config object (uses cfg.signal, cfg.risk)
        sentiment_score: fixed sentiment score for all bars. Defaults to
                         cfg.signal.min_sentiment_score.
        starting_equity: account equity used for position sizing.
    """
    if sentiment_score is None:
        sentiment_score = float(cfg.signal.min_sentiment_score)

    all_trades = []
    for ticker, bars in bars_by_ticker.items():
        if not bars:
            logger.warning("No bars for %s — skipping", ticker)
            continue
        trades = _run_ticker(ticker, bars, cfg, sentiment_score, starting_equity)
        logger.info("%s: %d signal(s) → %d trade(s)", ticker, len(trades), len(trades))
        all_trades.extend(trades)

    return all_trades


def _run_ticker(ticker: str, bars: list, cfg, sentiment_score: float,
                equity: float) -> list:
    trades = []
    open_position = None
    window: deque = deque(maxlen=30)

    for i, bar in enumerate(bars):
        # Check open position against this bar before evaluating new signals
        if open_position is not None:
            result = _check_exit(open_position, bar)
            if result is not None:
                trades.append(result)
                open_position = None
            else:
                window.append(bar)
                continue  # still in trade — skip signal evaluation

        window.append(bar)

        if len(window) < _WARMUP_BARS:
            continue

        technical = tech.analyze(list(window))
        sig = evaluate_signal(ticker, technical, sentiment_score, None, cfg.signal)
        if sig is None:
            continue

        entry, stop, target, risk = _calc_prices(sig, cfg.risk.reward_risk_ratio)
        if risk <= 0:
            logger.debug("%s: invalid risk at bar %d — skip", ticker, i)
            continue

        qty = _position_size(entry, stop, equity, cfg.risk.max_position_pct)
        if qty <= 0:
            continue

        open_position = {
            "ticker":         ticker,
            "direction":      sig["direction"],
            "entry_price":    entry,
            "stop_price":     stop,
            "target_price":   target,
            "qty":            qty,
            "signal_strength": sig.get("signal_strength"),
            "signal_bar_ts":  bar.get("timestamp"),
        }
        logger.debug("%s: signal %s at bar %d entry=%.2f stop=%.2f target=%.2f",
                     ticker, sig["direction"], i, entry, stop, target)

    # Force-close any position still open at end of data
    if open_position is not None and bars:
        exit_price = bars[-1]["close"]
        direction = open_position["direction"]
        if direction == "long":
            pnl = (exit_price - open_position["entry_price"]) * open_position["qty"]
        else:
            pnl = (open_position["entry_price"] - exit_price) * open_position["qty"]
        trades.append({
            **open_position,
            "exit_price":  exit_price,
            "pnl":         round(pnl, 2),
            "exit_reason": "eod",
        })

    return trades


def _check_exit(position: dict, bar: dict) -> Optional[dict]:
    """Return a completed trade dict if the bar triggers stop or target, else None."""
    direction = position["direction"]
    stop      = position["stop_price"]
    target    = position["target_price"]
    entry     = position["entry_price"]
    qty       = position["qty"]

    if direction == "long":
        if bar["low"] <= stop:
            pnl = round((stop - entry) * qty, 2)
            return {**position, "exit_price": stop,   "pnl": pnl, "exit_reason": "stop"}
        if bar["high"] >= target:
            pnl = round((target - entry) * qty, 2)
            return {**position, "exit_price": target, "pnl": pnl, "exit_reason": "target"}
    else:  # short
        if bar["high"] >= stop:
            pnl = round((entry - stop) * qty, 2)
            return {**position, "exit_price": stop,   "pnl": pnl, "exit_reason": "stop"}
        if bar["low"] <= target:
            pnl = round((entry - target) * qty, 2)
            return {**position, "exit_price": target, "pnl": pnl, "exit_reason": "target"}

    return None


def _calc_prices(signal: dict, rr_ratio: float) -> tuple:
    """Return (entry, stop, target, risk) from a signal dict."""
    close     = signal["close"]
    direction = signal["direction"]

    if direction == "long":
        entry  = round(close * 1.001, 2)
        stop   = signal.get("breakout_bar_low") or round(close * 0.99, 2)
        risk   = entry - stop
        target = round(entry + risk * rr_ratio, 2)
    else:
        entry  = round(close * 0.999, 2)
        stop   = signal.get("local_high") or round(close * 1.01, 2)
        risk   = stop - entry
        target = round(entry - risk * rr_ratio, 2)

    return entry, stop, target, risk


def _position_size(entry: float, stop: float, equity: float,
                   max_position_pct: float) -> float:
    risk_per_share = abs(entry - stop)
    if risk_per_share == 0:
        return 0
    risk_amount = equity * max_position_pct
    return round(risk_amount / risk_per_share, 2)
