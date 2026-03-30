"""
valuation.py — Claude-powered valuation assessment.

Given trailing-twelve-month metrics (P/E, PEG, P/FCF, EV/EBITDA), asks Claude
to grade the stock as cheap, fair, or expensive and provide a brief narrative.

This complements the filing/earnings analysis by answering "is it cheap?"
rather than just "is the business healthy?".
"""

import json
import logging
from typing import Optional

import anthropic

from analysis import _claude

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a value investor assessing equity valuations. "
    "Respond ONLY with valid JSON."
)

_USER_PROMPT = """\
Assess the current valuation of {ticker} using these trailing twelve month metrics:

  P/E Ratio:   {pe}
  PEG Ratio:   {peg}
  Price/FCF:   {pfcf}
  EV/EBITDA:   {ev_ebitda}

Guidelines (use as reference, not hard rules):
- PEG < 1 often suggests undervaluation relative to growth
- P/E < 15 has historically been considered cheap for the broad market
- High-quality compounders routinely trade above market averages
- "Unknown" metrics should not automatically disqualify a grade

Give a concise 2–3 sentence assessment and a single grade.

Respond with:
{{
  "valuation_grade":   "cheap" | "fair" | "expensive" | "unknown",
  "valuation_summary": "<2-3 sentences>"
}}"""


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.1f}x"
    except (TypeError, ValueError):
        return "n/a"


def assess(ticker: str, metrics: dict, cfg) -> Optional[dict]:
    """
    Ask Claude to grade the valuation of ticker based on key_metrics dict.

    Args:
        ticker:  stock symbol
        metrics: dict from financials.get_key_metrics()
        cfg:     ClaudeConfig

    Returns dict with pe_ratio, peg_ratio, pfcf_ratio, ev_ebitda,
    valuation_grade, valuation_summary — or None on failure.
    """
    prompt = _USER_PROMPT.format(
        ticker=ticker,
        pe=_fmt(metrics.get("pe_ratio")),
        peg=_fmt(metrics.get("peg_ratio")),
        pfcf=_fmt(metrics.get("pfcf")),
        ev_ebitda=_fmt(metrics.get("ev_ebitda")),
    )

    try:
        msg = _claude.create_message(
            model=cfg.model,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if not msg.content:
            return None
        raw = msg.content[0].text
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON for valuation of %s", ticker)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error for valuation of %s: %s", ticker, e)
        return None

    grade = result.get("valuation_grade", "unknown")
    if grade not in ("cheap", "fair", "expensive", "unknown"):
        grade = "unknown"

    return {
        "pe_ratio":         metrics.get("pe_ratio"),
        "peg_ratio":        metrics.get("peg_ratio"),
        "pfcf_ratio":       metrics.get("pfcf"),
        "ev_ebitda":        metrics.get("ev_ebitda"),
        "valuation_grade":   grade,
        "valuation_summary": result.get("valuation_summary", ""),
    }
