"""
plots.py — generates end-of-session review charts.

Produces PNG files in reports_output/plots/YYYY-MM-DD/:
  - {TICKER}_price.png  per active ticker (price + VWAP + signals + trades + news)
  - pnl_curve.png       cumulative P&L over the session
  - summary.png         P&L bar chart by ticker

Uses the Agg (non-interactive) backend so it works headlessly from Task Scheduler.
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure data-preparation helpers — no matplotlib dependency, fully testable
# ---------------------------------------------------------------------------

def prep_ticker_data(ticker: str, bars: list, signals: list,
                     trades: list, news: list) -> dict:
    """
    Organise raw DB rows for one ticker into plot-ready structures.

    All timestamps are returned as datetime objects (UTC-aware).
    Only rows for this ticker are included.
    """
    def _parse(ts):
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    timestamps, closes, vwaps = [], [], []
    for b in bars:
        ts = _parse(b["timestamp"])
        if ts:
            timestamps.append(ts)
            closes.append(b["close"])
            vwaps.append(b.get("vwap"))

    long_signals, short_signals = [], []
    for s in signals:
        if s["ticker"] != ticker:
            continue
        ts = _parse(s["generated_at"])
        if ts:
            price = s.get("close") or 0
            if s["direction"] == "long":
                long_signals.append((ts, price))
            else:
                short_signals.append((ts, price))

    trade_entries, trade_exits = [], []
    for t in trades:
        if t["ticker"] != ticker:
            continue
        entry_ts = _parse(t["opened_at"])
        if entry_ts and t.get("entry_price"):
            trade_entries.append((entry_ts, t["entry_price"], t["direction"]))
        exit_ts = _parse(t.get("closed_at"))
        if exit_ts and t.get("exit_price"):
            trade_exits.append((exit_ts, t["exit_price"],
                                "target" if (t.get("pnl") or 0) > 0 else "stop"))

    news_events = []
    for n in news:
        if n["ticker"] != ticker:
            continue
        ts = _parse(n["received_at"])
        if ts:
            news_events.append((ts, n.get("sentiment_score", 5)))

    return {
        "ticker":        ticker,
        "timestamps":    timestamps,
        "closes":        closes,
        "vwaps":         vwaps,
        "long_signals":  long_signals,
        "short_signals": short_signals,
        "trade_entries": trade_entries,
        "trade_exits":   trade_exits,
        "news_events":   news_events,
    }


def build_pnl_curve(trades: list) -> tuple:
    """
    Build cumulative P&L series from closed trades sorted by close time.
    Returns (times, cumulative_pnl) as parallel lists.
    """
    closed = [t for t in trades if t.get("status") == "closed" and t.get("closed_at")]
    closed.sort(key=lambda t: t["closed_at"])

    times, cumulative = [], []
    running = 0.0
    for t in closed:
        try:
            ts = datetime.fromisoformat(t["closed_at"])
        except (ValueError, TypeError):
            continue
        running += t.get("pnl") or 0.0
        times.append(ts)
        cumulative.append(round(running, 2))

    return times, cumulative


def build_summary(trades: list, tickers: list) -> tuple:
    """
    Build per-ticker P&L totals for the summary bar chart.
    Returns (ticker_labels, pnl_values).
    """
    pnl_by_ticker = {t: 0.0 for t in tickers}
    for t in trades:
        if t["ticker"] in pnl_by_ticker:
            pnl_by_ticker[t["ticker"]] += t.get("pnl") or 0.0

    labels = list(pnl_by_ticker.keys())
    values = [round(pnl_by_ticker[t], 2) for t in labels]
    return labels, values


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def generate(db, tickers: list, output_dir: str, paper: bool = False) -> list:
    """
    Generate all session plots. Returns a list of saved file paths.
    Returns [] if there is no data or matplotlib is unavailable.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless — must be set before importing pyplot
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        logger.warning("matplotlib not installed — skipping plots (pip install matplotlib)")
        return []

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    plot_dir = os.path.join(output_dir, "plots", date_str)
    os.makedirs(plot_dir, exist_ok=True)

    all_signals = db.get_today_signals()
    all_trades  = db.get_today_trades()
    all_news    = db.get_today_news_events()

    saved = []
    mode_label = "PAPER" if paper else "LIVE"

    # --- Per-ticker price charts ---
    for ticker in tickers:
        bars = db.get_today_bars(ticker)
        if not bars:
            logger.debug("%s: no bars today — skipping price chart", ticker)
            continue

        data = prep_ticker_data(ticker, bars, all_signals, all_trades, all_news)
        path = _plot_price(data, plot_dir, date_str, mode_label, plt, mdates)
        if path:
            saved.append(path)

    # --- Cumulative P&L curve ---
    times, cumulative = build_pnl_curve(all_trades)
    if times:
        path = _plot_pnl_curve(times, cumulative, plot_dir, date_str, mode_label, plt, mdates)
        if path:
            saved.append(path)

    # --- Summary bar chart ---
    labels, values = build_summary(all_trades, tickers)
    if any(v != 0 for v in values):
        path = _plot_summary(labels, values, plot_dir, date_str, mode_label, plt)
        if path:
            saved.append(path)

    logger.info("Generated %d plot(s) in %s", len(saved), plot_dir)
    return saved


def _plot_price(data: dict, plot_dir: str, date_str: str,
                mode_label: str, plt, mdates) -> str | None:
    ticker = data["ticker"]
    if not data["timestamps"]:
        return None

    try:
        fig, ax = plt.subplots(figsize=(14, 6))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#0d1117")

        # Price line
        ax.plot(data["timestamps"], data["closes"],
                color="#58a6ff", linewidth=1.2, label="Close", zorder=2)

        # VWAP line (skip None values)
        vwap_pairs = [(t, v) for t, v in zip(data["timestamps"], data["vwaps"]) if v is not None]
        if vwap_pairs:
            vt, vv = zip(*vwap_pairs)
            ax.plot(vt, vv, color="#f0a500", linewidth=1.0,
                    linestyle="--", alpha=0.8, label="VWAP", zorder=2)

        # News events — faint vertical lines coloured by sentiment
        for ts, sentiment in data["news_events"]:
            color = "#3fb950" if sentiment >= 7 else "#f85149" if sentiment <= 3 else "#8b949e"
            ax.axvline(ts, color=color, linewidth=0.7, alpha=0.4, zorder=1)

        # Signal markers
        if data["long_signals"]:
            st, sp = zip(*data["long_signals"])
            ax.scatter(st, sp, marker="^", color="#3fb950", s=100,
                       zorder=4, label="Long signal")
        if data["short_signals"]:
            st, sp = zip(*data["short_signals"])
            ax.scatter(st, sp, marker="v", color="#f85149", s=100,
                       zorder=4, label="Short signal")

        # Trade entries
        for ts, price, direction in data["trade_entries"]:
            color = "#3fb950" if direction == "long" else "#f85149"
            ax.scatter(ts, price, marker="o", color=color, s=120,
                       edgecolors="white", linewidths=0.5, zorder=5)

        # Trade exits
        for ts, price, reason in data["trade_exits"]:
            marker = "*" if reason == "target" else "x"
            color  = "#3fb950" if reason == "target" else "#f85149"
            ax.scatter(ts, price, marker=marker, color=color, s=150,
                       zorder=5, label=f"Exit ({reason})")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        _style_axes(ax)
        ax.set_title(f"{ticker} — {date_str} [{mode_label}]",
                     color="white", fontsize=13, pad=10)
        ax.set_xlabel("Time (ET)", color="#8b949e")
        ax.set_ylabel("Price ($)", color="#8b949e")

        handles, labels = ax.get_legend_handles_labels()
        seen, h2, l2 = set(), [], []
        for h, lb in zip(handles, labels):
            if lb not in seen:
                seen.add(lb); h2.append(h); l2.append(lb)
        ax.legend(h2, l2, facecolor="#161b22", edgecolor="#30363d",
                  labelcolor="white", fontsize=8)

        fig.tight_layout()
        path = os.path.join(plot_dir, f"{ticker}_price.png")
        fig.savefig(path, dpi=120, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        return path
    except Exception as e:
        logger.error("Failed to render price chart for %s: %s", ticker, e)
        plt.close("all")
        return None


def _plot_pnl_curve(times: list, cumulative: list,
                    plot_dir: str, date_str: str, mode_label: str,
                    plt, mdates) -> str | None:
    try:
        fig, ax = plt.subplots(figsize=(12, 4))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#0d1117")

        final_pnl = cumulative[-1] if cumulative else 0
        line_color = "#3fb950" if final_pnl >= 0 else "#f85149"
        ax.plot(times, cumulative, color=line_color, linewidth=1.5)
        ax.fill_between(times, cumulative, 0,
                        where=[v >= 0 for v in cumulative],
                        color="#3fb950", alpha=0.15)
        ax.fill_between(times, cumulative, 0,
                        where=[v < 0 for v in cumulative],
                        color="#f85149", alpha=0.15)
        ax.axhline(0, color="#8b949e", linewidth=0.8, linestyle="--")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        _style_axes(ax)
        ax.set_title(f"Cumulative P&L — {date_str} [{mode_label}]  "
                     f"Final: ${final_pnl:+,.2f}",
                     color="white", fontsize=12, pad=10)
        ax.set_xlabel("Time (ET)", color="#8b949e")
        ax.set_ylabel("P&L ($)", color="#8b949e")

        fig.tight_layout()
        path = os.path.join(plot_dir, "pnl_curve.png")
        fig.savefig(path, dpi=120, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        return path
    except Exception as e:
        logger.error("Failed to render P&L curve: %s", e)
        plt.close("all")
        return None


def _plot_summary(labels: list, values: list,
                  plot_dir: str, date_str: str, mode_label: str, plt) -> str | None:
    try:
        fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.4), 4))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#0d1117")

        colors = ["#3fb950" if v >= 0 else "#f85149" for v in values]
        bars = ax.bar(labels, values, color=colors, edgecolor="#30363d", width=0.6)

        for bar, val in zip(bars, values):
            ypos = bar.get_height() + (max(values) * 0.02 if max(values) != 0 else 0.5)
            ax.text(bar.get_x() + bar.get_width() / 2, ypos,
                    f"${val:+.2f}", ha="center", va="bottom",
                    color="white", fontsize=9)

        ax.axhline(0, color="#8b949e", linewidth=0.8)
        _style_axes(ax)
        ax.set_title(f"P&L by Ticker — {date_str} [{mode_label}]",
                     color="white", fontsize=12, pad=10)
        ax.set_ylabel("P&L ($)", color="#8b949e")

        fig.tight_layout()
        path = os.path.join(plot_dir, "summary.png")
        fig.savefig(path, dpi=120, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        return path
    except Exception as e:
        logger.error("Failed to render summary chart: %s", e)
        plt.close("all")
        return None


def _style_axes(ax):
    """Apply dark-theme styling to an axes object."""
    ax.tick_params(colors="#8b949e")
    ax.spines["bottom"].set_color("#30363d")
    ax.spines["left"].set_color("#30363d")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.label.set_color("#8b949e")
    ax.xaxis.label.set_color("#8b949e")
    ax.grid(True, color="#21262d", linewidth=0.5, linestyle="--", alpha=0.6)
