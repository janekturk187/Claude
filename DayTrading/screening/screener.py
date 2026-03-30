"""
screener.py — ranks stocks by pre-market conditions.

Pure functions only. The runner handles I/O; this module handles scoring.

Scoring model:
  - Hard filters: gap %, volume, price range
  - Base score = abs(gap_pct) * (1 + log10(volume_M + 1))
  - RVOL boost: pre-market volume relative to prior day amplifies the score
  - Turnover intensity: rough proxy for float — high volume relative to price
    suggests smaller float, which means gaps are more likely to follow through.
    Proper float data from a reference provider would be better.
  - Sector cap: after scoring, limit picks per sector to prevent correlated risk
"""

import logging
import math
from typing import Optional

from screening.sectors import get_sector

logger = logging.getLogger(__name__)


def score_snapshot(ticker: str, snapshot, cfg) -> Optional[dict]:
    """
    Evaluate a single Alpaca snapshot against the screening criteria.

    Returns a candidate dict or None if the ticker doesn't pass filters.

    snapshot is an alpaca-py Snapshot object with attributes:
      .prev_daily_bar.close, .prev_daily_bar.volume
      .daily_bar.volume (today's accumulated volume, including pre-market)
      .latest_trade.price
    """
    prev_bar = snapshot.prev_daily_bar if snapshot else None
    daily_bar = snapshot.daily_bar if snapshot else None
    latest_trade = snapshot.latest_trade if snapshot else None

    prev_close  = float(prev_bar.close)  if prev_bar and prev_bar.close  else None
    prev_volume = int(prev_bar.volume)   if prev_bar and prev_bar.volume else 0
    current_price = float(latest_trade.price) if latest_trade and latest_trade.price else None

    if not prev_close or not current_price or prev_close == 0:
        return None

    gap_pct = (current_price - prev_close) / prev_close * 100

    # --- Hard filters ---
    if abs(gap_pct) < cfg.min_gap_pct:
        return None
    if prev_volume < cfg.min_avg_daily_volume:
        return None
    if current_price < cfg.min_price or current_price > cfg.max_price:
        return None

    # --- RVOL: today's accumulated volume vs yesterday's full day ---
    daily_volume = int(daily_bar.volume) if daily_bar and daily_bar.volume else 0
    rvol = daily_volume / prev_volume if prev_volume > 0 else 0.0

    if cfg.min_rvol > 0 and rvol < cfg.min_rvol:
        return None

    # --- Base score: gap magnitude × log-scaled liquidity ---
    volume_m = prev_volume / 1_000_000
    base_score = abs(gap_pct) * (1 + math.log10(volume_m + 1))

    # --- RVOL boost: unusually active pre-market gets a multiplier ---
    # rvol is small pre-market (0.01-0.10 typical), so scale it up.
    # A stock showing 5% of yesterday's volume before the bell is notable.
    rvol_boost = 1 + min(rvol * 10, 2.0)  # cap at 3x total multiplier

    # --- Turnover intensity: float proxy ---
    # High share volume relative to price suggests smaller effective float.
    # volume / (price * 10_000) normalizes across price levels.
    turnover = prev_volume / (prev_close * 10_000) if prev_close > 0 else 0
    float_factor = 1 + min(math.log10(turnover + 1), 0.5)

    score = base_score * rvol_boost * float_factor
    sector = get_sector(ticker)

    return {
        "ticker":        ticker,
        "gap_pct":       round(gap_pct, 2),
        "direction":     "up" if gap_pct > 0 else "down",
        "current_price": round(current_price, 2),
        "prev_close":    round(prev_close, 2),
        "prev_volume":   prev_volume,
        "rvol":          round(rvol, 4),
        "sector":        sector,
        "score":         round(score, 3),
    }


def pick_tickers(snapshots: dict, cfg) -> list:
    """
    Score all snapshots, apply filters and sector cap, return top N candidates
    sorted by score descending.

    Args:
        snapshots: {ticker: Snapshot} from Alpaca
        cfg: ScreeningConfig
    """
    candidates = []
    for ticker, snapshot in snapshots.items():
        result = score_snapshot(ticker, snapshot, cfg)
        if result is not None:
            candidates.append(result)
            logger.debug("%s: gap=%+.1f%% vol=%s rvol=%.3f sector=%s score=%.2f",
                         ticker, result["gap_pct"],
                         f"{result['prev_volume']:,}", result["rvol"],
                         result["sector"], result["score"])

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Apply sector cap if configured
    max_sector = getattr(cfg, "max_per_sector", 0)
    if max_sector > 0:
        picks = _apply_sector_cap(candidates, max_sector, cfg.max_picks)
    else:
        picks = candidates[: cfg.max_picks]

    if candidates:
        logger.info(
            "%d/%d tickers passed screening — top picks: %s",
            len(candidates), len(snapshots),
            [p["ticker"] for p in picks],
        )
    else:
        logger.info("No tickers passed screening criteria")

    return picks


def _apply_sector_cap(candidates: list, max_per_sector: int, max_picks: int) -> list:
    """
    Walk the score-sorted candidate list, skipping any ticker that would
    exceed the per-sector cap.  Returns up to max_picks candidates.
    """
    picks = []
    sector_count: dict[str, int] = {}

    for c in candidates:
        if len(picks) >= max_picks:
            break
        sector = c["sector"]
        count = sector_count.get(sector, 0)
        if count >= max_per_sector:
            logger.debug("Sector cap: skipping %s (%s already has %d pick(s))",
                         c["ticker"], sector, count)
            continue
        picks.append(c)
        sector_count[sector] = count + 1

    return picks
