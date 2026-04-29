# CLAUDE.md — dshipe/stocks Codebase Guide

> This file helps AI assistants understand the architecture, conventions, and history
> of this codebase before making changes. Read this before touching anything.

---

## What This Project Is

A Python-based stock scanning system implementing **Kristjan Qullamaggie's breakout
methodology**. It runs two automated scanners daily on AWS EC2:

1. **Watchlist Scanner** (`scan/watchlist_scanner.py`) — 8:00 AM EST weekdays.
   Finds stocks approaching a breakout pivot. Writes to `watchlist_entries` table.
2. **Breakout Scanner** (`scan/breakout_scanner.py`) — every 30 min during market hours.
   Monitors watchlist entries for live breakout confirmation. Writes to `breakout_entries`.
3. **Performance Tracker** (`scan/performance_tracker.py`) — 4:30 PM EST weekdays.
   Tracks how breakouts performed. Writes to `watchlist_performance` / `breakout_performance`.

Reference material lives in `qullamaggie/` — blog posts, methodology notes, example charts.

---

## Repository Structure

```
stocks/
├── scan/
│   ├── watchlist_scanner.py      # Daily 8am watchlist generator (main entry point)
│   ├── breakout_scanner.py       # Intraday breakout detector
│   ├── performance_tracker.py    # End-of-day performance tracking
│   ├── config.py                 # ALL thresholds and DB config — edit here first
│   ├── cron_setup.sh             # Install cron jobs on EC2
│   ├── db_setup.sql              # SQL Server schema (idempotent, safe to re-run)
│   ├── requirements.txt          # Python deps (yfinance, pandas, pyodbc, etc.)
│   └── shared/
│       ├── criteria.py           # All stage filter functions (the core logic)
│       ├── data_fetcher.py       # yfinance wrappers + indicator computation
│       ├── db_writer.py          # SQL Server writes (pyodbc, parameterized queries)
│       └── telegram_notify.py    # Telegram bot alerts
├── plans/
│   ├── Rules-Reference.MD        # Complete rules table + threshold change log
│   ├── watchlist-plan.md         # Watchlist scanner design, rationale, change history
│   ├── breakout-scanner-plan.md  # Breakout scanner design
│   ├── breakout-scanner-usage.md # How to use the breakout scanner
│   └── watchlist-usage.md        # How to use the watchlist scanner
├── qullamaggie/
│   ├── breakouts/                # Rules.MD, Summary.MD, patterns, examples
│   ├── blog/                     # Qullamaggie blog post transcripts (01–09)
│   ├── index.md                  # Index and grading rubric
│   ├── summary.md                # Methodology summary
│   └── resources.md              # External links, videos
└── prompts.txt                   # Ad-hoc prompts used during development
```

---

## Stage Flow (as of 2026-04-29)

```
Stage 1   Universe Filter
          R1: price >= $5
          R2: avg daily volume >= 300k
          R3: ADR% >= 3% (daily movement potential)
              ↓
Stage 2   Momentum Trend  ← PRIMARY GATE (added 2026-04-29, never ages out)
          R6a: 1M (20d) gain >= 10%
          R6b: 3M (60d) gain >= 20%
          R6c: 6M (120d) gain >= 30%
          R9:  within 20% of 52-week high
              ↓
Stage 2b  Prior Explosive Move  ← BONUS GRADING ONLY (not a gate)
          R6: >= 25% move within 60 trading days
          R7: >= 1 day with 2x+ volume surge during move
              ↓
Stage 3   Consolidation Base
          R11: 5–40 trading days
          R12: base depth <= 20% (high to low)
          R14: price above 50d MA
          R16: 10d MA above 20d MA
              ↓
Stage 4   Volume Contraction
          R19: base avg volume <= 75% of 50d average
          R20: >= 3 consecutive below-average volume days
              ↓
Trigger   Watchlist Entry
          Stock must be 0–8% BELOW its pivot (base high)
          (If price > pivot: already broke out, excluded)
              ↓
Stage 5   Breakout Confirmation  ← Breakout scanner only
          R23: price > pivot
          R24: volume >= 1.5x avg
          R25: close within 5% of session high
```

---

## Key Design Decision: Why Stage 2 Uses Momentum, Not Event Detection

**Prior to 2026-04-29**, Stage 2 was `find_prior_explosive_move()` — a sliding 60-day window
looking for a specific ≥25% price event. The problem: stocks aged off the watchlist when
their initial move window expired, even if they were still market leaders.

**CVNA example:** On 2026-04-28 it was on the watchlist (+25% move in 43 days). Next day it
was gone — the window had moved. The stock itself hadn't changed.

**Fix:** Stage 2 is now `check_momentum_trend()` — multi-timeframe performance measurement
(1M/3M/6M). This measures *current state*, not a past event. It never ages out.

`find_prior_explosive_move()` still runs as **Stage 2b** for bonus grading:
- If found → contributes to grade score, appears in qualification_reasons
- If not found → grade falls back to 3M momentum scoring, stock still qualifies

---

## Config (`scan/config.py`)

**All thresholds live here.** Override any value via `.env` in the `scan/` directory.
Never hardcode thresholds in criteria.py or the scanner files.

| Parameter | Value | Stage | Description |
|-----------|-------|-------|-------------|
| `MIN_PRICE` | $5.00 | 1 | R1: minimum stock price |
| `MIN_AVG_VOLUME` | 300,000 | 1 | R2: 20-day avg volume floor |
| `MIN_ADR_PCT` | 3.0% | 1 | R3: minimum average daily range |
| `MIN_MOMENTUM_1M_PCT` | 10% | 2 | R6a: 1-month gain floor |
| `MIN_MOMENTUM_3M_PCT` | 20% | 2 | R6b: 3-month gain floor |
| `MIN_MOMENTUM_6M_PCT` | 30% | 2 | R6c: 6-month gain floor |
| `MAX_FROM_52W_HIGH` | 20% | 2 | R9: max distance from 52-week high |
| `MIN_PRIOR_MOVE_PCT` | 25% | 2b | R6: minimum explosive move (was 30%) |
| `MAX_PRIOR_MOVE_DAYS` | 60 | 2b | R6: window for prior move (was 40) |
| `MIN_VOL_SURGE_RATIO` | 2.0× | 2b | R7: volume surge multiplier |
| `MIN_BASE_DAYS` | 5 | 3 | R11: minimum base duration |
| `MAX_BASE_DAYS` | 40 | 3 | R11: maximum base duration |
| `MAX_BASE_DEPTH_PCT` | 20% | 3 | R12: base depth limit (was 15%) |
| `MAX_BASE_VOL_RATIO` | 0.75 | 4 | R19: volume contraction threshold (was 0.60) |
| `MIN_CONSEC_LOW_VOL_DAYS` | 3 | 4 | R20: consecutive quiet days required |
| `MAX_DIST_FROM_PIVOT_PCT` | 8% | trigger | proximity to pivot (was 5%) |
| `MIN_BREAKOUT_VOL_RATIO` | 1.5× | 5 | R24: breakout volume multiplier |
| `MAX_CLOSE_FROM_HIGH_PCT` | 5% | 5 | R25: candle quality check |

---

## Database (SQL Server)

**Server:** `ec2-35-172-202-150.compute-1.amazonaws.com`
**Database:** `python`
**User:** `ai-agent`

Credentials live in `config.py` (read from `.env`). Schema is in `scan/db_setup.sql`.

### Tables

| Table | Written by | Purpose |
|-------|-----------|---------|
| `watchlist_entries` | watchlist_scanner.py | Daily watchlist results |
| `watchlist_performance` | performance_tracker.py | Tracks watchlist entry outcomes |
| `breakout_entries` | breakout_scanner.py | Confirmed intraday breakouts |
| `breakout_performance` | performance_tracker.py | Tracks breakout outcomes |

### Key Columns (watchlist_entries)

```sql
scan_date, ticker, price_at_scan, pivot_price, pct_from_pivot,
prior_move_pct, prior_move_days,          -- Stage 2b (0 if no prior move found)
base_depth_pct, base_duration_days,
volume_contraction_ratio,
adr_pct, avg_daily_volume,
ma10_above_ma20, above_50d_ma,
volume_contraction_days,
qualification_reasons,                     -- JSON array of human-readable strings
pattern_type,                              -- VCP / HTF / FlatBase / Pennant
pattern_grade                              -- A+ / A / B / C
```

---

## `shared/criteria.py` — The Core Logic

All stage functions are here. Rules references (e.g. R6) match `plans/Rules-Reference.MD`.

| Function | Stage | Description |
|----------|-------|-------------|
| `check_universe_filter(df, ticker)` | 1 | Price, volume, ADR check |
| `check_momentum_trend(df)` | 2 | Multi-timeframe momentum gate |
| `find_prior_explosive_move(df)` | 2b | Event detection (bonus grading) |
| `find_consolidation_base(df, peak_date)` | 3 | Base quality check |
| `check_volume_contraction(df, base_start_date)` | 4 | Volume dry-up check |
| `check_breakout(intraday, base, avg_vol_20d)` | 5 | Live breakout confirmation |
| `detect_pattern_type(df, base)` | — | VCP / HTF / FlatBase / Pennant |
| `grade_setup(prior_move, base, vol, pattern, momentum)` | — | Grade A+/A/B/C |
| `build_qualification_reasons(...)` | — | JSON reasons string for DB |

**Important:** `prior_move` and `momentum` are both optional in `grade_setup()` and
`build_qualification_reasons()`. Always pass both when available; handle `None` safely.

---

## `shared/data_fetcher.py`

- `get_ticker_universe()` — scrapes S&P 500 + Nasdaq-100 from Wikipedia (~516 tickers).
  Falls back to a hardcoded list if Wikipedia is unreachable.
- `fetch_history(ticker, days=365)` — yfinance daily OHLCV. Returns `None` on failure.
- `fetch_intraday(ticker)` — 1-minute bars for today. Used by breakout scanner.
- `compute_indicators(df)` — adds ma10/ma20/ma50, avg_vol_20d/50d, atr_14, adr_pct.

**Data source:** yfinance (free). To swap in Polygon.io or another provider,
replace `fetch_history()` and `fetch_intraday()` — the rest of the code is source-agnostic.

---

## Notifications

Telegram bot configured via `.env`:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```
`telegram_notify.py` sends a summary at the end of each watchlist scan.
If env vars are not set the notification is silently skipped — no crash.

---

## Cron Schedule (EC2, UTC)

```
0  13 * * 1-5   watchlist_scanner.py       # 8:00 AM EST
0,30 14-20 * * 1-5  breakout_scanner.py    # Every 30 min, 9:30 AM–4:00 PM EST
0  21 * * 1-5   breakout_scanner.py        # Final run at 4:00 PM EST
30 21 * * 1-5   performance_tracker.py     # 4:30 PM EST
```

Logs: `/var/log/stock-scanner/watchlist.log`, `breakout.log`, `performance.log`

---

## Running Manually

```bash
cd ~/stocks/scan

# Full scan (writes to DB)
python3 watchlist_scanner.py

# Dry run (print only, no DB write)
python3 watchlist_scanner.py --dry-run

# Single ticker debug
python3 watchlist_scanner.py --dry-run --ticker AAPL

# Breakout scanner (force run outside market hours)
python3 breakout_scanner.py --force --dry-run
```

---

## Conventions

- **All thresholds in `config.py`.** Never hardcode a number in criteria.py.
- **Log changes.** Every threshold change gets a row in `plans/Rules-Reference.MD`
  (change log table) and a section in `plans/watchlist-plan.md`.
- **Parameterized queries only.** No string formatting of SQL in `db_writer.py`.
- **Return `None` to fail a stage.** All criteria functions return `None` on miss,
  a populated dict on pass. The scanner treats `None` as "drop this stock".
- **`prior_move` is optional everywhere.** Since 2026-04-29, Stage 2b is not a gate.
  All downstream functions handle `prior_move=None` gracefully.
- **DB schema is in `db_setup.sql`.** It's idempotent — safe to re-run. If you add
  a column, add it there too with a `IF NOT EXISTS` guard.

---

## Known Issues / Tech Debt

1. **No market holiday calendar** — `is_market_open()` uses weekday check only.
   Add `pandas_market_calendars` for accurate holiday handling.
2. **yfinance rate limits** — 516-ticker scans hit yfinance sequentially.
   Consider adding a small `time.sleep(0.1)` between requests or batching.
3. **Ticker universe is S&P 500 + NDX only** — misses many mid/small-cap breakouts.
   Consider adding Russell 2000 or a broader screener universe.
4. **No dedup on watchlist_entries** — same ticker can appear multiple days.
   Consider a UNIQUE constraint on (scan_date, ticker).
5. **Telegram chat ID hardcoded in .env** — works, but multi-user delivery
   would require a more flexible notification layer.
6. **No backtesting harness** — criteria changes are validated by running on current
   data only. A proper backtest would replay historical bars.

---

## Threshold Change Log Summary

| Date | Parameter | Old | New | Reason |
|------|-----------|-----|-----|--------|
| 2026-04-27 | `MIN_PRIOR_MOVE_PCT` | 30% | 25% | More stocks qualify |
| 2026-04-27 | `MAX_PRIOR_MOVE_DAYS` | 40 | 60 | Valid setups form up to 12w post-move |
| 2026-04-27 | `MAX_BASE_DEPTH_PCT` | 15% | 20% | Energy stocks form wider bases |
| 2026-04-27 | `MAX_BASE_VOL_RATIO` | 0.60 | 0.75 | Stage 4 was too restrictive post-move changes |
| 2026-04-29 | `MAX_DIST_FROM_PIVOT_PCT` | 5% | 8% | SNDK was 6.3% from pivot, valid setup |
| 2026-04-29 | `find_prior_explosive_move` end_idx | uncapped | capped at `len-1-MIN_BASE_DAYS` | WDC/SNDK silently dropped — peak too recent for base |
| 2026-04-29 | Stage 2 gate | Prior move (ages out) | Momentum trend (never ages out) | CVNA aged off despite being a market leader |
| 2026-04-29 | `MIN_MOMENTUM_1M_PCT` | — | 10% | New Stage 2 parameter |
| 2026-04-29 | `MIN_MOMENTUM_3M_PCT` | — | 20% | New Stage 2 parameter |
| 2026-04-29 | `MIN_MOMENTUM_6M_PCT` | — | 30% | New Stage 2 parameter |

Full history: `plans/Rules-Reference.MD` → Criteria Change Log table.

---

*Generated: 2026-04-29 | Reflects all changes through 2026-04-29*
