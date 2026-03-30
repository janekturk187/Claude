"""
historical.py — fetches historical 1-minute bars from Alpaca for backtesting.
"""

import logging
from datetime import datetime

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

logger = logging.getLogger(__name__)


def fetch_bars(ticker: str, api_key: str, secret_key: str,
               start: datetime, end: datetime) -> list:
    """
    Fetch 1-minute bars for a single ticker between start and end (UTC datetimes).
    Returns a list of normalized bar dicts, oldest first.
    """
    client = StockHistoricalDataClient(api_key, secret_key)
    req = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
    )
    try:
        response = client.get_stock_bars(req)
    except Exception as e:
        logger.error("Failed to fetch historical bars for %s: %s", ticker, e)
        return []

    raw_bars = response.get(ticker, [])
    bars = [
        {
            "ticker":     b.symbol,
            "timestamp":  b.timestamp.isoformat(),
            "resolution": "1min",
            "open":       float(b.open),
            "high":       float(b.high),
            "low":        float(b.low),
            "close":      float(b.close),
            "volume":     int(b.volume),
            "vwap":       float(b.vwap) if b.vwap else None,
        }
        for b in raw_bars
    ]
    logger.info("Fetched %d bars for %s (%s → %s)", len(bars), ticker,
                start.date(), end.date())
    return bars
