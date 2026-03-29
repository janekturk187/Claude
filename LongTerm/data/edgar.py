"""
edgar.py — fetches SEC filings from the EDGAR full-text search API (free).

Retrieves 10-K, 10-Q, and 8-K filings for a given ticker and returns
the filing text for Claude to analyze.
"""

import logging
import threading
import time
from typing import Optional

from data import _http

logger = logging.getLogger(__name__)

_EDGAR_BASE = "https://data.sec.gov"

# SEC requires a real User-Agent. Call set_user_agent() at startup with a
# value from config so the SEC can contact you if your bot misbehaves.
_HEADERS = {"User-Agent": "LongTermAnalysis contact@example.com"}

# Ticker -> zero-padded CIK map, loaded once per process from SEC's JSON file.
# _TICKER_MAP_LOCK ensures the ~1 MB JSON is fetched exactly once even when
# multiple ticker threads call _get_cik concurrently on first run.
_TICKER_MAP: dict[str, str] = {}
_TICKER_MAP_LOCK = threading.Lock()

# SEC rate limit: 10 requests/sec. Enforce a minimum interval across all
# threads so parallel workers can't collectively exceed the limit.
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_TIME: float = 0.0
_MIN_REQUEST_INTERVAL = 0.11  # ~9 req/s — safely under the 10 req/s limit


def _rate_limited_get(url: str, **kwargs):
    """Wrapper around _http.get_with_retry that enforces the SEC rate limit."""
    global _LAST_REQUEST_TIME
    with _RATE_LOCK:
        wait = _MIN_REQUEST_INTERVAL - (time.time() - _LAST_REQUEST_TIME)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_TIME = time.time()
    return _http.get_with_retry(url, **kwargs)


def set_user_agent(user_agent: str) -> None:
    """Set the User-Agent header for all EDGAR requests (call once at startup)."""
    global _HEADERS
    _HEADERS = {"User-Agent": user_agent}


def _load_ticker_map() -> dict[str, str]:
    """
    Load and cache the full SEC company-tickers map.
    The JSON (~1 MB) is fetched once per process and reused for all tickers.
    Thread-safe: concurrent callers block until the first fetch completes.
    """
    global _TICKER_MAP
    if _TICKER_MAP:
        return _TICKER_MAP
    with _TICKER_MAP_LOCK:
        if _TICKER_MAP:  # re-check inside lock — another thread may have populated it
            return _TICKER_MAP
        try:
            resp = _rate_limited_get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=_HEADERS,
                timeout=10,
            )
            _TICKER_MAP = {
                entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
                for entry in resp.json().values()
                if entry.get("ticker")
            }
            logger.debug("Loaded %d tickers from SEC company_tickers.json", len(_TICKER_MAP))
        except Exception as e:
            logger.error("Failed to load SEC ticker map: %s", e)
    return _TICKER_MAP


def _get_cik(ticker: str) -> Optional[str]:
    """Resolve a ticker symbol to a zero-padded SEC CIK number."""
    return _load_ticker_map().get(ticker.upper())


def get_recent_filings(ticker: str, form_type: str = "10-K", count: int = 2) -> list[dict]:
    """
    Fetch metadata for the most recent filings of a given type.

    Returns a list of dicts with keys:
        ticker, cik, form_type, filing_date, accession_number, document_url
    """
    cik = _get_cik(ticker)
    if not cik:
        return []

    try:
        url = f"{_EDGAR_BASE}/submissions/CIK{cik}.json"
        resp = _rate_limited_get(url, headers=_HEADERS, timeout=15)
        data = resp.json()

        filings      = data.get("filings", {}).get("recent", {})
        forms        = filings.get("form", [])
        dates        = filings.get("filingDate", [])
        accessions   = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])

        results = []
        for form, date, accession, primary_doc in zip(forms, dates, accessions, primary_docs):
            if form == form_type:
                acc_clean = accession.replace("-", "")
                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{acc_clean}/{primary_doc}"
                )
                results.append({
                    "ticker":           ticker,
                    "cik":              cik,
                    "form_type":        form,
                    "filing_date":      date,
                    "accession_number": accession,
                    "document_url":     doc_url,
                })
                if len(results) >= count:
                    break

        logger.debug("Found %d %s filings for %s", len(results), form_type, ticker)
        return results

    except Exception as e:
        logger.error("Failed to fetch filings for %s: %s", ticker, e)
        return []


def fetch_filing_text(filing: dict, max_chars: int = 30000) -> Optional[str]:
    """
    Download and return the plain text of a filing, truncated to max_chars.
    Uses the primary document URL resolved during get_recent_filings.
    """
    text_url = filing.get("document_url", "")
    if not text_url:
        logger.error("No document_url in filing dict for %s", filing.get("accession_number"))
        return None

    try:
        resp = _rate_limited_get(text_url, headers=_HEADERS, timeout=30)
        text = resp.text[:max_chars]
        logger.debug("Fetched filing %s (%d chars)", filing["accession_number"], len(text))
        return text
    except Exception as e:
        logger.error("Failed to fetch filing text for %s: %s", filing["accession_number"], e)
        return None
