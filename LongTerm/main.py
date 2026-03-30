"""
main.py — Long-Term Investment Analysis System entry point.

Runs on a scheduled basis (not a live loop):
  - Fetches SEC filings and sends them to Claude for analysis
  - Pulls financial statement data from FMP
  - Refreshes macro indicators from FRED
  - Checks active theses for assumption violations
  - Generates a weekly report every Sunday

Usage:
    ANTHROPIC_API_KEY=<key> python main.py              # run full cycle now
    ANTHROPIC_API_KEY=<key> python main.py --report     # weekly report only
    ANTHROPIC_API_KEY=<key> python main.py --ticker AAPL # single ticker only
    ANTHROPIC_API_KEY=<key> python main.py --schedule   # run on cron schedule
"""

import argparse
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import schedule

from loadconfig import load_config
from storage import Storage
from data import edgar, financials, macro
from analysis import document_analyzer, earnings_scorer, valuation
from portfolio import thesis_monitor
from alerts import email_alert
from reports import weekly_report

logger = logging.getLogger(__name__)

# Per-ticker locks prevent the thread pool from analyzing the same ticker
# concurrently when the same ticker appears in multiple scheduled cycles.
_ticker_locks: dict[str, threading.Lock] = {}
_ticker_locks_guard = threading.Lock()


def _get_ticker_lock(ticker: str) -> threading.Lock:
    with _ticker_locks_guard:
        if ticker not in _ticker_locks:
            _ticker_locks[ticker] = threading.Lock()
        return _ticker_locks[ticker]


def run_filing_analysis(ticker: str, db: Storage, cfg, force: bool = False):
    """Fetch the latest 10-K and 10-Q for a ticker and analyze with Claude."""
    macro_snaps = db.get_latest_macro()
    from data.macro import macro_context_summary
    macro_ctx = macro_context_summary(macro_snaps) if macro_snaps else ""

    for form in ("10-K", "10-Q"):
        filings = edgar.get_recent_filings(ticker, form_type=form, count=1)
        if not filings:
            logger.warning("No %s filings found for %s", form, ticker)
            continue

        filing = filings[0]
        if not force and db.has_company_profile(ticker, form, filing["filing_date"]):
            logger.info("Skipping %s %s %s — already in database", ticker, form, filing["filing_date"])
            continue

        text = edgar.fetch_filing_text(filing)
        if not text:
            continue

        result = document_analyzer.analyze_filing(
            ticker=ticker,
            filing_type=form,
            period=filing["filing_date"],
            text=text,
            cfg=cfg.claude,
            macro_context=macro_ctx,
        )
        if result:
            db.save_company_profile(ticker, form, filing["filing_date"], result)


def run_earnings_analysis(ticker: str, db: Storage, cfg, force: bool = False):
    """Score the latest earnings report for a ticker."""
    income = financials.get_income_statement(ticker, cfg.fmp.api_key, quarters=4)
    surprises = financials.get_earnings_surprises(ticker, cfg.fmp.api_key, quarters=4)

    if not income:
        logger.warning("No income statement data for %s", ticker)
        return

    period = income[0].get("period", "latest")
    if not force and db.has_earnings_score(ticker, period):
        logger.info("Skipping earnings score for %s %s — already in database", ticker, period)
    else:
        result = earnings_scorer.score(ticker, period, income, surprises, cfg.claude)
        if result:
            db.save_earnings_score(ticker, period, result)

    fin_period = income[0].get("date", period)
    if not force and db.has_financials(ticker, fin_period):
        logger.info("Skipping financials for %s %s — already in database", ticker, fin_period)
    else:
        cashflow = financials.get_cash_flow(ticker, cfg.fmp.api_key, quarters=1)
        balance = financials.get_balance_sheet(ticker, cfg.fmp.api_key, quarters=1)
        if income and cashflow and balance:
            merged = {
                **{k: income[0].get(k) for k in ("revenue", "gross_margin", "operating_margin")},
                "free_cash_flow": cashflow[0].get("free_cash_flow") if cashflow else None,
                "debt_to_equity": balance[0].get("debt_to_equity") if balance else None,
                "roe": None,
            }
            metrics = financials.get_key_metrics(ticker, cfg.fmp.api_key)
            if metrics:
                merged["roe"] = metrics.get("roe")
            db.save_financials(ticker, fin_period, merged)


def run_valuation_analysis(ticker: str, db: Storage, cfg, force: bool = False):
    """Fetch key metrics and ask Claude to grade the valuation."""
    from datetime import date
    period = date.today().isoformat()
    if not force and db.has_valuation(ticker, period):
        logger.info("Skipping valuation for %s %s — already in database", ticker, period)
        return
    metrics = financials.get_key_metrics(ticker, cfg.fmp.api_key)
    if not metrics:
        logger.warning("No key metrics for %s — skipping valuation", ticker)
        return
    result = valuation.assess(ticker, metrics, cfg.claude)
    if result:
        db.save_valuation(ticker, period, result)
        logger.info("Valuation for %s: %s", ticker, result.get("valuation_grade"))


def run_macro_refresh(db: Storage, cfg):
    """Refresh all macro indicators from FRED."""
    snaps = macro.fetch_all(cfg.fred.api_key)
    for s in snaps:
        db.save_macro(s["indicator"], s["value"], s["direction"])
    logger.info("Macro snapshot updated (%d indicators)", len(snaps))


def run_thesis_check(db: Storage, cfg):
    """Check all active theses against latest data and alert on flags."""
    results = thesis_monitor.check_all(db, cfg.claude)
    flagged = [r for r in results if r.get("flag")]
    if flagged:
        logger.warning("%d thesis(es) flagged — review required", len(flagged))
        active = {t["id"]: t for t in db.get_active_theses()}
        for r in flagged:
            thesis = active.get(r.get("thesis_id"), {})
            email_alert.send_flag_alert(
                ticker=r["ticker"],
                flag_reason=r.get("flag_reason", ""),
                thesis_text=thesis.get("thesis_text", ""),
                cfg=cfg.alerts.email,
            )
    else:
        logger.info("All active theses checked — no flags")


def run_weekly_report(db: Storage, cfg):
    """Generate and write the weekly report."""
    path = weekly_report.generate(db, cfg.tickers, cfg.reports_dir,
                                  fmp_api_key=cfg.fmp.api_key)
    logger.info("Weekly report: %s", path)


def full_cycle(db: Storage, cfg, tickers: list, force: bool = False):
    """Run a complete analysis cycle for all tickers."""
    logger.info("Starting full analysis cycle for: %s", tickers)

    run_macro_refresh(db, cfg)

    def _analyze(ticker: str):
        lock = _get_ticker_lock(ticker)
        if not lock.acquire(blocking=False):
            logger.warning("Skipping %s — analysis already in progress", ticker)
            return
        try:
            logger.info("--- Analyzing %s ---", ticker)
            run_filing_analysis(ticker, db, cfg, force=force)
            run_earnings_analysis(ticker, db, cfg, force=force)
            run_valuation_analysis(ticker, db, cfg, force=force)
        finally:
            lock.release()

    failed = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_analyze, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            exc = future.exception()
            if exc:
                logger.error("Cycle failed for %s: %s", ticker, exc)
                failed.append(ticker)

    if failed:
        logger.warning(
            "Cycle finished with errors — %d/%d tickers failed: %s",
            len(failed), len(tickers), failed,
        )
    else:
        logger.info("Cycle finished — all %d tickers completed successfully", len(tickers))

    run_thesis_check(db, cfg)
    logger.info("Full cycle complete")


def main():
    parser = argparse.ArgumentParser(description="Long-Term Investment Analysis System")
    parser.add_argument("--report", action="store_true", help="Generate weekly report only")
    parser.add_argument("--ticker", help="Run analysis for a single ticker only")
    parser.add_argument("--force", action="store_true",
                        help="Re-analyze even if a filing/score is already in the database")
    parser.add_argument("--schedule", action="store_true",
                        help="Run on automated schedule (blocking)")
    args = parser.parse_args()

    cfg = load_config("config.json")

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    edgar.set_user_agent(cfg.sec.user_agent)

    db = Storage(cfg.db_path)
    tickers = [args.ticker] if args.ticker else cfg.tickers

    if args.report:
        run_weekly_report(db, cfg)
        return

    if args.force:
        logger.info("--force: skipping deduplication checks")

    if args.schedule:
        logger.info("Running on schedule — earnings check every %dh, macro every %dh, report on %s",
                    cfg.schedule.earnings_check_interval_hours,
                    cfg.schedule.macro_refresh_interval_hours,
                    cfg.schedule.weekly_report_day)

        schedule.every(cfg.schedule.earnings_check_interval_hours).hours.do(
            full_cycle, db=db, cfg=cfg, tickers=tickers
        )
        schedule.every(cfg.schedule.macro_refresh_interval_hours).hours.do(
            run_macro_refresh, db=db, cfg=cfg
        )
        schedule.every().week.do(run_weekly_report, db=db, cfg=cfg)

        # Run once immediately on startup
        full_cycle(db, cfg, tickers, force=args.force)

        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        # Single run
        full_cycle(db, cfg, tickers, force=args.force)


if __name__ == "__main__":
    main()
