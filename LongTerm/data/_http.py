"""
_http.py — shared HTTP helper with exponential-backoff retry.

All data modules use this instead of calling requests.get directly so that
transient 429 / 5xx / timeout errors are retried automatically rather than
silently dropped as a failed ticker.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)


def get_with_retry(
    url: str,
    *,
    headers: dict = None,
    params: dict = None,
    timeout: int = 15,
    max_retries: int = 3,
) -> requests.Response:
    """
    GET with exponential backoff on 429, 5xx, and timeouts.

    - 429 / 5xx: retried up to max_retries times with 1s, 2s, 4s waits.
    - Timeout: retried the same way.
    - 4xx (other than 429): raised immediately, no retry.
    - Raises on the final failed attempt.
    """
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "HTTP %d on %s — retry %d/%d in %ds",
                        resp.status_code, url, attempt + 1, max_retries - 1, wait,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            return resp
        except requests.Timeout:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "Timeout on %s — retry %d/%d in %ds",
                    url, attempt + 1, max_retries - 1, wait,
                )
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"get_with_retry: exhausted {max_retries} retries for {url}")
