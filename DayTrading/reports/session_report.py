"""
session_report.py — generates an end-of-session trading summary.

Covers signals fired, trades taken, P&L, win rate, and notable news.
Written to reports_dir as a markdown file.
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate(db, tickers: list, output_dir: str, paper: bool = False) -> str:
    """
    Generate a session report and write it to output_dir.
    Returns the path to the written file.
    """
    os.makedirs(output_dir, exist_ok=True)

    signals = db.get_today_signals()
    trades = db.get_today_trades()
    news = db.get_today_news_events()

    now = datetime.now(timezone.utc)
    mode_label = "PAPER" if paper else "LIVE"

    lines = []
    lines.append(f"# Session Report — {now.strftime('%Y-%m-%d')} [{mode_label}]")
    lines.append(f"Generated: {now.strftime('%H:%M UTC')}\n")

    # --- Summary ---
    closed_trades = [t for t in trades if t["status"] == "closed"]
    open_trades   = [t for t in trades if t["status"] == "open"]
    winners       = [t for t in closed_trades if (t["pnl"] or 0) > 0]
    total_pnl     = sum(t["pnl"] or 0 for t in closed_trades)
    win_rate      = len(winners) / len(closed_trades) * 100 if closed_trades else 0

    lines.append("## Summary\n")
    lines.append(f"| | |")
    lines.append(f"|---|---|")
    lines.append(f"| Signals fired | {len(signals)} |")
    lines.append(f"| Trades taken | {len(trades)} |")
    lines.append(f"| Closed | {len(closed_trades)} |")
    lines.append(f"| Still open | {len(open_trades)} |")
    lines.append(f"| Winners | {len(winners)} |")
    lines.append(f"| Win rate | {win_rate:.0f}% |")
    lines.append(f"| Realized P&L | ${total_pnl:+.2f} |")
    lines.append("")

    # --- Signals ---
    lines.append("## Signals Fired\n")
    if not signals:
        lines.append("_No signals generated today._\n")
    else:
        lines.append("| Time | Ticker | Direction | Strength | Sentiment | Price |")
        lines.append("|------|--------|-----------|----------|-----------|-------|")
        for s in signals:
            ts = s["generated_at"][11:16] if s["generated_at"] else "?"
            sent = f"{s['sentiment_score']:.1f}" if s["sentiment_score"] is not None else "n/a"
            price = f"${s['close']:.2f}" if s["close"] else "n/a"
            lines.append(
                f"| {ts} | {s['ticker']} | {s['direction']} "
                f"| {s.get('signal_strength', 'n/a')} | {sent} | {price} |"
            )
        lines.append("")

    # --- Trades ---
    lines.append("## Trades\n")
    if not trades:
        lines.append("_No trades placed today._\n")
    else:
        lines.append("| Ticker | Dir | Entry | Exit | Stop | Target | Qty | P&L | Status |")
        lines.append("|--------|-----|-------|------|------|--------|-----|-----|--------|")
        for t in trades:
            entry  = f"${t['entry_price']:.2f}"  if t["entry_price"]  else "n/a"
            exit_  = f"${t['exit_price']:.2f}"   if t["exit_price"]   else "—"
            stop   = f"${t['stop_price']:.2f}"   if t["stop_price"]   else "n/a"
            target = f"${t['target_price']:.2f}" if t["target_price"] else "n/a"
            pnl    = f"${t['pnl']:+.2f}"         if t["pnl"] is not None else "—"
            lines.append(
                f"| {t['ticker']} | {t['direction']} | {entry} | {exit_} "
                f"| {stop} | {target} | {t['qty']} | {pnl} | {t['status']} |"
            )
        lines.append("")

    # --- Notable News ---
    lines.append("## News Received\n")
    if not news:
        lines.append("_No news events today._\n")
    else:
        lines.append("| Time | Ticker | Sentiment | Confidence | Type | Headline |")
        lines.append("|------|--------|-----------|------------|------|---------|")
        for n in news[:20]:  # cap at 20 to keep report readable
            ts = n["received_at"][11:16] if n["received_at"] else "?"
            headline = (n["headline"] or "")[:60]
            lines.append(
                f"| {ts} | {n['ticker']} | {n['sentiment_score']} "
                f"| {n['confidence']} | {n.get('event_type', 'n/a')} | {headline} |"
            )
        if len(news) > 20:
            lines.append(f"\n_... and {len(news) - 20} more events._")
        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("_This report is for informational purposes only. Not financial advice._")

    report = "\n".join(lines)
    filename = f"session_{now.strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("Session report written to %s", filepath)
    return filepath
