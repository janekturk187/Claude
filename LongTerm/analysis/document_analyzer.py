"""
document_analyzer.py — sends SEC filings and earnings transcripts to Claude
for structured company analysis.

Uses claude-opus for deep document comprehension. Returns a structured
company profile dict suitable for storage and thesis building.
"""

import json
import logging
from typing import Optional

import anthropic

from analysis import _claude

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a senior fundamental equity analyst. Analyze the provided filing "
    "excerpt and respond ONLY with a valid JSON object. No markdown, no explanation."
)

_USER_PROMPT = """\
Analyze this {filing_type} filing for {ticker} (period: {period}).

{macro_context}

Filing excerpt:
---
{text}
---

Respond with exactly this JSON structure:
{{
  "revenue_trend": <"growing" | "stable" | "declining">,
  "margin_trend": <"expanding" | "stable" | "compressing">,
  "key_risks": [<list of up to 5 specific risk strings>],
  "key_opportunities": [<list of up to 5 specific opportunity strings>],
  "management_tone": <"confident" | "cautious" | "defensive" | "neutral">,
  "guidance_direction": <"raised" | "maintained" | "lowered" | "none">,
  "thesis_score": <integer 1-10, overall investment attractiveness>,
  "thesis_summary": "<2-3 sentence synthesis of the investment case>"
}}"""


def analyze_filing(ticker: str, filing_type: str, period: str,
                   text: str, cfg, macro_context: str = "") -> Optional[dict]:
    """
    Send a filing excerpt to Claude and return a structured company profile.

    Args:
        ticker:        Stock ticker (e.g. "AAPL")
        filing_type:   "10-K", "10-Q", or "8-K"
        period:        Reporting period string (e.g. "FY2025", "Q1 2026")
        text:          Filing text (will be truncated to fit context)
        cfg:           ClaudeConfig
        macro_context: Optional macro summary string from macro.py

    Returns:
        Parsed analysis dict, or None on failure.
    """
    # Truncate text to fit within model context window.
    # claude-opus-4 has a 200k token context window; reserve ~4k tokens for the
    # prompt template and response. cfg.max_tokens is the *output* limit, not the
    # context window, so do not use it here (~3 chars per token on average).
    MAX_FILING_CHARS = 580_000  # ≈ 193k tokens, leaves headroom for prompt + response
    if len(text) > MAX_FILING_CHARS:
        text = text[:MAX_FILING_CHARS]
        logger.debug("Truncated %s %s filing to %d chars", ticker, filing_type, MAX_FILING_CHARS)

    prompt = _USER_PROMPT.format(
        ticker=ticker,
        filing_type=filing_type,
        period=period,
        text=text,
        macro_context=macro_context or "No macro context available.",
    )

    raw = None
    try:
        msg = _claude.create_message(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if not msg.content:
            logger.warning("Claude returned empty content for %s %s", ticker, filing_type)
            return None
        raw = msg.content[0].text
        result = json.loads(raw)
        result["raw_response"] = raw
        _validate_profile(result)
        logger.info(
            "Analyzed %s %s %s | score=%s trend=%s tone=%s",
            ticker, filing_type, period,
            result.get("thesis_score"),
            result.get("revenue_trend"),
            result.get("management_tone"),
        )
        return result

    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON for %s %s", ticker, filing_type)
        if raw:
            logger.debug("Raw: %s", raw[:200])
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error analyzing %s %s: %s", ticker, filing_type, e)
        return None


def _validate_profile(result: dict):
    """Normalize and clamp fields in place."""
    score = result.get("thesis_score")
    if score is not None:
        try:
            result["thesis_score"] = max(1, min(10, int(score)))
        except (TypeError, ValueError):
            result["thesis_score"] = 5

    valid_trends = {"growing", "stable", "declining"}
    if result.get("revenue_trend") not in valid_trends:
        result["revenue_trend"] = "stable"

    valid_margin = {"expanding", "stable", "compressing"}
    if result.get("margin_trend") not in valid_margin:
        result["margin_trend"] = "stable"

    valid_tone = {"confident", "cautious", "defensive", "neutral"}
    if result.get("management_tone") not in valid_tone:
        result["management_tone"] = "neutral"

    valid_guidance = {"raised", "maintained", "lowered", "none"}
    if result.get("guidance_direction") not in valid_guidance:
        result["guidance_direction"] = "none"

    for field in ("key_risks", "key_opportunities"):
        if not isinstance(result.get(field), list):
            result[field] = []
