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
import requests
from typing import Optional

logger = logging.getLogger(__name__)

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

_INDICATORS = {
    "fed_funds_rate":    "DFF",
    "cpi_yoy":           "CPIAUCSL",
    "treasury_10y":      "DGS10",
    "industrial_prod":   "INDPRO",
    "consumer_sentiment": "UMCSENT",
}


def _fetch_latest(series_id: str, api_key: str) -> Optional[float]:
    try:
        resp = requests.get(
            _FRED_BASE,
            params={
                "series_id":    series_id,
                "api_key":      api_key,
                "file_type":    "json",
                "sort_order":   "desc",
                "limit":        2,
            },
            timeout=10,
        )
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
        for obs in observations:
            val = obs.get("value")
            if val and val != ".":
                return float(val)
    except Exception as e:
        logger.error("FRED fetch failed for %s: %s", series_id, e)
    return None


def _direction(series_id: str, api_key: str) -> Optional[str]:
    """Compare the last two observations to determine trend direction."""
    try:
        resp = requests.get(
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
        if len(obs) >= 2:
            if obs[0] > obs[1]:
                return "rising"
            elif obs[0] < obs[1]:
                return "falling"
            return "flat"
    except Exception:
        pass
    return None


def fetch_all(api_key: str) -> list[dict]:
    """
    Fetch all tracked macro indicators and return a list of snapshot dicts.
    Each dict has: indicator, value, direction
    """
    snapshots = []
    for name, series_id in _INDICATORS.items():
        value = _fetch_latest(series_id, api_key)
        direction = _direction(series_id, api_key)
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
