"""
position_tracker.py — enriches open positions with current market prices
and computes unrealized P&L.

Positions are entered and managed manually via the DB (or a future CLI).
This module handles the read side: given open positions, fetch live prices
from FMP and return a portfolio summary.
"""

import logging
from typing import Optional

from data import financials

logger = logging.getLogger(__name__)


def get_portfolio_summary(db, fmp_api_key: str) -> list:
    """
    Fetch current prices for all open positions and compute unrealized P&L.

    Returns a list of position dicts enriched with:
        current_price, unrealized_pnl, pnl_pct, current_value
    Fields are None when the quote fetch fails.
    """
    positions = db.get_open_positions()
    if not positions:
        return []

    result = []
    for pos in positions:
        ticker = pos["ticker"]
        quote = financials.get_quote(ticker, fmp_api_key)
        current_price = quote["price"] if quote else None

        if current_price is not None and pos["entry_price"] and pos["shares"]:
            cost_basis     = pos["entry_price"] * pos["shares"]
            current_value  = current_price * pos["shares"]
            unrealized_pnl = round(current_value - cost_basis, 2)
            pnl_pct        = round(
                (current_price - pos["entry_price"]) / pos["entry_price"] * 100, 2
            )
        else:
            current_value  = None
            unrealized_pnl = None
            pnl_pct        = None

        result.append({
            **pos,
            "current_price":  current_price,
            "current_value":  round(current_value, 2) if current_value else None,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct":        pnl_pct,
        })

    return result
