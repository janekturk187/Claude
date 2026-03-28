"""Tests for the _http retry helper."""

import pytest
from unittest.mock import patch, MagicMock, call

import requests as requests_lib
from data._http import get_with_retry


def _mock_resp(status, raise_on_raise_for_status=False):
    mock = MagicMock()
    mock.status_code = status
    if raise_on_raise_for_status:
        mock.raise_for_status.side_effect = requests_lib.HTTPError(f"HTTP {status}")
    else:
        mock.raise_for_status.return_value = None
    return mock


@patch("data._http.time.sleep")
@patch("data._http.requests.get")
def test_success_on_first_attempt(mock_get, mock_sleep):
    mock_get.return_value = _mock_resp(200)
    resp = get_with_retry("http://example.com")
    assert resp.status_code == 200
    mock_sleep.assert_not_called()
    assert mock_get.call_count == 1


@patch("data._http.time.sleep")
@patch("data._http.requests.get")
def test_retries_on_429_then_succeeds(mock_get, mock_sleep):
    mock_get.side_effect = [_mock_resp(429), _mock_resp(429), _mock_resp(200)]
    resp = get_with_retry("http://example.com", max_retries=3)
    assert resp.status_code == 200
    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


@patch("data._http.time.sleep")
@patch("data._http.requests.get")
def test_retries_on_500_then_succeeds(mock_get, mock_sleep):
    mock_get.side_effect = [_mock_resp(500), _mock_resp(200)]
    resp = get_with_retry("http://example.com", max_retries=2)
    assert resp.status_code == 200
    assert mock_get.call_count == 2


@patch("data._http.time.sleep")
@patch("data._http.requests.get")
def test_retries_on_timeout_then_succeeds(mock_get, mock_sleep):
    mock_get.side_effect = [
        requests_lib.Timeout(),
        requests_lib.Timeout(),
        _mock_resp(200),
    ]
    resp = get_with_retry("http://example.com", max_retries=3)
    assert resp.status_code == 200
    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2


@patch("data._http.time.sleep")
@patch("data._http.requests.get")
def test_raises_after_exhausted_timeout_retries(mock_get, mock_sleep):
    mock_get.side_effect = requests_lib.Timeout()
    with pytest.raises(requests_lib.Timeout):
        get_with_retry("http://example.com", max_retries=3)
    assert mock_get.call_count == 3


@patch("data._http.time.sleep")
@patch("data._http.requests.get")
def test_no_retry_on_4xx_client_error(mock_get, mock_sleep):
    mock_get.return_value = _mock_resp(404, raise_on_raise_for_status=True)
    with pytest.raises(requests_lib.HTTPError):
        get_with_retry("http://example.com", max_retries=3)
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@patch("data._http.time.sleep")
@patch("data._http.requests.get")
def test_backoff_doubles_each_retry(mock_get, mock_sleep):
    mock_get.side_effect = [
        requests_lib.Timeout(),
        requests_lib.Timeout(),
        requests_lib.Timeout(),
    ]
    with pytest.raises(requests_lib.Timeout):
        get_with_retry("http://example.com", max_retries=3)
    sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleep_calls == [1, 2]
