"""Tests for macro.macro_context_summary — no API calls required."""

from data.macro import macro_context_summary


def test_header_always_present():
    result = macro_context_summary([])
    assert result.startswith("Current macroeconomic context:")


def test_value_formatted_to_two_decimals():
    snapshots = [{"indicator": "fed_funds_rate", "value": 5.3, "direction": "flat"}]
    result = macro_context_summary(snapshots)
    assert "5.30" in result


def test_none_value_shown_as_na():
    snapshots = [{"indicator": "treasury_10y", "value": None, "direction": "rising"}]
    result = macro_context_summary(snapshots)
    assert "n/a" in result


def test_none_direction_shown_as_unknown():
    snapshots = [{"indicator": "cpi_yoy", "value": 3.1, "direction": None}]
    result = macro_context_summary(snapshots)
    assert "unknown" in result


def test_indicator_name_title_cased():
    snapshots = [{"indicator": "fed_funds_rate", "value": 5.0, "direction": "flat"}]
    result = macro_context_summary(snapshots)
    assert "Fed Funds Rate" in result


def test_all_five_indicators_produce_six_lines():
    snapshots = [
        {"indicator": "fed_funds_rate",     "value": 5.33, "direction": "flat"},
        {"indicator": "cpi_yoy",             "value": 3.10, "direction": "rising"},
        {"indicator": "treasury_10y",        "value": 4.20, "direction": "falling"},
        {"indicator": "industrial_prod",     "value": 103.5, "direction": "rising"},
        {"indicator": "consumer_sentiment",  "value": 67.8,  "direction": "falling"},
    ]
    lines = macro_context_summary(snapshots).strip().split("\n")
    assert len(lines) == 6  # header + 5 indicators


def test_direction_included_in_output():
    snapshots = [{"indicator": "fed_funds_rate", "value": 5.0, "direction": "rising"}]
    result = macro_context_summary(snapshots)
    assert "rising" in result
