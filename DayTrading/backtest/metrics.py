"""
metrics.py — performance metrics calculated from a list of backtest trades.
"""


def calculate(trades: list) -> dict:
    """
    Calculate performance metrics from a list of completed trades.

    Returns a dict with: total_trades, winners, losers, win_rate, total_pnl,
    avg_win, avg_loss, profit_factor, max_drawdown, exits_by_reason.
    """
    if not trades:
        return {
            "total_trades":   0,
            "winners":        0,
            "losers":         0,
            "win_rate":       0.0,
            "total_pnl":      0.0,
            "avg_win":        0.0,
            "avg_loss":       0.0,
            "profit_factor":  0.0,
            "max_drawdown":   0.0,
            "exits_by_reason": {},
        }

    winners = [t for t in trades if t["pnl"] > 0]
    losers  = [t for t in trades if t["pnl"] <= 0]

    total_pnl    = sum(t["pnl"] for t in trades)
    win_rate     = len(winners) / len(trades) * 100
    avg_win      = sum(t["pnl"] for t in winners) / len(winners) if winners else 0.0
    avg_loss     = sum(t["pnl"] for t in losers)  / len(losers)  if losers  else 0.0
    gross_profit = sum(t["pnl"] for t in winners)
    gross_loss   = abs(sum(t["pnl"] for t in losers))

    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = None  # infinite — no losers
    else:
        profit_factor = 0.0

    # Max drawdown — largest peak-to-trough in cumulative P&L
    running_pnl  = 0.0
    peak         = 0.0
    max_drawdown = 0.0
    for t in trades:
        running_pnl += t["pnl"]
        if running_pnl > peak:
            peak = running_pnl
        drawdown = peak - running_pnl
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    exits_by_reason: dict = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        exits_by_reason[reason] = exits_by_reason.get(reason, 0) + 1

    return {
        "total_trades":    len(trades),
        "winners":         len(winners),
        "losers":          len(losers),
        "win_rate":        round(win_rate, 1),
        "total_pnl":       round(total_pnl, 2),
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss, 2),
        "profit_factor":   profit_factor,
        "max_drawdown":    round(max_drawdown, 2),
        "exits_by_reason": exits_by_reason,
    }
