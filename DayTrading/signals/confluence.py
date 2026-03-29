"""
confluence.py — combines technical and sentiment analysis into a trade signal.

evaluate() is called on each bar close. It returns a signal dict if
both layers agree on direction, or None if conditions aren't met.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _strength(technical: dict, sentiment_score: float,
              sentiment_delta: Optional[float], direction: str, cfg) -> str:
    """
    Classify signal strength based on how many confluence factors align.
    Direction-aware: bullish scoring for longs, bearish scoring for shorts.
    Returns: "strong" | "moderate" | "weak" | "none"
    """
    score = 0
    bearish_threshold = 10 - cfg.min_sentiment_score

    # Sentiment factors — scored relative to the signal direction
    if direction == "long":
        if sentiment_score >= 8:
            score += 2
        elif sentiment_score >= cfg.min_sentiment_score:
            score += 1
    else:  # short
        if sentiment_score <= 2:
            score += 2
        elif sentiment_score <= bearish_threshold:
            score += 1

    if sentiment_delta is not None and abs(sentiment_delta) >= 2:
        score += 1

    # Technical factors
    if technical.get("relative_volume", 0) and technical["relative_volume"] >= cfg.min_relative_volume:
        score += 1

    if technical.get("momentum") and abs(technical["momentum"]) >= 0.5:
        score += 1

    if score >= 4:
        return "strong"
    elif score >= 2:
        return "moderate"
    elif score >= 1:
        return "weak"
    return "none"


def evaluate(ticker: str, technical: dict, sentiment_score: Optional[float],
             sentiment_delta: Optional[float], cfg) -> Optional[dict]:
    """
    Evaluate whether a trade signal exists for this ticker.

    Rules:
    - Long: price broke above local high AND sentiment bullish AND above VWAP
    - Short: price broke below local low AND sentiment bearish AND below VWAP
    - Skip: technical and sentiment disagree
    - Watch: sentiment strong but no structural break yet

    Returns a signal dict or None.
    """
    if technical is None or not technical:
        return None

    # Require minimum sentiment data
    if sentiment_score is None:
        logger.debug("%s: no sentiment data — skip", ticker)
        return None

    bullish_threshold = cfg.min_sentiment_score
    bearish_threshold = 10 - cfg.min_sentiment_score
    if bearish_threshold < sentiment_score < bullish_threshold:
        logger.debug("%s: sentiment neutral (%.1f) — skip", ticker, sentiment_score)
        return None

    breakout_high = technical.get("breakout_high", False)
    breakdown_low = technical.get("breakdown_low", False)
    above_vwap = technical.get("above_vwap")

    direction = None
    if breakout_high and sentiment_score >= cfg.min_sentiment_score and above_vwap:
        direction = "long"
    elif breakdown_low and sentiment_score <= (10 - cfg.min_sentiment_score) and above_vwap is False:
        direction = "short"

    if direction is None:
        # Log as a watch if sentiment is strong but structure hasn't confirmed
        if sentiment_score >= cfg.min_sentiment_score or sentiment_score <= (10 - cfg.min_sentiment_score):
            logger.info(
                "%s WATCH | sentiment=%.1f delta=%s | no structural break yet",
                ticker, sentiment_score,
                f"{sentiment_delta:+.1f}" if sentiment_delta is not None else "n/a",
            )
        return None

    strength = _strength(technical, sentiment_score, sentiment_delta, direction, cfg)
    if strength in ("none", "weak"):
        return None

    signal = {
        "ticker":            ticker,
        "direction":         direction,
        "close":             technical.get("close"),
        "local_high":        technical.get("local_high"),
        "local_low":         technical.get("local_low"),
        "breakout_bar_low":  technical.get("breakout_bar_low"),
        "vwap":              technical.get("vwap"),
        "relative_volume":   technical.get("relative_volume"),
        "momentum":          technical.get("momentum"),
        "sentiment_score":   sentiment_score,
        "sentiment_delta":   sentiment_delta,
        "near_gap":          False,  # populated by order_manager if gap data available
        "signal_strength":   strength,
    }

    logger.info(
        "SIGNAL %s %s | strength=%s sentiment=%.1f rvol=%s close=%.2f",
        direction.upper(), ticker, strength, sentiment_score,
        technical.get("relative_volume", "n/a"), technical.get("close", 0),
    )

    return signal
