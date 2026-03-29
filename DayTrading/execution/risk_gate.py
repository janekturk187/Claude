"""
risk_gate.py — hard rules that block trade execution regardless of signal quality.

check() returns (True, None) if the trade is allowed, or (False, reason) if blocked.
All rules are enforced before any order is submitted.
"""

import logging
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _market_time(tz_name: str) -> dtime:
    return datetime.now(ZoneInfo(tz_name)).time()


def check(signal: dict, db, cfg, last_news_time: dict,
          alpaca_client=None) -> tuple[bool, str | None]:
    """
    Run all risk gate checks for a prospective trade.

    Args:
        signal:          The signal dict from confluence.evaluate()
        db:              Storage instance for live P&L and position queries
        cfg:             Full Config (risk and trading_hours sub-configs used)
        last_news_time:  {ticker: monotonic_timestamp} of most recent headline per ticker

    Returns:
        (allowed: bool, reason: str | None)
    """
    ticker = signal["ticker"]
    tz = cfg.trading_hours.timezone

    # 1. Trading hours check
    now = _market_time(tz)
    start   = dtime.fromisoformat(cfg.trading_hours.start)
    pause_s = dtime.fromisoformat(cfg.trading_hours.midday_pause_start)
    pause_e = dtime.fromisoformat(cfg.trading_hours.midday_pause_end)
    end     = dtime.fromisoformat(cfg.trading_hours.end)

    if now < start or now > end:
        return False, f"outside trading hours ({now.strftime('%H:%M')})"
    if pause_s <= now < pause_e:
        return False, f"midday pause ({now.strftime('%H:%M')})"

    # 2. Daily loss limit — includes unrealized losses on open positions
    daily_pnl = db.get_daily_pnl()
    account_equity = _get_account_equity(alpaca_client) if alpaca_client else None
    unrealized_pnl = _get_unrealized_pnl(alpaca_client) if alpaca_client else 0.0
    total_pnl = daily_pnl + unrealized_pnl
    if account_equity and total_pnl < -(account_equity * cfg.risk.max_daily_loss_pct):
        return False, f"daily loss limit hit (P&L: ${total_pnl:.2f})"

    # 3. Max concurrent positions
    open_trades = db.get_open_trades()
    if len(open_trades) >= cfg.risk.max_open_positions:
        return False, f"max open positions ({cfg.risk.max_open_positions}) reached"

    # 4. Already in a position for this ticker
    open_tickers = {t["ticker"] for t in open_trades}
    if ticker in open_tickers:
        return False, f"already in a position for {ticker}"

    # 5. News blackout — don't enter within N minutes of a fresh headline
    last = last_news_time.get(ticker)
    if last is not None:
        age_seconds = time.monotonic() - last
        blackout = cfg.risk.news_blackout_minutes * 60
        if age_seconds < blackout:
            remaining = int((blackout - age_seconds) / 60)
            return False, f"news blackout active for {ticker} ({remaining}m remaining)"

    return True, None


def _get_account_equity(alpaca_client) -> float | None:
    """Fetch current account equity from an existing Alpaca client."""
    try:
        return float(alpaca_client.get_account().equity)
    except Exception as e:
        logger.warning("Could not fetch account equity: %s", e)
        return None


def _get_unrealized_pnl(alpaca_client) -> float:
    """Sum unrealized P&L across all open positions."""
    try:
        positions = alpaca_client.get_all_positions()
        return sum(float(p.unrealized_pl) for p in positions)
    except Exception as e:
        logger.warning("Could not fetch unrealized P&L: %s", e)
        return 0.0
