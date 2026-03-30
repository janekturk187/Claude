"""
report.py — generates a markdown backtest results report.
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate(metrics: dict, trades: list, tickers: list,
             output_dir: str, start: str, end: str,
             sentiment_score: float, starting_equity: float) -> str:
    """
    Write a backtest report to output_dir and return the file path.
    """
    os.makedirs(output_dir, exist_ok=True)

    now = datetime.now(timezone.utc)
    lines = []

    lines.append(f"# Backtest Report")
    lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Period: {start} → {end}")
    lines.append(f"Tickers: {', '.join(tickers)}")
    lines.append(f"Starting equity: ${starting_equity:,.0f} | Fixed sentiment: {sentiment_score}\n")
    lines.append("> **Note:** Sentiment was fixed for all bars — results reflect technical "
                 "signals only. Live performance will differ based on news flow.\n")

    # --- Overall metrics ---
    lines.append("## Overall Performance\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total trades | {metrics['total_trades']} |")
    lines.append(f"| Winners | {metrics['winners']} |")
    lines.append(f"| Losers | {metrics['losers']} |")
    lines.append(f"| Win rate | {metrics['win_rate']}% |")
    lines.append(f"| Total P&L | ${metrics['total_pnl']:+,.2f} |")
    lines.append(f"| Avg win | ${metrics['avg_win']:+,.2f} |")
    lines.append(f"| Avg loss | ${metrics['avg_loss']:+,.2f} |")
    pf = metrics['profit_factor']
    lines.append(f"| Profit factor | {'∞' if pf is None else pf} |")
    lines.append(f"| Max drawdown | ${metrics['max_drawdown']:,.2f} |")
    lines.append("")

    # --- Exit breakdown ---
    exits = metrics.get("exits_by_reason", {})
    if exits:
        lines.append("## Exit Breakdown\n")
        lines.append("| Exit Reason | Count |")
        lines.append("|-------------|-------|")
        for reason, count in sorted(exits.items()):
            lines.append(f"| {reason} | {count} |")
        lines.append("")

    # --- Per-ticker breakdown ---
    lines.append("## Per-Ticker Breakdown\n")
    lines.append("| Ticker | Trades | Win Rate | P&L |")
    lines.append("|--------|--------|----------|-----|")
    for ticker in tickers:
        ticker_trades = [t for t in trades if t["ticker"] == ticker]
        if not ticker_trades:
            lines.append(f"| {ticker} | 0 | — | — |")
            continue
        wins    = [t for t in ticker_trades if t["pnl"] > 0]
        pnl     = sum(t["pnl"] for t in ticker_trades)
        wr      = len(wins) / len(ticker_trades) * 100
        lines.append(f"| {ticker} | {len(ticker_trades)} | {wr:.0f}% | ${pnl:+,.2f} |")
    lines.append("")

    # --- Trade log ---
    lines.append("## Trade Log\n")
    if not trades:
        lines.append("_No trades generated._\n")
    else:
        lines.append("| Ticker | Dir | Strength | Entry | Exit | P&L | Reason |")
        lines.append("|--------|-----|----------|-------|------|-----|--------|")
        for t in trades:
            lines.append(
                f"| {t['ticker']} | {t['direction']} | {t.get('signal_strength', 'n/a')} "
                f"| ${t['entry_price']:.2f} | ${t['exit_price']:.2f} "
                f"| ${t['pnl']:+.2f} | {t.get('exit_reason', '?')} |"
            )
        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("_Backtest results are hypothetical and do not guarantee future performance. "
                 "Not financial advice._")

    report = "\n".join(lines)
    filename = f"backtest_{start}_to_{end}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("Backtest report written to %s", filepath)
    return filepath
