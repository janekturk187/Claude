"""Tests for analysis._claude retry logic — no real API calls."""

import pytest
from unittest.mock import patch, MagicMock

import anthropic
from analysis._claude import create_message


def _mock_message():
    msg = MagicMock(spec=anthropic.types.Message)
    msg.content = [MagicMock(text='{"sentiment_score": 8}')]
    return msg


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_success_first_attempt(mock_get_client, mock_sleep):
    mock_get_client.return_value.messages.create.return_value = _mock_message()
    result = create_message(model="claude-haiku-4-5-20251001", max_tokens=256,
                            messages=[{"role": "user", "content": "classify"}])
    assert result.content[0].text == '{"sentiment_score": 8}'
    mock_sleep.assert_not_called()


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_retries_on_internal_server_error(mock_get_client, mock_sleep):
    client = mock_get_client.return_value
    client.messages.create.side_effect = [
        anthropic.InternalServerError(
            message="overloaded", response=MagicMock(status_code=529), body={}
        ),
        _mock_message(),
    ]
    result = create_message(model="claude-haiku-4-5-20251001", max_tokens=256,
                            messages=[{"role": "user", "content": "hi"}], max_retries=2)
    assert result is not None
    assert client.messages.create.call_count == 2
    mock_sleep.assert_called_once()
    assert 0.8 <= mock_sleep.call_args[0][0] <= 1.2  # base=1s ±20% jitter


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_retries_on_rate_limit(mock_get_client, mock_sleep):
    client = mock_get_client.return_value
    client.messages.create.side_effect = [
        anthropic.RateLimitError(
            message="rate limited", response=MagicMock(status_code=429), body={}
        ),
        _mock_message(),
    ]
    result = create_message(model="claude-haiku-4-5-20251001", max_tokens=256,
                            messages=[{"role": "user", "content": "hi"}], max_retries=2)
    assert result is not None
    mock_sleep.assert_called_once()
    assert 4.0 <= mock_sleep.call_args[0][0] <= 6.0  # base=5s ±20% jitter


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_raises_after_exhausted_retries(mock_get_client, mock_sleep):
    client = mock_get_client.return_value
    client.messages.create.side_effect = anthropic.InternalServerError(
        message="down", response=MagicMock(status_code=500), body={}
    )
    with pytest.raises(anthropic.InternalServerError):
        create_message(model="claude-haiku-4-5-20251001", max_tokens=256,
                       messages=[{"role": "user", "content": "hi"}], max_retries=3)
    assert client.messages.create.call_count == 3


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_no_retry_on_auth_error(mock_get_client, mock_sleep):
    client = mock_get_client.return_value
    client.messages.create.side_effect = anthropic.AuthenticationError(
        message="bad key", response=MagicMock(status_code=401), body={}
    )
    with pytest.raises(anthropic.AuthenticationError):
        create_message(model="claude-haiku-4-5-20251001", max_tokens=256,
                       messages=[{"role": "user", "content": "hi"}], max_retries=3)
    assert client.messages.create.call_count == 1
    mock_sleep.assert_not_called()
