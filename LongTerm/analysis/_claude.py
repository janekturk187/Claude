"""
_claude.py — shared Anthropic client with retry for transient errors.

All analysis modules call create_message() instead of the client directly
so that 529 (overloaded) and 500 errors are retried automatically rather
than silently dropping the analysis for a ticker.
"""

import logging
import time
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def create_message(*, max_retries: int = 3, **kwargs) -> anthropic.types.Message:
    """
    Call messages.create with exponential backoff on transient errors.

    Retries on:
      - RateLimitError (429) — longer waits since quota needs time to replenish
      - InternalServerError (500 / 529 overloaded)

    Raises immediately on other errors (bad key, invalid request, etc.)
    so callers get fast feedback on configuration problems.
    """
    for attempt in range(max_retries):
        try:
            return get_client().messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)  # 5s, 10s, 20s
                logger.warning(
                    "Claude rate limit — retry %d/%d in %ds",
                    attempt + 1, max_retries - 1, wait,
                )
                time.sleep(wait)
                continue
            raise
        except anthropic.InternalServerError:
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "Claude server error — retry %d/%d in %ds",
                    attempt + 1, max_retries - 1, wait,
                )
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"create_message: exhausted {max_retries} retries")
