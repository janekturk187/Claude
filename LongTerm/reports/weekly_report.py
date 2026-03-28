"""
weekly_report.py — generates a weekly research summary from the database.

Produces a markdown file covering:
  - Active thesis statuses and any flags
  - Earnings quality trends per ticker
  - Current macro environment
  - Upcoming analysis triggers (tickers due for filing review)
"""

import logging
import os
from datetime import datetime, timezone

from analysis.earnings_scorer import consecutive_beats

logger = logging.getLogger(__name__)


def generate(db, tickers: list, output_dir: str) -> str:
    """
    Generate a weekly report and write it to output_dir.
    Returns the path to the written file.
    """
    os.makedirs(output_dir, exist_ok=True)

    lines = []
    now = datetime.now(timezone.utc)
    lines.append(f"# Weekly Research Report")
    lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}\n")

    # --- Active Theses ---
    lines.append("## Active Theses\n")
    theses = db.get_active_theses()
    flagged = [t for t in theses if t.get("status") == "flagged"]

    if not theses:
        lines.append("_No active theses on record._\n")
    else:
        for t in theses:
            flag_marker = " ⚠ FLAGGED" if t.get("status") == "flagged" else ""
            lines.append(f"### {t['ticker']}{flag_marker}")
            lines.append(f"- **Entered:** {t['entered_at'][:10]}")
            lines.append(f"- **Thesis:** {t['thesis_text']}")
            if t.get("flag_reason"):
                lines.append(f"- **Flag reason:** {t['flag_reason']}")
            lines.append("")

    if flagged:
        lines.append(f"> **{len(flagged)} thesis(es) flagged for review this week.**\n")

    # --- Earnings Quality Trends ---
    lines.append("## Earnings Quality Trends\n")
    lines.append("| Ticker | Latest Score | Trend | EPS Beat | Guidance | Beat Streak |")
    lines.append("|--------|-------------|-------|----------|----------|-------------|")
    for ticker in tickers:
        history = db.get_earnings_history(ticker, n=4)
        if history:
            e = history[0]
            streak = consecutive_beats(history)
            lines.append(
                f"| {ticker} | {e.get('quality_score', 'n/a')} "
                f"| {e.get('trend', 'n/a')} "
                f"| {'✓' if e.get('eps_beat') else '✗'} "
                f"| {e.get('guidance_dir', 'n/a')} "
                f"| {streak}Q |"
            )
        else:
            lines.append(f"| {ticker} | — | — | — | — | — |")
    lines.append("")

    # --- Company Profile Scores ---
    lines.append("## Latest Company Profile Scores\n")
    lines.append("| Ticker | Thesis Score | Revenue | Margins | Tone | Guidance |")
    lines.append("|--------|-------------|---------|---------|------|----------|")
    for ticker in tickers:
        p = db.get_latest_profile(ticker)
        if p:
            lines.append(
                f"| {ticker} | {p.get('thesis_score', 'n/a')} "
                f"| {p.get('revenue_trend', 'n/a')} "
                f"| {p.get('margin_trend', 'n/a')} "
                f"| {p.get('management_tone', 'n/a')} "
                f"| {p.get('guidance_direction', 'n/a')} |"
            )
        else:
            lines.append(f"| {ticker} | — | — | — | — | — |")
    lines.append("")

    # --- Macro Environment ---
    lines.append("## Macro Environment\n")
    macro = db.get_latest_macro()
    if macro:
        lines.append("| Indicator | Value | Direction |")
        lines.append("|-----------|-------|-----------|")
        for m in macro:
            val = f"{m['value']:.2f}" if m["value"] is not None else "n/a"
            lines.append(
                f"| {m['indicator'].replace('_', ' ').title()} "
                f"| {val} | {m.get('direction', 'n/a')} |"
            )
    else:
        lines.append("_No macro data available._")
    lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("_This report is for research purposes only. Not financial advice._")

    report = "\n".join(lines)
    filename = f"weekly_{now.strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("Weekly report written to %s", filepath)
    return filepath
