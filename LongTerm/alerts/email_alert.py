"""
email_alert.py — sends email notifications when a thesis is flagged.

Uses Python's built-in smtplib (no extra dependency).
Enable by setting alerts.email.enabled = true in config.json and
providing EMAIL_PASSWORD as an environment variable.

Gmail example:
  smtp_host: smtp.gmail.com
  smtp_port: 587
  Use an App Password (not your account password):
  https://myaccount.google.com/apppasswords
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_flag_alert(ticker: str, flag_reason: str,
                    thesis_text: str, cfg) -> bool:
    """
    Send an email alert for a flagged thesis.

    Args:
        ticker:      stock symbol
        flag_reason: why the thesis was flagged
        thesis_text: the original thesis statement
        cfg:         EmailAlertConfig (enabled, smtp_host, smtp_port,
                     from_addr, to_addr)

    Returns True on success, False on failure or if alerts are disabled.
    """
    if not cfg.enabled:
        return False

    password = os.environ.get("EMAIL_PASSWORD")
    if not password:
        logger.warning(
            "EMAIL_PASSWORD not set — skipping email alert for %s", ticker
        )
        return False

    subject = f"[LongTerm] Thesis Flagged: {ticker}"
    body = (
        f"The investment thesis for {ticker} has been flagged for review.\n\n"
        f"Flag reason:\n{flag_reason}\n\n"
        f"Original thesis:\n{thesis_text}\n\n"
        "Log in to review the full analysis."
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = cfg.from_addr
    msg["To"]      = cfg.to_addr
    msg.set_content(body)

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg.from_addr, password)
            smtp.send_message(msg)
        logger.info("Flag alert sent for %s → %s", ticker, cfg.to_addr)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed for %s — check EMAIL_PASSWORD", ticker
        )
    except smtplib.SMTPException as e:
        logger.error("SMTP error sending alert for %s: %s", ticker, e)
    except Exception as e:
        logger.error("Unexpected error sending alert for %s: %s", ticker, e)

    return False
