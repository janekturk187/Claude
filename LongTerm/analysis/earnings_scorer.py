"""
earnings_scorer.py — scores an earnings report relative to expectations
and builds a quality trend across multiple quarters.
"""

import json
import logging
from typing import Optional

import anthropic

from analysis import _claude

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a financial analyst evaluating earnings quality. "
    "Respond ONLY with a valid JSON object. No markdown, no explanation."
)

_USER_PROMPT = """\
Evaluate this earnings report for {ticker} ({period}).

Financial data:
{financials}

EPS surprise history (most recent first):
{surprises}

Respond with exactly:
{{
  "revenue_beat": <true | false>,
  "eps_beat": <true | false>,
  "guidance_direction": <"raised" | "maintained" | "lowered" | "none">,
  "quality_score": <integer 1-10, where 10 = exceptional beat with raised guidance>,
  "trend": <"improving" | "stable" | "deteriorating">,
  "summary": "<1-2 sentence assessment>"
}}"""


def score(ticker: str, period: str, financials: list, surprises: list,
          cfg) -> Optional[dict]:
    """
    Score an earnings report using financial data and surprise history.

    Args:
        ticker:     Stock ticker
        period:     Quarter string (e.g. "Q1 2026")
        financials: List of income statement dicts from financials.py
        surprises:  List of EPS surprise dicts from financials.py
        cfg:        ClaudeConfig

    Returns:
        Scoring dict or None on failure.
    """
    fin_text = json.dumps(financials[:4], indent=2)
    sur_text = json.dumps(surprises[:4], indent=2)

    prompt = _USER_PROMPT.format(
        ticker=ticker,
        period=period,
        financials=fin_text,
        surprises=sur_text,
    )

    raw = None
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
        result["raw_response"] = raw

        # Clamp quality score
        try:
            result["quality_score"] = max(1, min(10, int(result.get("quality_score", 5))))
        except (TypeError, ValueError):
            result["quality_score"] = 5

        logger.info(
            "Earnings score %s %s | score=%d beat_eps=%s guidance=%s trend=%s",
            ticker, period, result["quality_score"],
            result.get("eps_beat"), result.get("guidance_direction"),
            result.get("trend"),
        )
        return result

    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON for earnings score %s %s", ticker, period)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error scoring earnings for %s: %s", ticker, e)
        return None


def consecutive_beats(history: list) -> int:
    """
    Count the number of consecutive EPS beats from the most recent quarter backward.
    Returns 0 if the most recent quarter was a miss.
    """
    count = 0
    for record in history:
        if record.get("eps_beat"):
            count += 1
        else:
            break
    return count
