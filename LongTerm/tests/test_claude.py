"""Tests for analysis._claude retry logic — no real API calls."""

import pytest
from unittest.mock import patch, MagicMock, call

import anthropic
from analysis._claude import create_message


def _mock_message():
    msg = MagicMock(spec=anthropic.types.Message)
    msg.content = [MagicMock(text='{"result": "ok"}')]
    return msg


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_success_on_first_attempt(mock_get_client, mock_sleep):
    mock_get_client.return_value.messages.create.return_value = _mock_message()
    result = create_message(model="claude-opus-4-6", max_tokens=100,
                            messages=[{"role": "user", "content": "hi"}])
    assert result.content[0].text == '{"result": "ok"}'
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
    result = create_message(model="claude-opus-4-6", max_tokens=100,
                            messages=[{"role": "user", "content": "hi"}], max_retries=2)
    assert result.content[0].text == '{"result": "ok"}'
    assert client.messages.create.call_count == 2
    mock_sleep.assert_called_once_with(1)


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
    result = create_message(model="claude-opus-4-6", max_tokens=100,
                            messages=[{"role": "user", "content": "hi"}], max_retries=2)
    assert result.content[0].text == '{"result": "ok"}'
    mock_sleep.assert_called_once_with(5)  # rate limit waits longer: 5 * 2^0


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_raises_after_exhausted_retries(mock_get_client, mock_sleep):
    client = mock_get_client.return_value
    client.messages.create.side_effect = anthropic.InternalServerError(
        message="down", response=MagicMock(status_code=500), body={}
    )
    with pytest.raises(anthropic.InternalServerError):
        create_message(model="claude-opus-4-6", max_tokens=100,
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
        create_message(model="claude-opus-4-6", max_tokens=100,
                       messages=[{"role": "user", "content": "hi"}], max_retries=3)
    assert client.messages.create.call_count == 1
    mock_sleep.assert_not_called()


@patch("analysis._claude.time.sleep")
@patch("analysis._claude.get_client")
def test_backoff_doubles_for_server_errors(mock_get_client, mock_sleep):
    client = mock_get_client.return_value
    client.messages.create.side_effect = anthropic.InternalServerError(
        message="down", response=MagicMock(status_code=500), body={}
    )
    with pytest.raises(anthropic.InternalServerError):
        create_message(model="claude-opus-4-6", max_tokens=100,
                       messages=[{"role": "user", "content": "hi"}], max_retries=3)
    sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleep_calls == [1, 2]
