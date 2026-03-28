# Proposal: Long-Term Investment Analysis System

A design for a fundamentals-driven, multi-month holding period system.
Where the day trading proposal competes on speed, this system competes on
depth — aggregating more information per company than any single analyst
would read, and surfacing it in a structured, comparable format.

---

## Core Thesis

Long-term edges come from understanding a business better than the consensus
does, and holding long enough for that understanding to be reflected in the
price. Claude is well-suited to this: it can read earnings call transcripts,
10-K filings, and analyst reports and extract structured insights that would
take a human analyst hours to compile.

This system does not try to time entries. It tries to identify undervalued or
overlooked businesses, build a thesis, and monitor that thesis for
confirmation or invalidation over weeks and months.

---

## What Makes This Different from Pelosi and the Day Trading System

| Dimension        | Pelosi              | Day Trading          | Long-Term System         |
|------------------|---------------------|----------------------|--------------------------|
| Signal horizon   | Daily               | Minutes to hours     | Weeks to months          |
| Primary data     | News headlines      | Price + breaking news| Filings, earnings, macro |
| Claude's role    | News classifier     | Fast sentiment filter| Deep document analysis   |
| Rebalance cadence| N/A                 | Intraday             | Weekly or monthly        |
| Position count   | N/A                 | 1–3 at a time        | 10–20 diversified        |
| Data latency     | Doesn't matter much | Critical             | Irrelevant               |

---

## System Architecture

```
 ┌──────────────────────────────────────────────────────────┐
 │                  Fundamental Data Layer                   │
 │                                                          │
 │  SEC EDGAR API ──► 10-K / 10-Q / 8-K filings            │
 │  Earnings Call Transcripts (Seeking Alpha / Motley Fool) │
 │  Financial Statements (Financial Modeling Prep API)      │
 │  Macro Indicators (FRED API — free)                      │
 └──────────────────────────────┬───────────────────────────┘
                                │
 ┌──────────────────────────────▼───────────────────────────┐
 │                  Claude Analysis Layer                    │
 │                                                          │
 │  Document Analyzer ──► Thesis Builder                    │
 │  Earnings Scorer   ──► Risk Extractor                    │
 │  Sector Summarizer ──► Comparative Ranker                │
 └──────────────────────────────┬───────────────────────────┘
                                │
 ┌──────────────────────────────▼───────────────────────────┐
 │                  Portfolio Layer                          │
 │                                                          │
 │  Watchlist Manager                                       │
 │  Position Tracker                                        │
 │  Thesis Monitor (flags when thesis assumptions change)   │
 │  Weekly Report Generator                                 │
 └──────────────────────────────────────────────────────────┘
```

---

## Layer 1: Fundamental Data

### SEC Filings (EDGAR API — free)

The SEC provides free API access to all public filings. The most valuable:

- **10-K** (annual report) — revenue, margins, debt, risk factors, management
  discussion. Claude reads this and extracts a structured company profile.
- **10-Q** (quarterly report) — same but quarterly; flags trend changes
- **8-K** (material events) — acquisitions, executive departures, guidance
  changes. These are the catalysts that move stock prices over weeks.

### Earnings Call Transcripts

Earnings calls contain forward guidance and management tone that doesn't
appear in the financial tables. Claude can read a transcript and extract:

- Whether guidance was raised, lowered, or maintained
- Management confidence tone (hedged language vs. assertive)
- Analyst question themes (what are the bears focused on?)
- Any mention of new risks not in prior transcripts

Sources: Seeking Alpha (paid), Motley Fool (free with scraping), or
The Motley Fool Transcripts API.

### Financial Statements

Structured financial data for ratio analysis:

- Revenue growth (YoY, QoQ)
- Gross margin and operating margin trends
- Free cash flow
- Debt-to-equity, interest coverage
- Return on equity / return on invested capital

**Financial Modeling Prep API** provides this in clean JSON format.
Free tier covers end-of-day data with a reasonable rate limit.

### Macro Indicators (FRED API — free)

Macroeconomic context affects sector rotation. Pull:

- Federal Funds Rate (current and trend)
- CPI / PCE (inflation)
- 10-year treasury yield
- ISM Manufacturing / Services PMI
- Consumer sentiment

Claude can contextualize a company's outlook against the macro backdrop:
"This company's thesis depends on consumer spending — current macro trends
are a headwind."

---

## Layer 2: Claude Analysis

### Document Analyzer

For each new 10-K or earnings transcript, Claude produces a structured
company report:

```json
{
  "ticker": "AAPL",
  "filing_type": "10-K",
  "period": "FY2025",
  "revenue_trend": "growing",
  "margin_trend": "compressing",
  "key_risks": ["China revenue concentration", "services growth slowdown"],
  "key_opportunities": ["Vision Pro platform", "India expansion"],
  "management_tone": "cautious",
  "guidance_direction": "maintained",
  "thesis_score": 7,
  "thesis_summary": "2-3 sentence synthesis"
}
```

### Earnings Scorer

Rates each earnings report relative to consensus expectations:

- Did revenue beat / meet / miss?
- Did EPS beat / meet / miss?
- Was guidance raised / maintained / lowered?
- How does this compare to the prior 4 quarters (trend)?

Outputs a single `earnings_quality_score` (1–10) that can be tracked over
time to identify companies that consistently beat vs. those that manage
expectations down.

### Risk Extractor

Reads the risk factors section of 10-K filings and flags:

- Risks that are *new* this year vs. prior filing (material change)
- Risks that have escalated in prominence (moved earlier in the list)
- Litigation mentions, regulatory risks, customer concentration

New or escalating risks are an early warning system — often appear in
filings months before they impact the stock price.

### Comparative Ranker

For a watchlist of 20–30 stocks in the same sector, Claude ranks them
across dimensions:

- Growth quality
- Balance sheet strength
- Management credibility (based on guidance accuracy history)
- Valuation vs. peers (using financial statement ratios)

Outputs a ranked table updated each earnings season.

---

## Layer 3: Portfolio Management

### Watchlist Manager

Maintains two lists:

- **Active positions** — companies you own with the thesis that justified entry
- **Watch candidates** — companies that score well but aren't at an attractive
  entry price yet

Tracks each position's original thesis assumptions and flags when new data
(earnings, 8-K, macro shift) puts an assumption at risk.

### Thesis Monitor

The most important component. For each active position, it stores the thesis
at entry:

```
NVDA thesis (entered 2026-01-15):
  - AI infrastructure spending accelerating through 2027
  - Gross margins stable above 70%
  - No credible GPU competitor in data center market
```

Each quarter, after Claude analyzes the new earnings/filing, it checks:
"Are these assumptions still true?" If a core assumption flips, the system
flags the position for review — not an automatic sell, but a prompt to
re-evaluate.

### Weekly Report

Every Sunday, generates a summary:

- Portfolio performance vs. S&P 500
- Any thesis flags triggered this week
- Upcoming earnings dates for held positions
- New 8-K filings from held companies
- Macro indicators that moved significantly

Output as a formatted report to a file or email (via SMTP or a simple
webhook to Slack/Discord).

---

## Tech Stack

| Component              | Technology                                    |
|------------------------|-----------------------------------------------|
| Language               | Python                                        |
| SEC filings            | EDGAR full-text search API (free)             |
| Financial statements   | Financial Modeling Prep API (free tier)       |
| Macro data             | FRED API (free)                               |
| Earnings transcripts   | Scraper (Motley Fool) or Seeking Alpha API    |
| Document analysis      | Claude API (claude-opus for deep reads)       |
| Persistence            | SQLite (company profiles, thesis log, scores) |
| Scheduling             | Python `schedule` library or cron             |
| Reporting              | Markdown files or SMTP email                  |

Note: Use `claude-opus` (not sonnet) for long document analysis — the
larger context window and stronger reasoning justify the higher cost when
reading a 100-page 10-K.

---

## Development Phases

**Phase 1 — Data pipelines**
Build EDGAR fetcher, financial statement fetcher, macro fetcher.
Store raw documents in SQLite. No analysis yet.

**Phase 2 — Claude analysis layer**
Build document analyzer and earnings scorer. Run against 6 months of
historical filings for a test watchlist. Evaluate output quality.

**Phase 3 — Thesis builder and monitor**
Build the thesis storage and monitoring system. Back-populate for a test
portfolio (pretend you held certain stocks, see if the thesis monitor
would have flagged the right exit points).

**Phase 4 — Live tracking**
Run against a real watchlist. Use Claude's outputs to inform actual
investment decisions. Do not automate execution — this system is a
research assistant, not an autopilot.

---

## Why Long-Term is More Defensible for Retail

- **No latency requirement** — a 10-K analysis that takes 30 seconds is
  perfectly fine; no one else is trading on that document in the next 30 sec
- **Less competition from HFT** — microsecond algos don't care about annual
  reports; this is genuinely underserved territory at retail scale
- **Claude's strengths align** — long document comprehension, structured
  extraction, nuanced tone analysis are exactly what Claude is good at
- **Compounding** — a 15–20% annual return through disciplined fundamental
  investing is a realistic and life-changing outcome over 10+ years

---

## Honest Risk Assessment

Long-term investing still requires discipline:

- **Thesis drift** — holding a position after the thesis has clearly broken
  because you don't want to realize a loss
- **Over-diversification** — 30+ positions dilutes every insight the system
  produces; keep the watchlist focused
- **Macro blindspot** — even great companies get crushed in rate-rising
  environments; the macro layer exists for this reason
- **Claude's limitations** — Claude can summarize and score a document but
  it cannot predict the future; every output is an input to your judgment,
  not a substitute for it
