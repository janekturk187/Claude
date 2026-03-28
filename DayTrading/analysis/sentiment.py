"""
sentiment.py — Claude-powered headline classifier + rolling session scorer.

classify_headline() sends a single headline to Claude and returns a
structured sentiment result. SessionSentiment tracks a rolling window
of scores per ticker for the current trading session.
"""

import json
import logging
import time
from collections import defaultdict
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

_client: Optional[anthropic.Anthropic] = None

_SYSTEM_PROMPT = (
    "You are a financial news classifier. Respond ONLY with a valid JSON object, "
    "no markdown, no explanation."
)

_USER_PROMPT = """\
Classify this financial headline for ticker {ticker}:

\"{headline}\"

Respond with exactly:
{{
  "sentiment_score": <integer 1-10, 1=extremely bearish, 5=neutral, 10=extremely bullish>,
  "confidence": <integer 1-10>,
  "event_type": <one of: "earnings","acquisition","product_launch","legal","executive_change","macro","analyst_rating","other">,
  "directional": <"bullish" | "bearish" | "neutral">
}}"""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def classify_headline(ticker: str, headline: str, cfg) -> Optional[dict]:
    """
    Send a headline to Claude and return a classification dict.
    Uses claude-haiku for low latency. Returns None on any failure.
    """
    prompt = _USER_PROMPT.format(ticker=ticker, headline=headline)
    try:
        msg = _get_client().messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if not msg.content:
            return None
        result = json.loads(msg.content[0].text)
        result["headline"] = headline
        result["ticker"] = ticker
        return result
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON for headline: %.80s", headline)
        return None
    except anthropic.APIError as e:
        logger.error("Claude API error classifying headline: %s", e)
        return None


class SessionSentiment:
    """
    Maintains a rolling window of sentiment scores per ticker
    within the current trading session.

    Scores are weighted by confidence and decay with age so that
    recent headlines carry more weight than older ones.
    """

    _DECAY_HALF_LIFE_SECONDS = 600  # score halves every 10 minutes

    def __init__(self, window: int = 5):
        self._window = window
        # {ticker: [(score, confidence, timestamp), ...]}
        self._events: dict[str, list] = defaultdict(list)

    def add(self, ticker: str, score: int, confidence: int):
        events = self._events[ticker]
        events.append((score, confidence, time.monotonic()))
        if len(events) > self._window:
            events.pop(0)

    def score(self, ticker: str) -> Optional[float]:
        """Weighted average sentiment score, or None if no events."""
        events = self._events.get(ticker, [])
        if not events:
            return None
        now = time.monotonic()
        total_weight = 0.0
        weighted_sum = 0.0
        for s, conf, ts in events:
            age = now - ts
            decay = 0.5 ** (age / self._DECAY_HALF_LIFE_SECONDS)
            weight = conf * decay
            weighted_sum += s * weight
            total_weight += weight
        if total_weight == 0:
            return None
        return round(weighted_sum / total_weight, 2)

    def delta(self, ticker: str) -> Optional[float]:
        """
        Difference between the most recent score and the prior score.
        Positive = sentiment improving, negative = deteriorating.
        """
        events = self._events.get(ticker, [])
        if len(events) < 2:
            return None
        return round(events[-1][0] - events[-2][0], 2)

    def reset(self, ticker: str):
        self._events[ticker] = []

    def reset_all(self):
        self._events.clear()
