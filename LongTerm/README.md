# Long-Term Investment Analysis System

A fundamentals-driven research tool that uses Claude to analyze SEC filings,
earnings reports, and macroeconomic data. Designed for multi-week to
multi-month holding periods where the edge comes from depth of analysis
rather than speed of execution.

---

## How It Works

The system runs on a scheduled basis — not a live loop. It periodically
fetches documents and financial data, sends them to Claude for structured
analysis, stores the results, and monitors whether the assumptions behind
active investment theses are still valid.

```
SEC EDGAR API          Financial Modeling Prep      FRED API
(10-K / 10-Q / 8-K)   (income, cash flow,          (rates, CPI,
        │               balance sheet, EPS)           treasury, sentiment)
        │                       │                          │
        ▼                       ▼                          ▼
Document Analyzer        Earnings Scorer            Macro Snapshot
(Claude Opus)            (Claude Opus)              (stored in DB)
        │                       │
        ▼                       ▼
  Company Profiles        Earnings Scores
  (stored in DB)          (stored in DB)
        │                       │
        └───────────────────────┘
                    │
                    ▼
           Thesis Monitor
           (checks active theses
            against latest data)
                    │
                    ▼
           Weekly Report
           (markdown summary)
```

---

## Data Sources

### SEC EDGAR (`data/edgar.py`)
The SEC provides free API access to all public filings. The system fetches
the most recent 10-K (annual) and 10-Q (quarterly) filings for each ticker
on the watchlist. Filing text is downloaded and truncated to a size Claude
can process, then passed to the document analyzer.

Also supports 8-K fetching (material event disclosures) for real-time
catalyst monitoring.

### Financial Modeling Prep (`data/financials.py`)
Provides clean JSON financial statements via a free-tier API. Fetches:
- **Income statements** — revenue, gross margin, operating margin, EPS
- **Cash flow statements** — free cash flow, capex, operating cash flow
- **Balance sheets** — total debt, cash, equity, debt-to-equity
- **Key metrics** — ROE, ROIC, P/E, P/FCF (trailing twelve months)
- **EPS surprise history** — actual vs. estimated EPS, beat/miss percentage

### FRED API (`data/macro.py`)
The Federal Reserve's free data API. Fetches five macro indicators and
determines the direction (rising/falling/flat) for each:

| Indicator           | FRED Series | Why It Matters                         |
|---------------------|-------------|----------------------------------------|
| Fed Funds Rate      | DFF         | Cost of capital affects all valuations |
| CPI (inflation)     | CPIAUCSL    | Margin pressure, consumer spending     |
| 10-Year Treasury    | DGS10       | Discount rate for long-duration assets |
| Industrial Production | INDPRO    | Economic activity proxy                |
| Consumer Sentiment  | UMCSENT     | Forward demand indicator               |

Macro context is included in Claude's filing analysis prompts so the
assessment reflects the current economic environment.

---

## Analysis

### Document Analyzer (`analysis/document_analyzer.py`)
Sends filing text to Claude Opus (used for its large context window and
stronger reasoning on long documents). Returns a structured company profile:

```json
{
  "revenue_trend":        "growing | stable | declining",
  "margin_trend":         "expanding | stable | compressing",
  "key_risks":            ["up to 5 specific risks"],
  "key_opportunities":    ["up to 5 specific opportunities"],
  "management_tone":      "confident | cautious | defensive | neutral",
  "guidance_direction":   "raised | maintained | lowered | none",
  "thesis_score":         7,
  "thesis_summary":       "2–3 sentence investment case"
}
```

The macro context snapshot is prepended to the prompt so Claude can factor
in whether the company's outlook makes sense given current rates and growth.

### Earnings Scorer (`analysis/earnings_scorer.py`)
Scores each quarterly earnings report relative to expectations using the
EPS surprise history and income statement trends. Returns:

```json
{
  "revenue_beat":       true,
  "eps_beat":           true,
  "guidance_direction": "raised",
  "quality_score":      8,
  "trend":              "improving | stable | deteriorating",
  "summary":            "1–2 sentence assessment"
}
```

The `consecutive_beats()` helper counts how many quarters in a row a
company has beaten EPS estimates — a useful signal of management credibility
and guidance conservatism.

---

## Portfolio Monitoring

### Thesis Monitor (`portfolio/thesis_monitor.py`)
This is the most important component for active positions. When you add a
thesis for a stock (via `db.save_thesis()`), you record the core assumptions
that justified the entry. For example:

```
NVDA thesis:
  - AI infrastructure spending accelerating through 2027
  - Gross margins stable above 70%
  - No credible GPU competitor in data center market
```

After each analysis cycle, the thesis monitor sends these assumptions along
with the latest company profile and earnings score to Claude. Claude evaluates
each assumption as "valid", "weakened", or "broken" and gives an overall
status. If any assumption is broken or the overall status is flagged, the
thesis is marked in the database and highlighted in the weekly report.

This creates an early warning system — the flag typically appears in a filing
or earnings report before it shows up in the stock price.

---

## Reporting (`reports/weekly_report.py`)

Every Sunday (or on demand with `--report`), the system generates a markdown
report in `reports_output/`. The report covers:

- **Active theses** — status of each position's assumptions, flags highlighted
- **Earnings quality trends** — latest score, trend, beat/miss, guidance per ticker
- **Company profile scores** — thesis score, revenue trend, margin trend, tone
- **Macro environment** — current values and direction for all five indicators

Reports are plain markdown files, easy to read in any text editor or
rendered in VS Code / GitHub.

---

## Storage (`storage.py`)

Five SQLite tables in `longterm.db`:

| Table               | Contents                                              |
|---------------------|-------------------------------------------------------|
| `company_profiles`  | Claude's analysis of each 10-K / 10-Q per ticker     |
| `earnings_scores`   | Quarterly earnings quality scores                     |
| `thesis_log`        | Active investment theses and their assumption status  |
| `macro_snapshots`   | Rolling history of macro indicator values             |
| `financials`        | Raw financial statement data (revenue, margins, etc.) |

All tables use `UNIQUE` constraints on (ticker, period) so re-running
the cycle updates existing rows rather than creating duplicates.

---

## Configuration (`config.json`)

| Key                                      | Description                                       |
|------------------------------------------|---------------------------------------------------|
| `claude.model`                           | Use `claude-opus-4-6` for deep document analysis  |
| `fmp.api_key`                            | Financial Modeling Prep API key                   |
| `fred.api_key`                           | FRED API key                                      |
| `watchlist.tickers`                      | Stocks to track                                   |
| `analysis.earnings_lookback_quarters`    | How many quarters of history to fetch             |
| `analysis.min_thesis_score`             | Minimum Claude score to consider a stock watchable|
| `schedule.earnings_check_interval_hours` | How often to run a full cycle in scheduled mode   |
| `schedule.weekly_report_day`             | Day to auto-generate the weekly report            |
| `reports.output_dir`                     | Where to write weekly report markdown files       |

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Fill in config.json
#    - fmp.api_key     (financialmodelingprep.com — free tier)
#    - fred.api_key    (fred.stlouisfed.org/docs/api/api_key — free)

# 3. Set your Anthropic key
export ANTHROPIC_API_KEY=your_key

# 4. Run a full cycle
python main.py

# Run for a single ticker only
python main.py --ticker AAPL

# Generate the weekly report without re-running analysis
python main.py --report

# Run on an automated schedule (blocks — use screen/tmux or Task Scheduler)
python main.py --schedule
```

**Required accounts (all free):**
- [Financial Modeling Prep](https://financialmodelingprep.com) — financial data
- [FRED](https://fred.stlouisfed.org/docs/api/api_key.html) — macro indicators
- [Anthropic](https://console.anthropic.com) — Claude API
- SEC EDGAR — no account needed, free public API

---

## Recommended Workflow

**Initial setup:**
1. Add your watchlist tickers to `config.json`
2. Run `python main.py` to populate the database with filing analyses
3. For any stock you hold or are considering, call `db.save_thesis()` with
   the core assumptions behind your view

**Ongoing:**
- Run `python main.py --schedule` in the background on a server or VM
- It will re-analyze filings each earnings season automatically
- Check the weekly report every Sunday for thesis flags and trend changes
- Any flagged thesis means re-read the latest filing yourself before acting

**Before entering a position:**
- Check the `company_profiles` table for the thesis score and trend direction
- Check `earnings_scores` for consistency (consecutive beats, guidance trend)
- Check macro context — is the macro environment a headwind or tailwind?

---

## File Structure

```
LongTerm/
├── main.py                      Entry point — single run, scheduled, or report
├── config.json                  All configuration
├── loadconfig.py                Config loader and validation
├── storage.py                   SQLite schema and read/write methods
├── requirements.txt
├── data/
│   ├── edgar.py                 SEC EDGAR filing fetcher
│   ├── financials.py            Financial Modeling Prep API client
│   └── macro.py                 FRED macro indicator fetcher
├── analysis/
│   ├── document_analyzer.py     Claude Opus filing analyzer
│   └── earnings_scorer.py       Claude earnings quality scorer
├── portfolio/
│   └── thesis_monitor.py        Checks active theses for broken assumptions
└── reports/
    └── weekly_report.py         Generates weekly markdown summary
```
