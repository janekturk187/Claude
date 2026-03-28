"""Tests for the Storage layer using a temporary on-disk database."""

import pytest
from storage import Storage


@pytest.fixture
def db(tmp_path):
    return Storage(str(tmp_path / "test.db"))


_PROFILE = {
    "revenue_trend":     "growing",
    "margin_trend":      "expanding",
    "key_risks":         ["competition", "regulation"],
    "key_opportunities": ["AI tailwind"],
    "management_tone":   "confident",
    "guidance_direction": "raised",
    "thesis_score":      8,
    "thesis_summary":    "Strong company with durable moat.",
    "raw_response":      "{}",
}

_SCORE = {
    "revenue_beat":      True,
    "eps_beat":          True,
    "guidance_direction": "raised",
    "quality_score":     9,
    "raw_response":      "{}",
}


class TestCompanyProfiles:
    def test_save_and_retrieve(self, db):
        db.save_company_profile("AAPL", "10-K", "FY2025", _PROFILE)
        p = db.get_latest_profile("AAPL")
        assert p is not None
        assert p["ticker"] == "AAPL"
        assert p["thesis_score"] == 8
        assert p["revenue_trend"] == "growing"

    def test_returns_latest_when_multiple(self, db):
        db.save_company_profile("AAPL", "10-K", "FY2024", {**_PROFILE, "thesis_score": 6})
        db.save_company_profile("AAPL", "10-K", "FY2025", {**_PROFILE, "thesis_score": 8})
        p = db.get_latest_profile("AAPL")
        assert p["thesis_score"] == 8

    def test_unknown_ticker_returns_none(self, db):
        assert db.get_latest_profile("FAKE") is None

    def test_upsert_on_same_period(self, db):
        db.save_company_profile("AAPL", "10-K", "FY2025", _PROFILE)
        db.save_company_profile("AAPL", "10-K", "FY2025", {**_PROFILE, "thesis_score": 9})
        with db._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM company_profiles WHERE ticker='AAPL'"
            ).fetchone()[0]
        assert count == 1


class TestEarningsScores:
    def test_save_and_retrieve(self, db):
        db.save_earnings_score("MSFT", "Q1 2026", _SCORE)
        history = db.get_earnings_history("MSFT", n=1)
        assert len(history) == 1
        assert history[0]["ticker"] == "MSFT"
        assert history[0]["quality_score"] == 9
        assert history[0]["eps_beat"] == 1  # stored as integer

    def test_unknown_ticker_returns_empty(self, db):
        assert db.get_earnings_history("FAKE") == []

    def test_history_ordered_most_recent_first(self, db):
        db.save_earnings_score("AAPL", "Q1 2025", {**_SCORE, "quality_score": 6})
        db.save_earnings_score("AAPL", "Q2 2025", {**_SCORE, "quality_score": 8})
        history = db.get_earnings_history("AAPL", n=2)
        assert history[0]["quality_score"] == 8


class TestThesisLog:
    def test_save_and_retrieve(self, db):
        tid = db.save_thesis("NVDA", "AI infrastructure play", ["Margins > 70%"])
        assert tid is not None
        theses = db.get_active_theses()
        assert len(theses) == 1
        assert theses[0]["ticker"] == "NVDA"

    def test_flagged_thesis_appears_in_active(self, db):
        tid = db.save_thesis("TSLA", "EV dominance", ["Market share growing"])
        db.flag_thesis(tid, "Market share declining in China")
        theses = db.get_active_theses()
        assert len(theses) == 1
        assert theses[0]["status"] == "flagged"
        assert theses[0]["flag_reason"] == "Market share declining in China"

    def test_closed_thesis_excluded(self, db):
        tid = db.save_thesis("AAPL", "Services growth", ["Revenue diversification"])
        with db._connect() as conn:
            conn.execute("UPDATE thesis_log SET status='closed' WHERE id=?", (tid,))
        assert db.get_active_theses() == []

    def test_both_active_and_flagged_returned(self, db):
        t1 = db.save_thesis("AAPL", "thesis 1", ["assumption 1"])
        t2 = db.save_thesis("MSFT", "thesis 2", ["assumption 2"])
        db.flag_thesis(t2, "assumption broken")
        theses = db.get_active_theses()
        assert len(theses) == 2
        statuses = {t["ticker"]: t["status"] for t in theses}
        assert statuses["AAPL"] == "active"
        assert statuses["MSFT"] == "flagged"


class TestMacroSnapshots:
    def test_save_and_retrieve_latest(self, db):
        db.save_macro("fed_funds_rate", 5.0, "flat")
        db.save_macro("fed_funds_rate", 5.25, "rising")
        macro = db.get_latest_macro()
        fed = next(m for m in macro if m["indicator"] == "fed_funds_rate")
        assert fed["value"] == 5.25

    def test_pruning_keeps_last_n(self, db):
        for i in range(10):
            db.save_macro("fed_funds_rate", float(i), "rising", keep_last=5)
        with db._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM macro_snapshots WHERE indicator='fed_funds_rate'"
            ).fetchone()[0]
        assert count == 5

    def test_pruning_independent_per_indicator(self, db):
        for i in range(10):
            db.save_macro("fed_funds_rate", float(i), "rising", keep_last=3)
        for i in range(7):
            db.save_macro("cpi_yoy", float(i), "flat", keep_last=3)
        with db._connect() as conn:
            for indicator in ("fed_funds_rate", "cpi_yoy"):
                count = conn.execute(
                    "SELECT COUNT(*) FROM macro_snapshots WHERE indicator=?",
                    (indicator,),
                ).fetchone()[0]
                assert count == 3


class TestDeduplicationChecks:
    def test_has_company_profile_true(self, db):
        db.save_company_profile("AAPL", "10-K", "FY2025", _PROFILE)
        assert db.has_company_profile("AAPL", "10-K", "FY2025") is True

    def test_has_company_profile_false_wrong_period(self, db):
        db.save_company_profile("AAPL", "10-K", "FY2025", _PROFILE)
        assert db.has_company_profile("AAPL", "10-K", "FY2024") is False

    def test_has_company_profile_false_wrong_form(self, db):
        db.save_company_profile("AAPL", "10-K", "FY2025", _PROFILE)
        assert db.has_company_profile("AAPL", "10-Q", "FY2025") is False

    def test_has_company_profile_false_unknown_ticker(self, db):
        assert db.has_company_profile("FAKE", "10-K", "FY2025") is False

    def test_has_earnings_score_true(self, db):
        db.save_earnings_score("MSFT", "Q1 2026", _SCORE)
        assert db.has_earnings_score("MSFT", "Q1 2026") is True

    def test_has_earnings_score_false_wrong_period(self, db):
        db.save_earnings_score("MSFT", "Q1 2026", _SCORE)
        assert db.has_earnings_score("MSFT", "Q2 2026") is False

    def test_has_earnings_score_false_unknown_ticker(self, db):
        assert db.has_earnings_score("FAKE", "Q1 2026") is False

    def test_has_financials_true(self, db):
        data = {"revenue": 100, "gross_margin": 0.4, "operating_margin": 0.2,
                "free_cash_flow": 50, "debt_to_equity": 0.5, "roe": 0.3}
        db.save_financials("AAPL", "2026-01-01", data)
        assert db.has_financials("AAPL", "2026-01-01") is True

    def test_has_financials_false_wrong_period(self, db):
        data = {"revenue": 100, "gross_margin": 0.4, "operating_margin": 0.2,
                "free_cash_flow": 50, "debt_to_equity": 0.5, "roe": 0.3}
        db.save_financials("AAPL", "2026-01-01", data)
        assert db.has_financials("AAPL", "2025-10-01") is False

    def test_has_financials_false_unknown_ticker(self, db):
        assert db.has_financials("FAKE", "2026-01-01") is False


class TestFinancials:
    def test_save_and_upsert(self, db):
        data = {
            "revenue": 100, "gross_margin": 0.4, "operating_margin": 0.2,
            "free_cash_flow": 50, "debt_to_equity": 0.5, "roe": 0.3,
        }
        db.save_financials("AAPL", "Q1 2026", data)
        db.save_financials("AAPL", "Q1 2026", {**data, "revenue": 200})
        with db._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM financials WHERE ticker='AAPL'"
            ).fetchone()[0]
        assert count == 1
