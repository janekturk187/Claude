# Day Trading System

A real-time intraday trading system that combines technical price analysis
with Claude-powered news sentiment to generate trade signals and execute
orders through Alpaca's brokerage API.

---

## How It Works

The system runs as a live process during market hours. Two data streams feed
into a signal engine simultaneously — one tracking price, one tracking news.
A trade is only considered when both streams agree on direction.

```
Polygon News WebSocket
        │
        ▼
  Claude Haiku             Alpaca Price WebSocket
  (headline classifier)           │
        │                         ▼
        ▼                  Bar Aggregator
  Session Sentiment         (1-min OHLCV)
  (rolling score)                 │
        │                         ▼
        └──────────► Confluence Filter ◄── Technical Analyzer
                            │               (VWAP, RVOL, momentum,
                            ▼                structure breaks)
                       Risk Gate
                            │
                            ▼
                      Order Manager
                     (Alpaca brackets)
```

---

## Data Streams

### Price Stream (`data/price_stream.py`)
Connects to Alpaca's websocket and subscribes to 1-minute bars for every
ticker on the watchlist. Each bar is stored in SQLite and passed to the
technical analyzer. The `BarAggregator` keeps a rolling 390-bar window
(one full trading day) in memory for indicator calculations.

### News Stream (`data/news_stream.py`)
Connects to Polygon.io's news websocket. Every incoming headline is
checked against the watchlist — if a watched ticker is mentioned, the
headline is passed to the sentiment classifier. The stream auto-reconnects
if the connection drops.

---

## Analysis

### Technical Analyzer (`analysis/technical.py`)
Runs on every bar close. Computes:

- **VWAP** — volume-weighted average price for the session. Price above VWAP
  signals institutional buying pressure; below signals the opposite.
- **Relative Volume (RVOL)** — current bar volume vs. the rolling average.
  Values above 1.5x confirm that a move has real participation behind it.
- **Momentum** — 5-bar rate of change (%). Filters out slow, low-conviction drifts.
- **Structure Break** — checks whether the latest close broke above the prior
  10-bar local high (potential long entry) or below the local low (short entry).
  The local high and low are also used to set stop-loss and target prices.

### Sentiment Classifier (`analysis/sentiment.py`)
Sends each headline to Claude Haiku (chosen for low latency, ~1 sec) and
returns a structured result: sentiment score (1–10), confidence (1–10),
and event type. The `SessionSentiment` class maintains a rolling window of
the last N classified headlines per ticker. Scores are weighted by confidence
and decay over time so that a headline from 30 minutes ago contributes less
than one from 2 minutes ago.

---

## Signal Generation (`signal/confluence.py`)

A signal is only generated when both layers align:

| Technical Setup         | Sentiment Condition            | Signal     |
|-------------------------|--------------------------------|------------|
| Break above local high  | Score ≥ threshold AND above VWAP | Long       |
| Break below local low   | Score ≤ inverse AND below VWAP   | Short      |
| Break above local high  | Sentiment neutral or negative  | Skip       |
| Strong sentiment spike  | No structural break yet        | Watch only |

"Watch" events are logged but do not trigger an order. They put the ticker
on notice — if a structure break follows, the next bar close will catch it.

Signal strength ("strong", "moderate", "weak") is calculated from how many
confluence factors align: sentiment score level, sentiment velocity (delta
from prior headline), relative volume, and momentum. Weak signals are not
executed.

---

## Risk Gate (`execution/risk_gate.py`)

Hard rules enforced before every order, regardless of signal quality:

1. **Trading hours** — only trades between 9:45–11:30am and 1:30–3:30pm ET.
   Avoids the open auction and end-of-day imbalances.
2. **Daily loss limit** — if account P&L for the day is down more than
   `max_daily_loss_pct` of equity, all new entries are blocked.
3. **Max concurrent positions** — never more than `max_open_positions` open
   at the same time.
4. **Duplicate position** — skips any signal for a ticker already held.
5. **News blackout** — blocks entries for `news_blackout_minutes` after a
   fresh headline arrives. Prevents chasing a move that's already happened.

---

## Order Execution (`execution/order_manager.py`)

For each approved signal, the order manager:

1. Calculates position size using risk-based sizing:
   `shares = (equity × max_position_pct) / (entry − stop)`
   This ensures every trade risks the same dollar amount regardless of the
   stock price.

2. Submits a **limit order** at a slight premium/discount to the current
   close (avoids market order slippage).

3. Attaches a **bracket**: stop-loss at the breakout bar's low (for longs)
   and profit target at `entry + (risk × reward_risk_ratio)`. Default 2:1.

All orders and resulting trades are recorded in SQLite for later review.

---

## Storage (`storage.py`)

Four SQLite tables:

| Table         | Contents                                         |
|---------------|--------------------------------------------------|
| `bars`        | Every 1-minute OHLCV bar received from Alpaca    |
| `news_events` | Every classified headline with sentiment score   |
| `signals`     | Every signal generated (including blocked ones)  |
| `trades`      | Every order placed with entry, stop, target, P&L |

---

## Configuration (`config.json`)

| Key                             | Description                                     |
|---------------------------------|-------------------------------------------------|
| `alpaca.api_key/secret_key`     | Alpaca credentials                              |
| `alpaca.paper`                  | `true` for paper trading, `false` for live      |
| `polygon.api_key`               | Polygon.io credentials                          |
| `watchlist.tickers`             | Stocks to watch                                 |
| `risk.max_position_pct`         | Max % of equity risked per trade (e.g. 0.05)    |
| `risk.max_daily_loss_pct`       | Daily loss limit as % of equity (e.g. 0.02)     |
| `risk.max_open_positions`       | Max simultaneous open trades                    |
| `risk.reward_risk_ratio`        | Profit target multiplier (e.g. 2.0 = 2:1 R:R)  |
| `risk.news_blackout_minutes`    | Minutes to block after a fresh headline         |
| `signal.min_sentiment_score`    | Minimum Claude score to consider bullish (1–10) |
| `signal.min_confidence`         | Minimum Claude confidence to use a headline     |
| `signal.min_relative_volume`    | Minimum RVOL to count as confirmed volume       |
| `trading_hours.start/end`       | Session open/close times (ET)                   |

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Fill in config.json
#    - alpaca.api_key / secret_key  (paper.alpaca.markets)
#    - polygon.api_key              (polygon.io)
#    - Set alpaca.paper: true to start in paper mode

# 3. Run
ANTHROPIC_API_KEY=your_key python main.py
```

**Required accounts (all have free tiers):**
- [Alpaca](https://alpaca.markets) — brokerage + market data
- [Polygon.io](https://polygon.io) — real-time news websocket
- [Anthropic](https://console.anthropic.com) — Claude API

---

## Recommended First Steps

1. Run in paper mode (`alpaca.paper: true`) for at least 30 days before
   switching to a live account.
2. Review the `signals` table daily to evaluate signal quality before
   the order manager is executing real money.
3. Start with a short watchlist (3–5 tickers) to keep signal volume
   manageable and results easy to interpret.
4. Read the `trades` table after each session to track win rate and
   average R:R against what the system predicted.

---

## File Structure

```
DayTrading/
├── main.py                  Entry point — wires all components together
├── config.json              All configuration
├── loadconfig.py            Config loader and validation
├── storage.py               SQLite schema and read/write methods
├── requirements.txt
├── data/
│   ├── price_stream.py      Alpaca websocket + bar aggregator
│   └── news_stream.py       Polygon news websocket
├── analysis/
│   ├── technical.py         VWAP, RVOL, momentum, structure breaks
│   └── sentiment.py         Claude headline classifier + session scorer
├── signal/
│   └── confluence.py        Combines technical + sentiment into a signal
└── execution/
    ├── risk_gate.py          Hard rules that block bad entries
    └── order_manager.py      Alpaca bracket order submission
```
