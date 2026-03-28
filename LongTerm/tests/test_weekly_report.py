"""Tests for weekly_report.generate — uses a real Storage with tmp_path."""

import os
import pytest
from storage import Storage
from reports.weekly_report import generate

_PROFILE = {
    "revenue_trend": "growing", "margin_trend": "expanding",
    "key_risks": [], "key_opportunities": [],
    "management_tone": "confident", "guidance_direction": "raised",
    "thesis_score": 8, "thesis_summary": "Strong moat.",
    "raw_response": "{}",
}

_SCORE = {
    "revenue_beat": True, "eps_beat": True,
    "guidance_direction": "raised", "quality_score": 9,
    "raw_response": "{}",
}


@pytest.fixture
def db(tmp_path):
    return Storage(str(tmp_path / "test.db"))


@pytest.fixture
def output_dir(tmp_path):
    return str(tmp_path / "reports")


def test_report_file_is_created(db, output_dir):
    path = generate(db, ["AAPL"], output_dir)
    assert os.path.exists(path)
    assert path.endswith(".md")


def test_report_contains_header(db, output_dir):
    content = open(generate(db, ["AAPL"], output_dir)).read()
    assert "# Weekly Research Report" in content
    assert "Generated:" in content


def test_report_shows_no_data_placeholders_when_empty(db, output_dir):
    content = open(generate(db, ["AAPL"], output_dir)).read()
    assert "No active theses on record" in content
    assert "No macro data available" in content


def test_report_shows_active_thesis(db, output_dir):
    db.save_thesis("NVDA", "AI infra play", ["Margins > 70%"])
    content = open(generate(db, ["NVDA"], output_dir)).read()
    assert "NVDA" in content
    assert "AI infra play" in content


def test_report_highlights_flagged_thesis(db, output_dir):
    tid = db.save_thesis("TSLA", "EV growth", ["Market share expanding"])
    db.flag_thesis(tid, "Margins collapsed")
    content = open(generate(db, ["TSLA"], output_dir)).read()
    assert "FLAGGED" in content
    assert "Margins collapsed" in content


def test_report_shows_earnings_table(db, output_dir):
    db.save_earnings_score("AAPL", "Q1 2026", _SCORE)
    content = open(generate(db, ["AAPL"], output_dir)).read()
    assert "Earnings Quality Trends" in content
    assert "Beat Streak" in content
    assert "AAPL" in content


def test_report_shows_beat_streak(db, output_dir):
    for i, period in enumerate(["Q4 2025", "Q3 2025", "Q2 2025"]):
        db.save_earnings_score("AAPL", period, {**_SCORE, "eps_beat": True})
    content = open(generate(db, ["AAPL"], output_dir)).read()
    assert "3Q" in content


def test_report_shows_company_profiles(db, output_dir):
    db.save_company_profile("AAPL", "10-K", "FY2025", _PROFILE)
    content = open(generate(db, ["AAPL"], output_dir)).read()
    assert "Latest Company Profile Scores" in content
    assert "growing" in content


def test_report_shows_macro_data(db, output_dir):
    db.save_macro("fed_funds_rate", 5.33, "falling")
    content = open(generate(db, ["AAPL"], output_dir)).read()
    assert "Macro Environment" in content
    assert "5.33" in content
    assert "falling" in content


def test_report_disclaimer_present(db, output_dir):
    content = open(generate(db, ["AAPL"], output_dir)).read()
    assert "Not financial advice" in content


def test_multiple_tickers_all_appear(db, output_dir):
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        db.save_earnings_score(ticker, "Q1 2026", _SCORE)
    content = open(generate(db, ["AAPL", "MSFT", "NVDA"], output_dir)).read()
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        assert ticker in content
