"""
technical.py — intraday technical analysis on bar data.

All methods operate on a list of bar dicts (newest last) and return
a structured result that the confluence filter can act on.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_vwap(bars: list) -> Optional[float]:
    """Volume-weighted average price across the provided bars."""
    total_volume = sum(b["volume"] for b in bars if b["volume"])
    if total_volume == 0:
        return None
    vwap = sum(
        ((b["high"] + b["low"] + b["close"]) / 3) * b["volume"]
        for b in bars if b["volume"]
    ) / total_volume
    return round(vwap, 4)


def compute_relative_volume(bars: list, lookback: int = 20) -> Optional[float]:
    """
    Current bar volume vs. average volume over the lookback window.
    Values > 1.5 indicate above-average participation.
    """
    if len(bars) < 2:
        return None
    current_volume = bars[-1]["volume"]
    prior = bars[-lookback:-1] if len(bars) >= lookback else bars[:-1]
    if not prior:
        return None
    avg_volume = sum(b["volume"] for b in prior) / len(prior)
    if avg_volume == 0:
        return None
    return round(current_volume / avg_volume, 2)


def compute_momentum(bars: list, period: int = 5) -> Optional[float]:
    """Rate of change over the last `period` bars (%)."""
    if len(bars) < period + 1:
        return None
    base = bars[-(period + 1)]["close"]
    current = bars[-1]["close"]
    if base == 0:
        return None
    return round(((current - base) / base) * 100, 3)


def find_structure_break(bars: list, lookback: int = 10) -> dict:
    """
    Checks whether the latest close breaks above a prior local high
    or below a prior local low within the lookback window.

    Returns:
        {
            "breakout_high": bool,
            "breakdown_low": bool,
            "local_high": float,
            "local_low": float,
            "breakout_bar_high": float,
        }
    """
    if len(bars) < lookback + 1:
        return {"breakout_high": False, "breakdown_low": False,
                "local_high": None, "local_low": None}

    window = bars[-(lookback + 1):-1]
    current = bars[-1]

    local_high = max(b["high"] for b in window)
    local_low = min(b["low"] for b in window)

    return {
        "breakout_high": current["close"] > local_high,
        "breakdown_low": current["close"] < local_low,
        "local_high": round(local_high, 4),
        "local_low": round(local_low, 4),
        "breakout_bar_low": current["low"],
    }


def analyze(bars: list) -> dict:
    """
    Run all technical indicators on a bar list and return a unified dict.
    Called by the confluence filter on each new bar close.
    """
    if not bars:
        return {}

    latest = bars[-1]
    vwap = compute_vwap(bars)
    rvol = compute_relative_volume(bars)
    momentum = compute_momentum(bars)
    structure = find_structure_break(bars)

    above_vwap = (latest["close"] > vwap) if vwap else None

    return {
        "ticker":        latest["ticker"],
        "close":         latest["close"],
        "vwap":          vwap,
        "above_vwap":    above_vwap,
        "relative_volume": rvol,
        "momentum":      momentum,
        **structure,
    }
