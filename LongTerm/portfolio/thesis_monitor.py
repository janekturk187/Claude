"""
thesis_monitor.py — checks whether the assumptions behind active positions
are still valid based on the latest company profile and earnings data.

check_all() is the main entry point. It iterates over all active theses,
compares the latest analysis against stored assumptions, and flags any
positions where a core assumption has changed.
"""

import json
import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a portfolio risk analyst. Evaluate whether investment thesis "
    "assumptions still hold based on new data. Respond ONLY with valid JSON."
)

_USER_PROMPT = """\
Review this investment thesis for {ticker} against the latest company data.

Original thesis assumptions:
{assumptions}

Latest company profile (from most recent filing analysis):
{profile}

Latest earnings score:
{earnings}

For each assumption, determine if it is still valid, weakened, or broken.
Then give an overall assessment.

Respond with:
{{
  "assumption_checks": [
    {{"assumption": "<text>", "status": <"valid" | "weakened" | "broken">, "reason": "<brief reason>"}}
  ],
  "overall_status": <"intact" | "weakened" | "broken">,
  "flag": <true | false>,
  "flag_reason": "<if flag is true, explain why the thesis should be reviewed>"
}}"""


def check_thesis(thesis: dict, profile: Optional[dict],
                 earnings_history: list, cfg) -> Optional[dict]:
    """
    Check a single thesis against the latest available data.

    Args:
        thesis:          Row from thesis_log table
        profile:         Latest company_profiles row (or None)
        earnings_history: Last N earnings_scores rows
        cfg:             ClaudeConfig

    Returns:
        Check result dict, or None on failure.
    """
    if profile is None and not earnings_history:
        logger.warning("No data available to check thesis for %s", thesis["ticker"])
        return None

    try:
        assumptions = json.loads(thesis.get("assumptions", "[]"))
    except (ValueError, TypeError):
        assumptions = [thesis.get("thesis_text", "")]

    profile_summary = {
        k: profile[k] for k in
        ("revenue_trend", "margin_trend", "management_tone",
         "guidance_direction", "thesis_score", "thesis_summary")
        if profile and k in profile
    } if profile else {}

    earnings_summary = [
        {k: e[k] for k in ("period", "eps_beat", "guidance_dir", "quality_score", "trend")
         if k in e}
        for e in earnings_history[:2]
    ]

    prompt = _USER_PROMPT.format(
        ticker=thesis["ticker"],
        assumptions=json.dumps(assumptions, indent=2),
        profile=json.dumps(profile_summary, indent=2),
        earnings=json.dumps(earnings_summary, indent=2),
    )

    raw = None
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=cfg.model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if not msg.content:
            return None
        raw = msg.content[0].text
        result = json.loads(raw)
        result["ticker"] = thesis["ticker"]
        result["thesis_id"] = thesis["id"]
        return result

    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON for thesis check on %s", thesis["ticker"])
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error checking thesis for %s: %s", thesis["ticker"], e)
        return None


def check_all(db, cfg) -> list[dict]:
    """
    Check all active theses and flag any with broken assumptions.
    Returns a list of check results (one per thesis).
    """
    active = db.get_active_theses()
    if not active:
        logger.info("No active theses to check")
        return []

    results = []
    for thesis in active:
        ticker = thesis["ticker"]
        profile = db.get_latest_profile(ticker)
        earnings = db.get_earnings_history(ticker, n=2)

        result = check_thesis(thesis, profile, earnings, cfg)
        if result is None:
            continue

        results.append(result)

        if result.get("flag"):
            db.flag_thesis(thesis["id"], result.get("flag_reason", ""))
            logger.warning(
                "THESIS FLAGGED: %s — %s",
                ticker, result.get("flag_reason", "review required"),
            )
        else:
            logger.info(
                "Thesis OK: %s | status=%s",
                ticker, result.get("overall_status"),
            )

    return results
