"""
edgar.py — fetches SEC filings from the EDGAR full-text search API (free).

Retrieves 10-K, 10-Q, and 8-K filings for a given ticker and returns
the filing text for Claude to analyze.
"""

import logging
import time
import requests
from typing import Optional

logger = logging.getLogger(__name__)

_EDGAR_BASE = "https://data.sec.gov"
_HEADERS = {"User-Agent": "PelosiResearch research@example.com"}  # SEC requires a User-Agent


def _get_cik(ticker: str) -> Optional[str]:
    """Resolve a ticker symbol to an SEC CIK number."""
    try:
        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&startdt=2020-01-01&forms=10-K".format(ticker),
            headers=_HEADERS,
            timeout=10,
        )
        # Use the company tickers JSON endpoint instead — more reliable
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
    except Exception as e:
        logger.error("CIK lookup failed for %s: %s", ticker, e)
    return None


def get_recent_filings(ticker: str, form_type: str = "10-K", count: int = 2) -> list[dict]:
    """
    Fetch metadata for the most recent filings of a given type.

    Returns a list of dicts with keys: accession_number, filing_date, form_type, document_url
    """
    cik = _get_cik(ticker)
    if not cik:
        return []

    try:
        url = f"{_EDGAR_BASE}/submissions/CIK{cik}.json"
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        dates   = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])

        results = []
        for form, date, accession in zip(forms, dates, accessions):
            if form == form_type:
                acc_clean = accession.replace("-", "")
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.htm"
                results.append({
                    "ticker":           ticker,
                    "form_type":        form,
                    "filing_date":      date,
                    "accession_number": accession,
                    "index_url":        doc_url,
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
    SEC EDGAR provides .txt versions of all filings.
    """
    accession = filing["accession_number"].replace("-", "")
    cik_url_part = filing.get("cik", "")
    # Construct the primary document URL — fall back to index page if needed
    text_url = filing.get("text_url") or filing.get("index_url", "")

    try:
        resp = requests.get(text_url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        text = resp.text[:max_chars]
        logger.debug("Fetched filing %s (%d chars)", filing["accession_number"], len(text))
        time.sleep(0.1)  # SEC rate limit: 10 requests/sec max
        return text
    except Exception as e:
        logger.error("Failed to fetch filing text for %s: %s", filing["accession_number"], e)
        return None
