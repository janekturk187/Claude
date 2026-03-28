"""Tests for document_analyzer._validate_profile — no API calls required."""

import pytest
from analysis.document_analyzer import _validate_profile


class TestThesisScore:
    def test_clamped_high(self):
        r = {"thesis_score": 99}
        _validate_profile(r)
        assert r["thesis_score"] == 10

    def test_clamped_low(self):
        r = {"thesis_score": -5}
        _validate_profile(r)
        assert r["thesis_score"] == 1

    def test_valid_score_unchanged(self):
        r = {"thesis_score": 7}
        _validate_profile(r)
        assert r["thesis_score"] == 7

    def test_string_score_invalid_defaults_to_5(self):
        r = {"thesis_score": "bad"}
        _validate_profile(r)
        assert r["thesis_score"] == 5

    def test_none_score_defaults_to_5(self):
        r = {"thesis_score": None}
        _validate_profile(r)
        assert r["thesis_score"] == 5

    def test_float_score_is_cast(self):
        r = {"thesis_score": 8.9}
        _validate_profile(r)
        assert r["thesis_score"] == 8


class TestRevenueTrend:
    def test_unknown_defaults_to_stable(self):
        r = {"revenue_trend": "exploding"}
        _validate_profile(r)
        assert r["revenue_trend"] == "stable"

    def test_valid_values_unchanged(self):
        for v in ("growing", "stable", "declining"):
            r = {"revenue_trend": v}
            _validate_profile(r)
            assert r["revenue_trend"] == v


class TestMarginTrend:
    def test_unknown_defaults_to_stable(self):
        r = {"margin_trend": "unknown"}
        _validate_profile(r)
        assert r["margin_trend"] == "stable"

    def test_valid_values_unchanged(self):
        for v in ("expanding", "stable", "compressing"):
            r = {"margin_trend": v}
            _validate_profile(r)
            assert r["margin_trend"] == v


class TestManagementTone:
    def test_unknown_defaults_to_neutral(self):
        r = {"management_tone": "aggressive"}
        _validate_profile(r)
        assert r["management_tone"] == "neutral"

    def test_valid_values_unchanged(self):
        for v in ("confident", "cautious", "defensive", "neutral"):
            r = {"management_tone": v}
            _validate_profile(r)
            assert r["management_tone"] == v


class TestGuidanceDirection:
    def test_unknown_defaults_to_none(self):
        r = {"guidance_direction": "sideways"}
        _validate_profile(r)
        assert r["guidance_direction"] == "none"

    def test_valid_values_unchanged(self):
        for v in ("raised", "maintained", "lowered", "none"):
            r = {"guidance_direction": v}
            _validate_profile(r)
            assert r["guidance_direction"] == v


class TestListFields:
    def test_non_list_risks_replaced_with_empty(self):
        r = {"key_risks": "many risks"}
        _validate_profile(r)
        assert r["key_risks"] == []

    def test_none_opportunities_replaced_with_empty(self):
        r = {"key_opportunities": None}
        _validate_profile(r)
        assert r["key_opportunities"] == []

    def test_valid_list_unchanged(self):
        r = {"key_risks": ["risk1", "risk2"]}
        _validate_profile(r)
        assert r["key_risks"] == ["risk1", "risk2"]

    def test_missing_fields_default_to_empty(self):
        r = {}
        _validate_profile(r)
        assert r["key_risks"] == []
        assert r["key_opportunities"] == []
