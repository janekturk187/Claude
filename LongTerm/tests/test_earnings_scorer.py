"""Tests for earnings_scorer.consecutive_beats — no API calls required."""

from analysis.earnings_scorer import consecutive_beats


def test_all_beats():
    history = [{"eps_beat": True}, {"eps_beat": True}, {"eps_beat": True}]
    assert consecutive_beats(history) == 3


def test_first_is_miss():
    history = [{"eps_beat": False}, {"eps_beat": True}, {"eps_beat": True}]
    assert consecutive_beats(history) == 0


def test_mixed_streak():
    history = [{"eps_beat": True}, {"eps_beat": True}, {"eps_beat": False}, {"eps_beat": True}]
    assert consecutive_beats(history) == 2


def test_empty_history():
    assert consecutive_beats([]) == 0


def test_single_beat():
    assert consecutive_beats([{"eps_beat": True}]) == 1


def test_single_miss():
    assert consecutive_beats([{"eps_beat": False}]) == 0


def test_none_value_treated_as_miss():
    history = [{"eps_beat": None}, {"eps_beat": True}]
    assert consecutive_beats(history) == 0


def test_missing_key_treated_as_miss():
    history = [{"quality_score": 8}, {"eps_beat": True}]
    assert consecutive_beats(history) == 0
