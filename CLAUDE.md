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

# Rules-based $ P&L backtest over tracked breakouts
python3 trade_simulator.py
python3 trade_simulator.py --position-size 25000 --grades A+,A,B

# Rank today's alerts and pick trades within a capital budget (advisory, R33/R34)
python3 select_trades.py
python3 select_trades.py --date 2026-07-08 --account-size 250000

# Repair performance rows for one ticker regardless of completeness (e.g. after a bug fix)
python3 performance_tracker.py --ticker KLAC

# Alert (not execute) on 2R/3R profit targets for open Schwab positions
python3 schwab_scripts/check_profit_targets.py --dry-run

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
Schema is in `scan/db_setup.sql` (idempotent — safe to re-run; schema changes to
already-existing tables go in the "Migrations" section using
`IF NOT EXISTS (SELECT ... FROM sys.columns ...) ALTER TABLE ... ADD ...`, added 2026-07-08).
Credentials in `scan/.env` (never in source).
Tables: `watchlist_entries`, `watchlist_performance`, `breakout_entries`,
`breakout_performance`, `runner_entries`, `runner_performance`, `profit_target_alerts`
(added 2026-07-08 — dedup log for `check_profit_targets.py`, alert-only, no orders placed).

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
- `INTRADAY_VOL_BASELINE_LOOKBACK_DAYS` — R24/ADR2 historical volume baseline window (default 20 days, added 2026-07-08)
- `ENABLE_MARKET_FILTER` / `MAX_VIX_LEVEL` — Stage 8 market gate (R43/R45; default on / VIX < 30, added 2026-07-08)
- `ACCOUNT_SIZE` / `MAX_POSITION_PCT` / `MAX_PCT_OF_ADV` / `MAX_CONCURRENT_POSITIONS` — R33/R34 position sizing, used by `select_trades.py` (added 2026-07-08)

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

## Why avg_30min_volume Uses a Historical Baseline, Not Today's Own Bars

Before 2026-07-08, `fetch_intraday()` computed `avg_30min_volume` as the mean of **today's
own** 30-min bars — self-referential, since the mean always included the very candle being
tested against it. This made R24/ADR2 (`last_30min_vol / avg_30min_vol >= 3x` / `2x`)
mathematically close to impossible early in the day, and still very hard even near the
close. Root cause of `breakout_entries` having zero rows for 2+ months straight despite
`watchlist_entries`/`runner_entries` populating normally the whole time.

`fetch_intraday_volume_baseline()` now fetches 60 days of 30-min-interval history and
averages volume per time-of-day slot over the trailing `INTRADAY_VOL_BASELINE_LOOKBACK_DAYS`
(20) trading days — a genuine historical comparison. **Do not revert to a same-day
average** — it reintroduces this exact bug.

That fix itself was DOA: it used `df.resample("30T")`, and pandas 3.0 removed the `"T"`
minute alias, so `fetch_intraday()` raised on every call, was swallowed by a
`logger.debug`-level `except`, and returned `None` — keeping `breakout_entries` at zero
rows for another six weeks with no visible error. Fixed 2026-08-19 by switching to
`resample("30min")`. See `docs/breakout-scanner-plan.md` item 14.

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

> These findings predate the 2026-07-08 `grade_setup()` fix (HTF removed from the VCP
> pattern bonus — see `docs/watchlist-plan.md` issue #18) and the R43/R45 market filter
> going live. A live trade simulation on 2026-07-08 found A-grade barely outperforming
> C-grade in practice, contradicting the A+ numbers above — see
> `docs/performance-analysis.md`'s 2026-07-08 snapshot. Re-run `backtest_scanner.py` before
> trusting these specific numbers going forward.

## Tech Debt

- `tickers_nasdaq()` from yahoo_fin returns all Nasdaq-listed stocks (~5,000+); no pre-screen
  by market cap or price before the bulk download. Stage 1 drops most, but the download is wide.
- R44 (distribution-day detection) and R46 (sector trend) are not automated — no rolling
  distribution-day counter and no ticker→sector mapping / sector ETF history exist in this
  codebase. R43/R45 were fixed and now gate alerts (2026-07-08); R44/R46 remain metadata-free.
- `check_profit_targets.py` (R36-R38 profit-target alerts) is not in `cron_setup.sh` — cadence
  (intraday vs. daily) hasn't been decided.
- R29 (initial stop at base-low) is not enforced live — `schwab_stop_loss.py` sets/raises
  stops at the 10-day SMA from day one, not at the base-low stop the breakout scanner
  computes and stores in `breakout_entries.stop_price`.
- `select_trades.py` and `trade_simulator.py` are read-only advisory/analysis tools, not
  wired into the live scanner pipeline — they don't change what alerts fire.
- `is_market_open()`'s holiday calendar (added 2026-07-08) doesn't model early-close days
  (e.g. day after Thanksgiving, Christmas Eve) — those still report "open" until 4pm.
- Split/reverse-split detection (`rebase_for_splits()`, added 2026-07-08) only fires when
  `performance_tracker.py` processes a row — a ticker that splits and is never scanned again
  (or whose row is already "complete" and thus outside the normal pending-rows query) needs
  the `--ticker` force-reprocess flag run manually. No automatic detection of *which*
  tickers have split since their entries were recorded.
- Grade calibration (`grade_setup()`) was fixed once (2026-07-08, HTF removed from the VCP
  pattern bonus) based on a small live sample (146 A/A+ trades). Needs re-validation against
  a fresh `backtest_scanner.py` run once more data accumulates under the fix.