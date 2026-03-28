# Proposal: Real-Time Day Trading System

A ground-up design for a day trading system built to operate at intraday
resolution. This is a separate application from Pelosi — it shares the
Claude analysis concept but requires fundamentally different data sources,
latency targets, and execution infrastructure.

---

## Core Thesis

Day trading edges come from speed and precision, not from sentiment alone.
The system needs to identify a technical setup (price structure, volume,
momentum) and use real-time news sentiment as a confluence filter — not
the other way around. A great sentiment signal on a bad technical setup
is still a bad trade.

---

## What Makes This Different from Pelosi

| Dimension        | Pelosi (current)         | Day Trading System          |
|------------------|--------------------------|-----------------------------|
| News latency     | ~15 min (NewsAPI/RSS)    | < 2 sec (paid feed)         |
| Price data       | 1-min REST polling       | Websocket tick stream        |
| Signal horizon   | Daily / multi-day        | Minutes to hours             |
| Execution        | None (research only)     | Brokerage API integration    |
| Risk management  | None                     | Hard stop-loss, daily limit  |
| Candle resolution| 1-min                    | 1-min, 5-min, VWAP           |

---

## System Architecture

```
 ┌─────────────────────────────────────────────────────────┐
 │                   Data Ingestion Layer                   │
 │                                                          │
 │  Polygon.io News WebSocket ──► News Classifier (Claude) │
 │  Alpaca Market Data WebSocket ──► Price Stream Handler  │
 └────────────────────┬──────────────────┬─────────────────┘
                      │                  │
 ┌────────────────────▼──────────────────▼─────────────────┐
 │                   Signal Engine                          │
 │                                                          │
 │  Technical Analyzer ──┐                                  │
 │  Sentiment Scorer  ───┼──► Confluence Filter ──► Signal │
 │  Risk Gate         ───┘                                  │
 └────────────────────────────────────┬────────────────────┘
                                      │
 ┌────────────────────────────────────▼────────────────────┐
 │                   Execution Layer                        │
 │                                                          │
 │  Order Manager ──► Alpaca Trading API                   │
 │  Position Tracker                                        │
 │  Stop-Loss Monitor                                       │
 └─────────────────────────────────────────────────────────┘
```

---

## Layer 1: Data Ingestion

### Real-Time News Feed

Replace NewsAPI/RSS with **Polygon.io** or **Benzinga** news websocket.
These provide headlines in under 2 seconds of publication — fast enough
to act before the 1-minute bar closes.

Claude's role stays the same: classify each headline into a structured
signal (sentiment, tickers, event type, confidence). However at this
latency the Claude call itself (~1–2 sec) becomes a bottleneck. Mitigation:

- Fire Claude calls async / non-blocking
- Cache classifications for duplicate headlines (same story, multiple sources)
- Use a lighter prompt focused only on: ticker, direction, confidence
  (drop market_impact narrative to cut tokens and latency)

### Real-Time Price Stream

Switch from yfinance REST polling to a **websocket price stream**
(Alpaca, Polygon, or Interactive Brokers market data API). This gives
you tick-by-tick trades and quotes rather than polling for the last
closed candle.

Build 1-minute and 5-minute OHLCV bars from the tick stream in memory.
Persist bars to SQLite for backtesting but make decisions from the
in-memory state.

---

## Layer 2: Signal Engine

### Technical Analyzer

Computes the following on each new bar close:

- **VWAP** — volume-weighted average price for the session; price above/below
  VWAP indicates institutional bias direction
- **Relative Volume** — current bar volume vs same-time average; high RVOL
  (> 1.5x) confirms that a move has participation
- **Momentum** — 5-bar rate of change; filters out slow, low-conviction moves
- **Structure** — is price breaking above a prior local high or below a prior
  local low? Breakouts with volume are the primary entry trigger
- **Fair Market Gaps** — inherited from Pelosi's `StockPoller`; gaps on the
  5-min chart are magnet levels and potential entry zones

### Sentiment Scorer

Computes a rolling sentiment score for each ticker using the last N news
events within the trading session:

```
session_sentiment = weighted_avg(
    claude_score,
    weight = confidence * recency_decay
)
```

Recency decay means a headline from 30 minutes ago contributes less than
one from 2 minutes ago.

### Confluence Filter

A trade signal is only generated when both layers agree:

| Technical Setup       | Sentiment Requirement             | Signal  |
|-----------------------|-----------------------------------|---------|
| Breakout above high   | Session sentiment >= 7, delta > 0 | Long    |
| Breakdown below low   | Session sentiment <= 4, delta < 0 | Short   |
| Breakout above high   | Sentiment neutral or negative     | Skip    |
| Strong sentiment spike| No technical breakout             | Watch   |

"Watch" signals are logged but do not trigger an order — they put the
ticker on a watchlist for the next structural break.

---

## Layer 3: Execution

### Brokerage Integration

**Alpaca** is the recommended integration for a first build:
- Commission-free, paper trading environment available
- REST + websocket API, well-documented Python SDK
- Supports fractional shares (useful for high-price tickers)

### Order Manager

For each signal:
1. Calculate position size based on account equity and max risk per trade
   (e.g. never risk more than 1% of account on a single trade)
2. Submit a **limit order** at or near the current ask/bid — never market
   orders, which have unpredictable fill prices on volatile stocks
3. Immediately place a **stop-loss order** at the defined invalidation level
   (typically below the breakout bar's low)
4. Set a **profit target** at 2x the risk distance (2:1 reward/risk minimum)

### Risk Gate

Hard rules that override the signal engine entirely:

- **Daily loss limit**: if the account is down X% on the day, stop trading
- **Max concurrent positions**: no more than 3 open at once
- **News blackout**: do not enter a new position within 5 minutes of a
  scheduled macro event (Fed announcements, CPI, NFP)
- **Time filter**: only trade between 9:45–11:30am and 1:30–3:30pm ET
  (avoid the open auction chaos and end-of-day imbalances)

---

## Tech Stack

| Component          | Technology                          |
|--------------------|-------------------------------------|
| Language           | Python                              |
| Price stream       | Alpaca websocket SDK                |
| News stream        | Polygon.io or Benzinga websocket    |
| News analysis      | Claude API (async)                  |
| Persistence        | SQLite (bars, signals, trades)      |
| Execution          | Alpaca Trading API                  |
| Backtesting        | Built from SQLite bar history       |

---

## Development Phases

**Phase 1 — Data infrastructure**
Wire up websocket price and news streams. Build the in-memory bar aggregator.
Log everything to SQLite. No signal generation yet.

**Phase 2 — Signal engine (paper only)**
Implement technical analyzer and sentiment scorer. Generate signals and log
them but do not execute. Run for 30 days, evaluate signal quality.

**Phase 3 — Paper execution**
Wire up Alpaca paper trading. Let the system place and manage paper trades
automatically. Evaluate P&L, win rate, avg winner/loser over 30 days.

**Phase 4 — Live, minimum size**
If Phase 3 clears the bar (positive expectancy, drawdown within tolerance),
go live with minimum position sizes. Run paper and live in parallel.

---

## Honest Risk Assessment

Day trading has a well-documented failure rate (> 80% of retail day traders
lose money over a 12-month period). The edge this system targets — news
confluence with technical structure — is real but thin and requires:

- Strict adherence to the risk gate (the rules only work if you don't override them)
- Enough capital that commissions and slippage don't consume the edge
- Continuous monitoring and signal recalibration as market regimes change

This is a high-complexity, high-discipline undertaking. The paper trading
phase is not optional.
