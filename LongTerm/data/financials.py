"""
financials.py — fetches structured financial statement data from
Financial Modeling Prep API (free tier).

Provides revenue, margins, FCF, and balance sheet ratios per ticker
for the last N quarters.
"""

import logging
from typing import Optional

from data import _http

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/api/v3"


def _get(endpoint: str, api_key: str, params: dict = None) -> Optional[list]:
    url = f"{_FMP_BASE}/{endpoint}"
    p = {"apikey": api_key, **(params or {})}
    try:
        resp = _http.get_with_retry(url, params=p, timeout=15)
        return resp.json()
    except Exception as e:
        logger.error("FMP request failed (%s): %s", endpoint, e)
        return None


def get_income_statement(ticker: str, api_key: str, quarters: int = 4) -> list[dict]:
    """Returns the last N quarterly income statements."""
    data = _get(f"income-statement/{ticker}", api_key, {"period": "quarter", "limit": quarters})
    if not data:
        return []
    results = []
    for item in data:
        results.append({
            "period":           item.get("period"),
            "date":             item.get("date"),
            "revenue":          item.get("revenue"),
            "gross_profit":     item.get("grossProfit"),
            "gross_margin":     item.get("grossProfitRatio"),
            "operating_income": item.get("operatingIncome"),
            "operating_margin": item.get("operatingIncomeRatio"),
            "net_income":       item.get("netIncome"),
            "eps":              item.get("eps"),
        })
    return results


def get_cash_flow(ticker: str, api_key: str, quarters: int = 4) -> list[dict]:
    """Returns the last N quarterly cash flow statements."""
    data = _get(f"cash-flow-statement/{ticker}", api_key, {"period": "quarter", "limit": quarters})
    if not data:
        return []
    return [
        {
            "period":         item.get("period"),
            "date":           item.get("date"),
            "free_cash_flow": item.get("freeCashFlow"),
            "capex":          item.get("capitalExpenditure"),
            "operating_cf":   item.get("operatingCashFlow"),
        }
        for item in data
    ]


def get_balance_sheet(ticker: str, api_key: str, quarters: int = 4) -> list[dict]:
    """Returns the last N quarterly balance sheets."""
    data = _get(f"balance-sheet-statement/{ticker}", api_key, {"period": "quarter", "limit": quarters})
    if not data:
        return []
    return [
        {
            "period":          item.get("period"),
            "date":            item.get("date"),
            "total_debt":      item.get("totalDebt"),
            "cash":            item.get("cashAndCashEquivalents"),
            "total_equity":    item.get("totalStockholdersEquity"),
            "debt_to_equity":  item.get("debtEquityRatio"),
        }
        for item in data
    ]


def get_key_metrics(ticker: str, api_key: str) -> Optional[dict]:
    """Returns current key metrics: ROE, ROIC, P/E, P/FCF."""
    data = _get(f"key-metrics-ttm/{ticker}", api_key)
    if not data:
        return None
    item = data[0] if data else {}
    return {
        "roe":       item.get("roeTTM"),
        "roic":      item.get("roicTTM"),
        "pe_ratio":  item.get("peRatioTTM"),
        "pfcf":      item.get("pfcfRatioTTM"),
        "ev_ebitda": item.get("enterpriseValueOverEBITDATTM"),
    }


def get_earnings_surprises(ticker: str, api_key: str, quarters: int = 4) -> list[dict]:
    """
    Returns actual vs. estimated EPS for the last N quarters.
    Positive surprise = beat, negative = miss.
    """
    data = _get(f"earnings-surprises/{ticker}", api_key)
    if not data:
        return []
    results = []
    for item in data[:quarters]:
        actual = item.get("actualEarningResult")
        estimated = item.get("estimatedEarning")
        surprise = None
        if actual is not None and estimated not in (None, 0):
            surprise = round(((actual - estimated) / abs(estimated)) * 100, 2)
        results.append({
            "date":               item.get("date"),
            "actual_eps":         actual,
            "estimated_eps":      estimated,
            "surprise_pct":       surprise,
            "beat":               actual > estimated if (actual and estimated) else None,
        })
    return results
