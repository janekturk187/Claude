"""Tests for screening/screener.py — no real API calls."""

import pytest
from unittest.mock import MagicMock

from screening.screener import score_snapshot, pick_tickers, _apply_sector_cap


def _cfg(min_gap=2.0, min_vol=500_000, min_price=5.0, max_price=500.0,
         max_picks=3, min_rvol=0.0, max_per_sector=0):
    cfg = MagicMock()
    cfg.min_gap_pct = min_gap
    cfg.min_avg_daily_volume = min_vol
    cfg.min_price = min_price
    cfg.max_price = max_price
    cfg.max_picks = max_picks
    cfg.min_rvol = min_rvol
    cfg.max_per_sector = max_per_sector
    return cfg


def _snapshot(prev_close=100.0, current_price=103.0, prev_volume=1_000_000,
              daily_volume=50_000):
    snap = MagicMock()
    snap.prev_daily_bar.close = prev_close
    snap.prev_daily_bar.volume = prev_volume
    snap.daily_bar.volume = daily_volume
    snap.latest_trade.price = current_price
    return snap


class TestScoreSnapshot:
    def test_valid_gap_up_returns_result(self):
        result = score_snapshot("AAPL", _snapshot(100.0, 103.0), _cfg())
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["gap_pct"] == pytest.approx(3.0, rel=0.01)
        assert result["direction"] == "up"

    def test_valid_gap_down_returns_result(self):
        result = score_snapshot("AAPL", _snapshot(100.0, 97.0), _cfg())
        assert result is not None
        assert result["direction"] == "down"
        assert result["gap_pct"] == pytest.approx(-3.0, rel=0.01)

    def test_gap_too_small_returns_none(self):
        result = score_snapshot("AAPL", _snapshot(100.0, 101.0), _cfg(min_gap=2.0))
        assert result is None

    def test_gap_exactly_at_threshold_passes(self):
        result = score_snapshot("AAPL", _snapshot(100.0, 102.0), _cfg(min_gap=2.0))
        assert result is not None

    def test_volume_too_low_returns_none(self):
        result = score_snapshot("AAPL", _snapshot(prev_volume=100_000), _cfg(min_vol=500_000))
        assert result is None

    def test_price_below_minimum_returns_none(self):
        result = score_snapshot("AAPL", _snapshot(prev_close=3.0, current_price=3.10), _cfg(min_price=5.0))
        assert result is None

    def test_price_above_maximum_returns_none(self):
        result = score_snapshot("AAPL", _snapshot(prev_close=600.0, current_price=620.0), _cfg(max_price=500.0))
        assert result is None

    def test_missing_prev_close_returns_none(self):
        snap = MagicMock()
        snap.prev_daily_bar = None
        snap.daily_bar = None
        snap.latest_trade.price = 100.0
        assert score_snapshot("AAPL", snap, _cfg()) is None

    def test_missing_latest_trade_returns_none(self):
        snap = MagicMock()
        snap.prev_daily_bar.close = 100.0
        snap.prev_daily_bar.volume = 1_000_000
        snap.daily_bar.volume = 50_000
        snap.latest_trade = None
        assert score_snapshot("AAPL", snap, _cfg()) is None

    def test_zero_prev_close_returns_none(self):
        result = score_snapshot("AAPL", _snapshot(prev_close=0, current_price=5.0), _cfg())
        assert result is None

    def test_score_higher_for_larger_gap(self):
        small_gap = score_snapshot("A", _snapshot(100.0, 102.5), _cfg())
        large_gap = score_snapshot("B", _snapshot(100.0, 106.0), _cfg())
        assert large_gap["score"] > small_gap["score"]

    def test_score_higher_for_more_volume(self):
        low_vol  = score_snapshot("A", _snapshot(100.0, 103.0, prev_volume=500_000), _cfg())
        high_vol = score_snapshot("B", _snapshot(100.0, 103.0, prev_volume=10_000_000), _cfg())
        assert high_vol["score"] > low_vol["score"]

    def test_result_contains_expected_fields(self):
        result = score_snapshot("AAPL", _snapshot(), _cfg())
        for field in ("ticker", "gap_pct", "direction", "current_price",
                      "prev_close", "prev_volume", "rvol", "sector", "score"):
            assert field in result

    def test_rvol_calculated_correctly(self):
        result = score_snapshot("AAPL", _snapshot(prev_volume=1_000_000, daily_volume=50_000), _cfg())
        assert result["rvol"] == pytest.approx(0.05, rel=0.01)

    def test_higher_rvol_boosts_score(self):
        low_rvol  = score_snapshot("A", _snapshot(100.0, 103.0, daily_volume=10_000), _cfg())
        high_rvol = score_snapshot("B", _snapshot(100.0, 103.0, daily_volume=200_000), _cfg())
        assert high_rvol["score"] > low_rvol["score"]

    def test_min_rvol_filter_excludes_low_rvol(self):
        # daily_volume=10_000 / prev_volume=1_000_000 = 0.01 rvol
        result = score_snapshot("AAPL", _snapshot(daily_volume=10_000), _cfg(min_rvol=0.05))
        assert result is None

    def test_min_rvol_filter_passes_high_rvol(self):
        # daily_volume=100_000 / prev_volume=1_000_000 = 0.10 rvol
        result = score_snapshot("AAPL", _snapshot(daily_volume=100_000), _cfg(min_rvol=0.05))
        assert result is not None

    def test_missing_daily_bar_rvol_zero(self):
        snap = _snapshot()
        snap.daily_bar = None
        result = score_snapshot("AAPL", snap, _cfg())
        assert result is not None
        assert result["rvol"] == 0.0

    def test_sector_assigned(self):
        result = score_snapshot("NVDA", _snapshot(), _cfg())
        assert result["sector"] == "semiconductor"

    def test_unknown_ticker_sector_is_other(self):
        result = score_snapshot("ZZZZZ", _snapshot(), _cfg())
        assert result["sector"] == "other"


class TestPickTickers:
    def test_empty_snapshots_returns_empty(self):
        assert pick_tickers({}, _cfg()) == []

    def test_returns_at_most_max_picks(self):
        snapshots = {f"T{i}": _snapshot(100.0, 103.0 + i) for i in range(10)}
        picks = pick_tickers(snapshots, _cfg(max_picks=3))
        assert len(picks) <= 3

    def test_sorted_by_score_descending(self):
        snapshots = {
            "LOW":  _snapshot(100.0, 102.5),
            "HIGH": _snapshot(100.0, 108.0),
            "MID":  _snapshot(100.0, 104.0),
        }
        picks = pick_tickers(snapshots, _cfg(max_picks=3))
        scores = [p["score"] for p in picks]
        assert scores == sorted(scores, reverse=True)

    def test_tickers_below_gap_threshold_excluded(self):
        snapshots = {
            "SMALL": _snapshot(100.0, 100.5),
            "BIG":   _snapshot(100.0, 105.0),
        }
        picks = pick_tickers(snapshots, _cfg(min_gap=2.0))
        assert all(p["ticker"] != "SMALL" for p in picks)
        assert any(p["ticker"] == "BIG" for p in picks)

    def test_returns_empty_when_none_pass_filters(self):
        snapshots = {"A": _snapshot(100.0, 100.5), "B": _snapshot(100.0, 101.0)}
        picks = pick_tickers(snapshots, _cfg(min_gap=5.0))
        assert picks == []


class TestSectorCap:
    def test_sector_cap_limits_per_sector(self):
        # All three are "tech" sector
        candidates = [
            {"ticker": "AAPL", "sector": "tech", "score": 10},
            {"ticker": "MSFT", "sector": "tech", "score": 9},
            {"ticker": "META", "sector": "tech", "score": 8},
            {"ticker": "JPM",  "sector": "financials", "score": 7},
        ]
        picks = _apply_sector_cap(candidates, max_per_sector=2, max_picks=5)
        tech_picks = [p for p in picks if p["sector"] == "tech"]
        assert len(tech_picks) == 2
        # JPM should be included since financials has room
        assert any(p["ticker"] == "JPM" for p in picks)

    def test_sector_cap_zero_means_no_cap(self):
        candidates = [
            {"ticker": "AAPL", "sector": "tech", "score": 10},
            {"ticker": "MSFT", "sector": "tech", "score": 9},
            {"ticker": "META", "sector": "tech", "score": 8},
        ]
        # max_per_sector=0 isn't used by _apply_sector_cap directly —
        # pick_tickers skips the call when max_per_sector=0
        picks = _apply_sector_cap(candidates, max_per_sector=100, max_picks=5)
        assert len(picks) == 3

    def test_sector_cap_respects_max_picks(self):
        candidates = [
            {"ticker": f"T{i}", "sector": f"sector_{i}", "score": 10 - i}
            for i in range(10)
        ]
        picks = _apply_sector_cap(candidates, max_per_sector=2, max_picks=3)
        assert len(picks) == 3

    def test_sector_cap_skips_over_capped_sector(self):
        candidates = [
            {"ticker": "NVDA", "sector": "semiconductor", "score": 10},
            {"ticker": "AMD",  "sector": "semiconductor", "score": 9},
            {"ticker": "INTC", "sector": "semiconductor", "score": 8},
            {"ticker": "XOM",  "sector": "energy", "score": 7},
            {"ticker": "CVX",  "sector": "energy", "score": 6},
        ]
        picks = _apply_sector_cap(candidates, max_per_sector=1, max_picks=3)
        tickers = [p["ticker"] for p in picks]
        assert tickers == ["NVDA", "XOM"]  # only 2 unique sectors available

    def test_diverse_sectors_all_pass(self):
        candidates = [
            {"ticker": "AAPL", "sector": "tech", "score": 10},
            {"ticker": "JPM",  "sector": "financials", "score": 9},
            {"ticker": "XOM",  "sector": "energy", "score": 8},
            {"ticker": "UNH",  "sector": "healthcare", "score": 7},
        ]
        picks = _apply_sector_cap(candidates, max_per_sector=2, max_picks=4)
        assert len(picks) == 4
