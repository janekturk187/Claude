# DayTrading Launch Checklist

## Already Done
- [x] Fix missing `import os` in main.py

---

## BLOCKERS — System won't start without these

### 1. Fill in API keys (deploy/env.bat)
- [ ] Set `ANTHROPIC_API_KEY` — real Anthropic key
- [ ] Set `ALPACA_API_KEY` — paper trading key from Alpaca dashboard
- [ ] Set `ALPACA_SECRET_KEY` — paper trading secret from Alpaca dashboard
- [ ] Set `POLYGON_API_KEY` — Polygon.io API key

> loadconfig.py validates on startup — aborts if any still contain placeholder strings.

### 2. Install Python dependencies
- [ ] Run `pip install -r requirements.txt`
- [ ] Verify: `py -3 -c "import anthropic, alpaca, websocket, matplotlib"`

### 3. Register Windows Task Scheduler tasks
- [ ] Open elevated PowerShell and run:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  cd C:\Users\ironm\Claude\DayTrading
  .\deploy\register_tasks.ps1
  ```
- [ ] Verify in `taskschd.msc`:
  - "DayTrading - Start Paper Session" — 7:35 AM MT (9:35 AM ET) weekdays
  - "DayTrading - Stop Session" — 2:05 PM MT (4:05 PM ET) weekdays

---

## RECOMMENDED — Do before first live session

### 4. Dry-run the screener
- [ ] Run: `py -3 screening/runner.py`
- [ ] Confirm `watchlist.json` was created
- [ ] Confirm `reports_output/screener_YYYY-MM-DD.md` was generated

### 5. Dry-run the main system (~5 minutes)
- [ ] Run: `py -3 main.py --paper`
- [ ] Confirm "PAPER TRADING MODE" banner appears
- [ ] Confirm Alpaca websocket connects (bar data flowing)
- [ ] Confirm Polygon websocket connects (news stream active)
- [ ] Ctrl+C to stop — should generate session report on shutdown

### 6. Review config.json defaults
- [ ] `risk.max_position_pct` — 0.05 (5% of equity per trade)
- [ ] `risk.max_daily_loss_pct` — 0.02 (2% daily loss hard stop)
- [ ] `risk.max_open_positions` — 3 concurrent max
- [ ] `risk.reward_risk_ratio` — 2.0 (2:1 target/stop)
- [ ] `trading_hours` — 9:45-11:30, 1:30-3:30 ET
- [ ] `watchlist.tickers` — AAPL, MSFT, NVDA, TSLA, AMZN (fallback if screener finds nothing)

---

## NOT issues (just FYI)
- Path casing (claude vs Claude in bat files) — Windows is case-insensitive
- Database (daytrading.db) — auto-creates on first run
- logs/ directory — already exists
- reports_output/ directory — auto-creates via os.makedirs
- trading.pid — auto-created and cleaned up by the system
- Paper mode — already set to true in config.json

---

## Startup sequence on launch day

1. **9:35 AM ET** — Task Scheduler fires start_paper.bat
2. Screener fetches pre-market snapshots, picks top 5 gap stocks -> watchlist.json
3. main.py --paper starts, connects Alpaca + Polygon websockets
4. **9:45 AM ET** — Risk gate opens, signals can fire
5. Runs all day (midday pause 11:30-1:30 ET)
6. **4:05 PM ET** — Task Scheduler fires stop_trading.bat, generates session report + plots
