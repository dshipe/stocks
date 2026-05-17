# CLAUDE.md

## Commands

```bash
# Run the daily watchlist scanner
cd scan && python3 watchlist_scanner.py

# Dry run (no DB writes)
python3 watchlist_scanner.py --dry-run

# Debug a single ticker
python3 watchlist_scanner.py --dry-run --ticker NVDA

# Intraday breakout scanner (force outside market hours)
python3 breakout_scanner.py --force --dry-run

# Performance tracker (end-of-day)
python3 performance_tracker.py --dry-run

# Backtest (1 year, S&P 500)
python3 backtest_scanner.py --years 1 --universe sp500

# Check live performance data
python3 check_performance.py

# Install cron jobs
chmod +x cron_setup.sh && ./cron_setup.sh
```

## Architecture

Three scanners run on AWS EC2 (Ubuntu 24.04) via cron:

| Scanner | Schedule | Output table |
|---------|----------|-------------|
| `watchlist_scanner.py` | 8:00 AM EST weekdays | `watchlist_entries`, `runner_entries` |
| `breakout_scanner.py` | Every 30 min, 9:30–4:00 PM EST | `breakout_entries` (checks watchlist + runners) |
| `performance_tracker.py` | 4:30 PM EST weekdays | `watchlist_performance`, `breakout_performance`, `runner_performance` |

**Data source:** yfinance (free, no API key). Swap in Polygon.io by replacing
`fetch_history()` / `fetch_intraday()` in `shared/data_fetcher.py` — rest of code is source-agnostic.

**Ticker universe:** `yahoo_fin.stock_info` — `tickers_sp500()` + `tickers_nasdaq()` (combined ~3,500+
tickers after dedup and junk-symbol filtering). Symbols are pre-filtered by `_is_valid_ticker()`
to strip warrants (`-W`, `-WS`), rights (`-R`), and units (`-U`) before any network call.
If `tickers_sp500()` returns HTTP 403, falls back to a GitHub-hosted S&P 500 CSV
(`datasets/s-and-p-500-companies`) via `requests`.

**Bulk data fetch:** `bulk_fetch_history()` in `shared/data_fetcher.py` downloads 200 tickers per
`yf.download()` call (vs. one request per ticker). Criteria evaluation then runs in parallel via
`ThreadPoolExecutor(max_workers=16)` in `watchlist_scanner.run_scan()`. Full Nasdaq scan takes
~5 minutes instead of 45+

**Database:** SQL Server on `ec2-35-172-202-150.compute-1.amazonaws.com`, DB `python`.
Schema is in `scan/db_setup.sql` (idempotent — safe to re-run).
Credentials in `scan/.env` (never in source).
Tables: `watchlist_entries`, `watchlist_performance`, `breakout_entries`,
`breakout_performance`, `runner_entries`, `runner_performance`.

## Stage Pipeline (`shared/criteria.py`)

```
Stage 1   check_universe_filter()      price ≥ $5, vol ≥ 300k, ADR ≥ 3%
Stage 2   check_momentum_trend()       1M ≥ 5%, 3M ≥ 15%, 6M ≥ 30%, near 52w high  ← NEVER AGES OUT
Stage 2b  find_prior_explosive_move()  ≥ 25% in 60d w/ vol surge — bonus grading only, NOT a gate
Stage 3   find_consolidation_base()    5–40 days, depth ≤ 20%
          → if base FOUND: Trigger (0–8% below pivot) → watchlist_entries
          → if base NONE:  check_runner_state() → if markup phase → runner_entries
Stage 4   check_volume_contraction()   base vol ≤ 85% of 50d avg — bonus grading only, NOT a gate
Stage 5   check_breakout()             price > pivot + last 30-min vol ≥ 3x avg 30-min vol + candle near high (base-pivot path)
          check_adr_breakout()          move ≥ 0.5× ADR% from prev close + 30-min vol ≥ 2x avg + near session high (ADR parallel path)
          → both paths run in parallel; base-pivot takes precedence if both fire
          → breakout scanner also checks runner_entries for intraday base formation
```

## Config (`scan/config.py`)

**All thresholds live here.** Override via `scan/.env`. Never hardcode values in criteria.py.

Key params:
- `MIN_MOMENTUM_1M/3M/6M_PCT` — Stage 2 momentum thresholds (5% / 15% / 30%)
- `MAX_DIST_FROM_PIVOT_PCT` — watchlist trigger proximity (8%)
- `MAX_BASE_DEPTH_PCT` — Stage 3 base tightness (20%)
- `MAX_BASE_VOL_RATIO` — Stage 4 volume contraction (0.85) — grading signal only, not a gate
- `MIN_BREAKOUT_GRADE` — global grade floor for breakout alerts (default B — C excluded)
- `MIN_HTF_BREAKOUT_GRADE` — HTF-specific floor (default A — HTF/B excluded; backtest shows -0.40% avg 5d)
- `MIN_RUNNER_PRICE` — runner price floor (default $10, tighter than Stage 1 $5)
- `MIN_RUNNER_AVG_VOLUME` — runner volume floor (default 500k, tighter than Stage 1 300k)

## Key Conventions

- **Thresholds only in `config.py`.** If you find a hardcoded number in criteria.py, move it.
- **Return `None` to fail a stage.** All criteria functions return `None` on miss, a dict on pass.
- **`prior_move` is optional everywhere.** Since 2026-04-29, Stage 2b is not a gate. `grade_setup()` and `build_qualification_reasons()` both accept `prior_move=None`.
- **Runners vs watchlist.** Stocks that pass S1+S2 but have no base go to `runner_entries` via
  `check_runner_state()` (price > MA20 > MA50, within 10% of 20d high, prior explosive move required).
  Controlled by `MAX_RUNNER_FROM_20D_HIGH=10.0` and `RUNNER_REQUIRE_PRIOR_MOVE=true` in config. They appear on the
  main watchlist automatically when a base forms — no manual promotion needed.
- **Log threshold changes.** Add a row to the change log table in `docs/Rules-Reference.MD` and a section in `docs/watchlist-plan.md`. Do not change thresholds silently.
- **Parameterized queries only** in `db_writer.py`. No string-formatted SQL.
- **Schema changes go in `db_setup.sql`** with `IF NOT EXISTS` guards.

## Why Stage 2 Is Momentum, Not Prior Move

Before 2026-04-29, Stage 2 was `find_prior_explosive_move()` — an event detector with a
60-day sliding window. Stocks aged off the watchlist when the window expired, even if they
were still market leaders (CVNA was a real example of this).

`check_momentum_trend()` measures *current* 1M/3M/6M performance. It never ages out.
`find_prior_explosive_move()` still runs as Stage 2b for grading bonus — but failing it
does not drop a stock. Do not revert this to a gate.

## Plans & Rules Docs

- `docs/Rules-Reference.MD` — complete rules table (R1–R46), thresholds, change log
- `docs/watchlist-plan.md` — design decisions, rationale, historical changes, runners section
- `docs/breakout-scanner-plan.md` — breakout scanner design, ADR path, grade filters, implementation history
- `docs/schwab-integration.md` — stop-loss manager + watchlist sync (auth, rate limits, scheduling)
- `docs/how-to-trade.md` — practical trading guide (when to buy, grade/pattern guidance, exit rules)
- `docs/performance-analysis.md` — live and backtest performance findings, action items
- `qullamaggie/breakouts/Rules.MD` — source methodology

## Backtest

`scan/backtest_scanner.py` runs the full Stage 1–4 pipeline against historical data:
- Point-in-time simulation (no look-ahead bias — slices data to each trading day)
- Measures 1d/5d/10d/20d forward returns for all qualifying entries
- Reports by grade, pattern, and quarter; saves full results to CSV

Key 1-year backtest findings (S&P 500, May 2025 – Apr 2026):
- **A+ grade**: +12.4% avg 20d, 79% win rate — act on every alert
- **FlatBase (A/A+)**: +11.5% avg 20d, 73% BO rate — best pattern at higher grades
- **HTF/B**: -0.40% avg 5d, 36% BO rate — excluded from alerts by default
- **Q1 2026 (choppy market)**: avg 20d only +0.22% — market regime matters

## Tech Debt

- No market holiday calendar (`is_market_open()` uses weekday only)
- No dedup constraint on `watchlist_entries(scan_date, ticker)` at the DB schema level (inserts are deduplicated in code via WHERE NOT EXISTS)
- `tickers_nasdaq()` from yahoo_fin returns all Nasdaq-listed stocks (~5,000+); no pre-screen
  by market cap or price before the bulk download. Stage 1 drops most, but the download is wide.