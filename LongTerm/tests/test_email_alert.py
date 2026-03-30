"""Tests for alerts/email_alert.py — no real SMTP connections."""

import pytest
from unittest.mock import MagicMock, patch

from alerts.email_alert import send_flag_alert


def _cfg(enabled=True, from_addr="from@test.com", to_addr="to@test.com",
         smtp_host="smtp.gmail.com", smtp_port=587):
    cfg = MagicMock()
    cfg.enabled = enabled
    cfg.from_addr = from_addr
    cfg.to_addr = to_addr
    cfg.smtp_host = smtp_host
    cfg.smtp_port = smtp_port
    return cfg


class TestSendFlagAlert:
    def test_disabled_config_returns_false(self):
        result = send_flag_alert("AAPL", "margins fell", "Long thesis", _cfg(enabled=False))
        assert result is False

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_password_returns_false(self):
        result = send_flag_alert("AAPL", "reason", "thesis", _cfg())
        assert result is False

    @patch("alerts.email_alert.smtplib.SMTP")
    @patch.dict("os.environ", {"EMAIL_PASSWORD": "secret"})
    def test_sends_email_on_success(self, mock_smtp_class):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        result = send_flag_alert("AAPL", "margins fell", "Long thesis", _cfg())
        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once()
        mock_smtp.send_message.assert_called_once()

    @patch("alerts.email_alert.smtplib.SMTP")
    @patch.dict("os.environ", {"EMAIL_PASSWORD": "secret"})
    def test_subject_contains_ticker(self, mock_smtp_class):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        send_flag_alert("NVDA", "reason", "thesis", _cfg())
        sent_msg = mock_smtp.send_message.call_args[0][0]
        assert "NVDA" in sent_msg["Subject"]

    @patch("alerts.email_alert.smtplib.SMTP")
    @patch.dict("os.environ", {"EMAIL_PASSWORD": "secret"})
    def test_smtp_auth_error_returns_false(self, mock_smtp_class):
        import smtplib
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad auth")
        result = send_flag_alert("AAPL", "reason", "thesis", _cfg())
        assert result is False

    @patch("alerts.email_alert.smtplib.SMTP")
    @patch.dict("os.environ", {"EMAIL_PASSWORD": "secret"})
    def test_generic_smtp_error_returns_false(self, mock_smtp_class):
        import smtplib
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        mock_smtp.send_message.side_effect = smtplib.SMTPException("error")
        result = send_flag_alert("AAPL", "reason", "thesis", _cfg())
        assert result is False

    @patch("alerts.email_alert.smtplib.SMTP")
    @patch.dict("os.environ", {"EMAIL_PASSWORD": "secret"})
    def test_flag_reason_in_body(self, mock_smtp_class):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        send_flag_alert("AAPL", "Revenue growth collapsed", "thesis", _cfg())
        sent_msg = mock_smtp.send_message.call_args[0][0]
        assert "Revenue growth collapsed" in sent_msg.get_content()
