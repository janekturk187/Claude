"""
macro.py — fetches macroeconomic indicators from the FRED API (free).

Indicators fetched:
  - Federal Funds Rate (DFF)
  - CPI Year-over-Year (CPIAUCSL)
  - 10-Year Treasury Yield (DGS10)
  - ISM Manufacturing PMI (MANEMP proxy via INDPRO)
  - Consumer Sentiment (UMCSENT)
"""

import logging
from typing import Optional

from data import _http

logger = logging.getLogger(__name__)

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

_INDICATORS = {
    "fed_funds_rate":    "DFF",
    "cpi_yoy":           "CPIAUCSL",
    "treasury_10y":      "DGS10",
    "industrial_prod":   "INDPRO",
    "consumer_sentiment": "UMCSENT",
}


def _fetch_indicator(series_id: str, api_key: str) -> tuple[Optional[float], Optional[str]]:
    """Fetch latest value and direction in a single API call."""
    try:
        resp = _http.get_with_retry(
            _FRED_BASE,
            params={
                "series_id":  series_id,
                "api_key":    api_key,
                "file_type":  "json",
                "sort_order": "desc",
                "limit":      3,
            },
            timeout=10,
        )
        resp.raise_for_status()
        obs = [
            float(o["value"]) for o in resp.json().get("observations", [])
            if o.get("value") and o["value"] != "."
        ]
        if not obs:
            return None, None
        value = obs[0]
        if len(obs) >= 2:
            if obs[0] > obs[1]:
                direction = "rising"
            elif obs[0] < obs[1]:
                direction = "falling"
            else:
                direction = "flat"
        else:
            direction = None
        return value, direction
    except Exception as e:
        logger.error("FRED fetch failed for %s: %s", series_id, e)
    return None, None


def fetch_all(api_key: str) -> list[dict]:
    """
    Fetch all tracked macro indicators and return a list of snapshot dicts.
    Each dict has: indicator, value, direction
    """
    snapshots = []
    for name, series_id in _INDICATORS.items():
        value, direction = _fetch_indicator(series_id, api_key)
        snapshots.append({
            "indicator": name,
            "value":     value,
            "direction": direction,
        })
        logger.debug("Macro %s = %s (%s)", name, value, direction)
    return snapshots


def macro_context_summary(snapshots: list[dict]) -> str:
    """
    Build a plain-text macro context paragraph to include in Claude prompts.
    """
    lines = ["Current macroeconomic context:"]
    for s in snapshots:
        val = f"{s['value']:.2f}" if s["value"] is not None else "n/a"
        direction = s["direction"] or "unknown"
        lines.append(f"  - {s['indicator'].replace('_', ' ').title()}: {val} ({direction})")
    return "\n".join(lines)
