"""Tests for edgar CIK resolution and ticker-map caching."""

import pytest
from unittest.mock import patch, MagicMock

import data.edgar as edgar


_TICKERS_JSON = {
    "0": {"cik_str": 320193,  "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019,  "ticker": "MSFT", "title": "Microsoft Corp"},
    "2": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
}


@pytest.fixture(autouse=True)
def clear_ticker_cache():
    """Reset the module-level ticker map between tests."""
    edgar._TICKER_MAP.clear()
    yield
    edgar._TICKER_MAP.clear()


def _mock_response(json_data):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


@patch("data._http.requests.get")
def test_get_cik_found(mock_get):
    mock_get.return_value = _mock_response(_TICKERS_JSON)
    assert edgar._get_cik("AAPL") == "0000320193"


@patch("data._http.requests.get")
def test_get_cik_case_insensitive(mock_get):
    mock_get.return_value = _mock_response(_TICKERS_JSON)
    assert edgar._get_cik("aapl") == "0000320193"
    assert edgar._get_cik("Msft") == "0000789019"


@patch("data._http.requests.get")
def test_get_cik_not_found_returns_none(mock_get):
    mock_get.return_value = _mock_response(_TICKERS_JSON)
    assert edgar._get_cik("FAKE") is None


@patch("data._http.requests.get")
def test_ticker_map_fetched_once(mock_get):
    mock_get.return_value = _mock_response(_TICKERS_JSON)
    edgar._get_cik("AAPL")
    edgar._get_cik("MSFT")
    edgar._get_cik("NVDA")
    assert mock_get.call_count == 1


@patch("data._http.requests.get")
def test_api_error_returns_none(mock_get):
    mock_get.side_effect = Exception("network error")
    assert edgar._get_cik("AAPL") is None


@patch("data._http.requests.get")
def test_cik_zero_padded_to_10_digits(mock_get):
    mock_get.return_value = _mock_response({"0": {"cik_str": 1, "ticker": "TEST"}})
    assert edgar._get_cik("TEST") == "0000000001"


@patch("data._http.requests.get")
def test_set_user_agent_changes_headers(mock_get):
    mock_get.return_value = _mock_response(_TICKERS_JSON)
    edgar.set_user_agent("TestApp test@example.com")
    edgar._get_cik("AAPL")
    called_kwargs = mock_get.call_args
    assert called_kwargs.kwargs.get("headers", {}).get("User-Agent") == "TestApp test@example.com"
