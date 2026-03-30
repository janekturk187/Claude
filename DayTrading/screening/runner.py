"""
runner.py — pre-market screener entry point.

Usage (from DayTrading/):
    py -3 screening/runner.py

Builds a candidate universe from:
  1. Alpaca market movers (top gainers + losers by % change)
  2. Alpaca most-active stocks by volume
  3. Static universe in config.json (as a supplement)

Scores each ticker with the screener, optionally checks for a recent news
catalyst via the Polygon REST API, and writes watchlist.json.
"""

import json
import logging
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockSnapshotRequest,
    MarketMoversRequest,
    MostActivesRequest,
)

from loadconfig import load_config
from screening.screener import pick_tickers

logger = logging.getLogger(__name__)

WATCHLIST_FILE = "watchlist.json"

_NEWS_BOOST = 1.25  # 25% score boost for tickers with a recent headline


def run(cfg=None) -> list:
    """
    Run the screener. Returns the list of selected tickers (may be empty).
    If no tickers pass screening, watchlist.json is not written and the
    trading system falls back to config.json's watchlist.
    """
    if cfg is None:
        cfg = load_config("config.json")

    client = StockHistoricalDataClient(cfg.alpaca.api_key, cfg.alpaca.secret_key)

    # --- Build candidate universe ---
    universe = _build_universe(client, cfg)
    if not universe:
        logger.warning("Empty universe — screener aborted")
        return []

    logger.info("Screening %d tickers for today's watchlist...", len(universe))

    # --- Fetch snapshots for the full universe ---
    try:
        req = StockSnapshotRequest(symbol_or_symbols=list(universe))
        snapshots = client.get_stock_snapshot(req)
    except Exception as e:
        logger.error("Failed to fetch snapshots: %s — screener aborted", e)
        return []

    # --- Score and pick ---
    picks = pick_tickers(snapshots, cfg.screening)

    if not picks:
        logger.warning("No tickers passed screening — falling back to config watchlist")
        return []

    # --- News catalyst check: boost picks that have a recent headline ---
    if cfg.screening.news_catalyst_check:
        _apply_news_boost(picks, cfg.polygon.api_key)

        # Re-sort after boost — a pick with news may now outrank one without
        picks.sort(key=lambda x: x["score"], reverse=True)

    tickers = [p["ticker"] for p in picks]

    # Write watchlist.json — main.py reads this at startup
    watchlist = {
        "tickers":      tickers,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "picks":        picks,
    }
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f, indent=2)
    logger.info("watchlist.json written: %s", tickers)

    _write_report(picks, cfg)
    return tickers


def _build_universe(client: StockHistoricalDataClient, cfg) -> set:
    """
    Merge dynamic movers/actives with the static config universe.
    Returns a deduplicated set of ticker symbols.
    """
    universe = set()

    if cfg.screening.use_dynamic_universe:
        top = cfg.screening.dynamic_top

        # Market movers: top gainers and losers by percent change
        try:
            movers = client.get_market_movers(MarketMoversRequest(top=top))
            for m in (movers.gainers or []):
                universe.add(m.symbol)
            for m in (movers.losers or []):
                universe.add(m.symbol)
            logger.info("Market movers: %d gainers + %d losers",
                        len(movers.gainers or []), len(movers.losers or []))
        except Exception as e:
            logger.warning("Failed to fetch market movers: %s — continuing", e)

        # Most active by volume
        try:
            actives = client.get_most_actives(MostActivesRequest(top=top))
            for a in (actives.most_actives or []):
                universe.add(a.symbol)
            logger.info("Most actives: %d tickers", len(actives.most_actives or []))
        except Exception as e:
            logger.warning("Failed to fetch most actives: %s — continuing", e)

    # Always include the static universe as a supplement
    static = cfg.screening.universe or []
    universe.update(static)

    logger.info("Universe built: %d dynamic + %d static = %d unique tickers",
                len(universe) - len(static), len(static), len(universe))
    return universe


def _apply_news_boost(picks: list, polygon_api_key: str) -> None:
    """
    For each pick, check the Polygon REST API for a headline in the last 24h.
    If found, boost the score and tag the pick.
    """
    for pick in picks:
        ticker = pick["ticker"]
        has_news = _check_recent_news(ticker, polygon_api_key)
        pick["has_news"] = has_news
        if has_news:
            pick["score"] = round(pick["score"] * _NEWS_BOOST, 3)
            logger.info("News catalyst found for %s — score boosted to %.2f",
                        ticker, pick["score"])


def _check_recent_news(ticker: str, api_key: str) -> bool:
    """
    Query Polygon's reference news endpoint for recent articles about a ticker.
    Returns True if at least one article exists, False otherwise.
    """
    url = (
        f"https://api.polygon.io/v2/reference/news"
        f"?ticker={ticker}&limit=1&apiKey={api_key}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DayTrading-Screener/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("results", [])
            return len(results) > 0
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.debug("News check failed for %s: %s", ticker, e)
        return False


def _write_report(picks: list, cfg) -> None:
    os.makedirs(cfg.reports_dir, exist_ok=True)
    now = datetime.now(timezone.utc)

    source = "dynamic + static" if cfg.screening.use_dynamic_universe else "static only"
    lines = [
        f"# Pre-Market Screener — {now.strftime('%Y-%m-%d')}",
        f"Generated: {now.strftime('%H:%M UTC')}",
        f"Universe: {source} | "
        f"Criteria: gap >= {cfg.screening.min_gap_pct}%, "
        f"vol >= {cfg.screening.min_avg_daily_volume:,}, "
        f"price ${cfg.screening.min_price}–${cfg.screening.max_price}, "
        f"sector cap {cfg.screening.max_per_sector}/sector\n",
        "## Selected Watchlist\n",
        "| # | Ticker | Gap % | Dir | Price | Prev Close | Volume | RVOL | Sector | News | Score |",
        "|---|--------|-------|-----|-------|------------|--------|------|--------|------|-------|",
    ]

    for i, p in enumerate(picks, 1):
        news_flag = "Y" if p.get("has_news") else "—"
        lines.append(
            f"| {i} | **{p['ticker']}** | {p['gap_pct']:+.1f}% | {p['direction']} "
            f"| ${p['current_price']:.2f} | ${p['prev_close']:.2f} "
            f"| {p['prev_volume']:,} | {p['rvol']:.3f} | {p['sector']} "
            f"| {news_flag} | {p['score']:.2f} |"
        )

    lines += [
        "",
        "---",
        "_Purely quantitative screening. Not financial advice._",
    ]

    filepath = os.path.join(cfg.reports_dir, f"screener_{now.strftime('%Y-%m-%d')}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info("Screener report: %s", filepath)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    tickers = run()
    if not tickers:
        sys.exit(1)  # non-zero so start_paper.bat can log a warning
