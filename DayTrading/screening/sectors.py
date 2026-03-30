"""
sectors.py — lightweight sector mapping for screening diversification.

Static mapping covers the default screening universe and common large-caps.
Unknown tickers fall back to "other".
"""

SECTOR_MAP: dict[str, str] = {
    # Big Tech
    "AAPL": "tech", "MSFT": "tech", "GOOGL": "tech", "GOOG": "tech",
    "AMZN": "tech", "META": "tech", "NFLX": "tech",

    # Semiconductors
    "NVDA": "semiconductor", "AMD": "semiconductor", "INTC": "semiconductor",
    "QCOM": "semiconductor", "MU": "semiconductor", "AVGO": "semiconductor",
    "TSM": "semiconductor", "AMAT": "semiconductor", "LRCX": "semiconductor",
    "KLAC": "semiconductor", "MRVL": "semiconductor", "ON": "semiconductor",
    "TXN": "semiconductor", "ADI": "semiconductor", "ARM": "semiconductor",
    "MCHP": "semiconductor", "SWKS": "semiconductor",

    # Software / Cloud
    "CRM": "software", "ADBE": "software", "ORCL": "software",
    "NOW": "software", "PANW": "software", "CRWD": "software",
    "SNOW": "software", "DDOG": "software", "ZS": "software",
    "NET": "software", "SHOP": "software", "WDAY": "software",
    "TEAM": "software", "HUBS": "software", "BILL": "software",
    "MDB": "software", "ESTC": "software",

    # Fintech / Speculative Tech
    "PLTR": "fintech", "HOOD": "fintech", "COIN": "fintech",
    "RBLX": "fintech", "SNAP": "fintech", "SQ": "fintech",
    "SOFI": "fintech", "AFRM": "fintech", "ROKU": "fintech",
    "U": "fintech", "DASH": "fintech", "UBER": "fintech",
    "LYFT": "fintech", "DKNG": "fintech",

    # Financials
    "JPM": "financials", "GS": "financials", "BAC": "financials",
    "MS": "financials", "C": "financials", "WFC": "financials",
    "SCHW": "financials", "BLK": "financials", "AXP": "financials",
    "V": "financials", "MA": "financials", "PYPL": "financials",
    "COF": "financials", "USB": "financials",

    # Energy
    "XOM": "energy", "CVX": "energy", "OXY": "energy",
    "COP": "energy", "SLB": "energy", "EOG": "energy",
    "DVN": "energy", "MPC": "energy", "VLO": "energy",
    "PSX": "energy", "HAL": "energy",

    # Healthcare
    "UNH": "healthcare", "JNJ": "healthcare", "PFE": "healthcare",
    "MRNA": "healthcare", "LLY": "healthcare", "ABBV": "healthcare",
    "BMY": "healthcare", "MRK": "healthcare", "AMGN": "healthcare",
    "GILD": "healthcare", "REGN": "healthcare", "VRTX": "healthcare",
    "ISRG": "healthcare", "TMO": "healthcare", "ABT": "healthcare",
    "DHR": "healthcare", "BSX": "healthcare",

    # Consumer
    "TSLA": "consumer", "NKE": "consumer", "SBUX": "consumer",
    "MCD": "consumer", "DIS": "consumer", "COST": "consumer",
    "WMT": "consumer", "TGT": "consumer", "HD": "consumer",
    "LOW": "consumer", "LULU": "consumer", "CMG": "consumer",
    "KO": "consumer", "PEP": "consumer", "PG": "consumer",
    "ABNB": "consumer", "BKNG": "consumer", "MAR": "consumer",

    # Industrials / Aerospace
    "BA": "industrials", "CAT": "industrials", "DE": "industrials",
    "GE": "industrials", "HON": "industrials", "LMT": "industrials",
    "RTX": "industrials", "UPS": "industrials", "FDX": "industrials",
    "MMM": "industrials", "UNP": "industrials",

    # ETFs
    "SPY": "etf", "QQQ": "etf", "IWM": "etf", "DIA": "etf",
    "XLF": "etf", "XLE": "etf", "XLK": "etf", "XLV": "etf",
    "ARKK": "etf", "SOXL": "etf", "TQQQ": "etf", "SMH": "etf",
}


def get_sector(ticker: str) -> str:
    """Return the sector for a ticker, or 'other' if not mapped."""
    return SECTOR_MAP.get(ticker, "other")
