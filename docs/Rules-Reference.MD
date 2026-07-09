# Qullamaggie Rules — Quick Numeric Reference

> All rules in order, R1 through R46, with thresholds used in the scanner.
> Full explanations: `Rules.MD` | Implementation: `scan/shared/criteria.py` | Config: `scan/config.py`
>
> **🔧 Modified rules:** R6 (prior move % and lookback window), R19 (volume contraction ratio), R_RUN1/R_RUN2 (runner gates tightened 2026-05-06), R43/R45 (market filter implemented 2026-07-08), R33/R34/R36/R37/R38 (position sizing + profit-target alerts added 2026-07-08) — see [Criteria Change Log](#criteria-change-log) below.

---

| # | Stage | Rule | Original Criteria | Current Criteria | Modified | Scanner |
|---|-------|------|-------------------|-----------------|----------|---------|
| **R1** | Universe | Price minimum | ≥ $5.00 | ≥ $5.00 | | ✅ |
| **R2** | Universe | Avg daily volume | ≥ 300,000 shares (20-day) | ≥ 300,000 shares (20-day) | | ✅ |
| **R3** | Universe | ADR% minimum | ≥ 3% | ≥ 3% | | ✅ |
| **R4** | Universe | Exchange | Not OTC / pink sheets | Not OTC / pink sheets | | — |
| **R5** | Universe | Market cap | ≥ $300M preferred | ≥ $300M preferred | | — |
| **R6** | Prior Move | Minimum move % | ≥ **30%** from a recent low | ≥ **25%** from a recent low | 🔧 2026-04-27 | ✅ |
| **R6** | Prior Move | Move lookback window | Within **40** trading days | Within **60** trading days | 🔧 2026-04-27 | ✅ |
| **R7** | Prior Move | Volume surge in move | ≥ 1 day with vol ≥ 2× avg | ≥ 1 day with vol ≥ 2× avg | | ✅ |
| **R8** | Prior Move | Catalyst | Clear identifiable catalyst | Clear identifiable catalyst | | — |
| **R9** | Prior Move | 52-week high proximity | Within 10–20% of 52w high | Within 20% of 52w high | | ✅ |
| **R10** | Prior Move | Relative strength | ≥ 50% more than S&P 500 | ≥ 50% more than S&P 500 | | — |
| **R11** | Base | Duration | 5–40 trading days | 5–40 trading days | | ✅ |
| **R12** | Base | Depth | ≤ **15%** (ideally ≤ 10%) | ≤ **20%** (ideally ≤ 10%) | 🔧 2026-04-27 | ✅ |
| **R13** | Base | Single candle body | ≤ 10% body range | ≤ 10% body range | | — |
| **R14** | Base | 50-day MA | Price above 50d MA | Price above 50d MA | | ✅ |
| **R15** | Base | 20-day MA | Price above 20d MA | Price above 20d MA | | ✅ |
| **R16** | Base | MA alignment | 10d MA above 20d MA | 10d MA above 20d MA | | ✅ |
| **R17** | Base | VCP legs | ≥ 2 contraction legs | ≥ 2 contraction legs | | — |
| **R18** | Base | Earnings in base | No earnings in base | No earnings in base | | — |
| **R19** | Volume | Base vol contraction | Base avg vol ≤ **60%** of 50d avg | Base avg vol ≤ **75%** of 50d avg | 🔧 2026-04-27 | ✅ |
| **R20** | Volume | Consecutive low-vol days | ≥ 3 consecutive days | ≥ 3 consecutive days | | ✅ |
| **R21** | Volume | Distribution days | No high-vol down days (last 5) | No high-vol down days (last 5) | | — |
| **R22** | Volume | Volume profile | Declining as base narrows | Declining as base narrows | | — |
| **R23** | Breakout | Price trigger | Above consolidation high (pivot) | Above consolidation high (pivot) | | ✅ |
| **R24** | Breakout | Breakout volume | ≥ 150% of 20-day avg | ≥ 300% of avg 30-min candle volume (intensity, historical per-time-slot baseline — fixed 2026-07-08, was self-referential) | 🔧 2026-05-07 / 2026-07-08 | ✅ |
| **R25** | Breakout | Candle strength | Closes within 5% of candle high | Closes within 5% of candle high | | ✅ |
| **ADR1** | ADR Breakout | Intraday move | — | ≥ 0.5× ADR% from prev close (parallel path) | 🔧 2026-05-11 | ✅ |
| **ADR2** | ADR Breakout | Volume | — | Last 30-min candle ≥ 2× avg 30-min vol (same approach as R24) | 🔧 2026-05-11 | ✅ |
| **ADR3** | ADR Breakout | Candle strength | — | Closes within 5% of session high (shared with R25) | 🔧 2026-05-11 | ✅ |
| **R26** | Breakout | Earnings proximity | No earnings within 3 days | No earnings within 3 days | | — |
| **R27** | Breakout | Market trend | S&P 500 / NASDAQ uptrend | S&P 500 / NASDAQ uptrend | | ✅ |
| **R28** | Breakout | Intraday entry | Break of Opening Range High | Break of Opening Range High | | — |
| **R29** | Risk | Stop placement | Base low − 0.5% buffer | Base low − 0.5% buffer | | ✅ |
| **R30** | Risk | Stop distance | ≤ 1× ATR-14 | ≤ 1× ATR-14 | | — |
| **R31** | Risk | Max risk per trade | 0.5% of account | 0.5% of account | | — |
| **R32** | Risk | Position size | Dollar Risk ÷ (Entry − Stop) | Dollar Risk ÷ (Entry − Stop) | | — |
| **R33** | Risk | Max position | 20% of account per stock | 20% of account per stock (`select_trades.py` — advisory sizing report, not a live scanner gate) | 🔧 2026-07-08 | ✅ |
| **R34** | Risk | Volume impact | ≤ 1% of stock's ADV | ≤ 1% of stock's ADV (`select_trades.py` — advisory sizing report) | 🔧 2026-07-08 | ✅ |
| **R35** | Risk | Min R/R ratio | ≥ 2:1 | ≥ 2:1 | | ✅ |
| **R36** | Exit | First partial sale | Sell 1/3–1/2 at 2R | Sell 1/3–1/2 at 2R (alert-only via `check_profit_targets.py` — no auto-execution) | 🔧 2026-07-08 | ✅ |
| **R37** | Exit | Stop move | Move to breakeven after 2R | Move to breakeven after 2R (alert-only — no live stop order placed) | 🔧 2026-07-08 | ✅ |
| **R38** | Exit | Second partial sale | Sell 1/4 at 3R | Sell 1/4 at 3R (alert-only via `check_profit_targets.py`) | 🔧 2026-07-08 | ✅ |
| **R39** | Exit | Trail stop | 10-day MA close | 10-day MA close | | — |
| **R40** | Exit | Alt trail | 20-day MA (extended trends) | 20-day MA (extended trends) | | — |
| **R41** | Exit | Failed breakout | Exit on close below pivot | Exit on close below pivot | | ✅ |
| **R42** | Exit | Earnings hold | Exit unless ≥ 30% cushion | Exit unless ≥ 30% cushion | | — |
| **R43** | Market | S&P trend | Above 50d and 200d MA | Above 50d and 200d MA — now actually gates alerts (was metadata-only and silently broken — `ma200` was never computed, every call threw and fell back to `{}`) | 🔧 2026-07-08 | ✅ |
| **R44** | Market | Distribution | No distribution phase | No distribution phase | | — |
| **R45** | Market | VIX | VIX < 30 | VIX < 30 (now fetched via `^VIX` and gates alerts; previously hardcoded `None`) | 🔧 2026-07-08 | ✅ |
| **R46** | Market | Sector | Sector in uptrend | Sector in uptrend | | — |
| **R_RUN1** | Runner | Near recent high | — | Within **10%** of 20-day high (`MAX_RUNNER_FROM_20D_HIGH`) | 🔧 2026-05-06 | ✅ |
| **R_RUN2** | Runner | Prior move required | — | `find_prior_explosive_move()` must return a result (`RUNNER_REQUIRE_PRIOR_MOVE`) | 🔧 2026-05-06 | ✅ |
| **R_RUN3** | Runner | Price floor | — | Price ≥ **$10** (`MIN_RUNNER_PRICE`) — filters micro-caps with extreme % moves from tiny base | 🔧 2026-05-16 | ✅ |
| **R_RUN4** | Runner | Volume floor | — | Avg vol ≥ **500k** (`MIN_RUNNER_AVG_VOLUME`) — ensures liquidity | 🔧 2026-05-16 | ✅ |
| `MIN_BREAKOUT_GRADE` | -- (all grades) | **B** | Breakout alert filter | 🔧 2026-05-16 |
| `MIN_HTF_BREAKOUT_GRADE` | -- (all HTF grades) | **A** | HTF alert filter | 🔧 2026-05-16 |

---

## Scanner Coverage

**✅ Implemented** — rule is checked in `scan/shared/criteria.py`
**—** — not yet automated (manual check or future enhancement)

Of the 46 rules, **25 are automated** in the current scanner (R6a, R6b, R6c added 2026-04-29;
R33, R34, R36, R37, R38, R45 added 2026-07-08 — R33/R34/R36-R38 as advisory/alert-only tools,
not live scanner gates; R43 fixed from silently-broken metadata to an actual gate).
R44 and R46 remain unautomated — no distribution-day detector or sector data source exists yet.

---

## Thresholds (Current Config)

Modify in `scan/config.py` or override via `scan/.env`:

| Setting | Original | Current | Rule | Modified |
|---------|----------|---------|------|----------|
| `MIN_PRICE` | $5.00 | $5.00 | R1 | |
| `MIN_AVG_VOLUME` | 300,000 | 300,000 | R2 | |
| `MIN_ADR_PCT` | 3.0% | 3.0% | R3 | |
| `MIN_MOMENTUM_1M_PCT` | — | **5%** | R6a | 🔧 2026-04-29 |
| `MIN_MOMENTUM_3M_PCT` | — | **15%** | R6b | 🔧 2026-04-29 |
| `MIN_MOMENTUM_6M_PCT` | — | **30%** | R6c | 🔧 2026-04-29 |
| `MIN_PRIOR_MOVE_PCT` | **30%** | **25%** | R6 (2b bonus) | 🔧 2026-04-27 |
| `MAX_PRIOR_MOVE_DAYS` | **40** | **60** | R6 | 🔧 2026-04-27 |
| `MIN_VOL_SURGE_RATIO` | 2.0× | 2.0× | R7 | |
| `MAX_FROM_52W_HIGH` | 20% | 20% | R9 | |
| `MIN_BASE_DAYS` | 5 | 5 | R11 | |
| `MAX_BASE_DAYS` | 40 | 40 | R11 | |
| `MAX_BASE_DEPTH_PCT` | **15%** | **20%** | R12 | 🔧 2026-04-27 |
| `MAX_BASE_VOL_RATIO` | **60%** | **85%** | R19 | 🔧 2026-04-27 / 2026-04-29 |
| `MIN_CONSEC_LOW_VOL_DAYS` | 3 | 3 | R20 | |
| `MAX_DIST_FROM_PIVOT_PCT` | 5% | **8%** | Watchlist trigger | 🔧 2026-04-29 |
| `MIN_BREAKOUT_30MIN_VOL_RATIO` | — | **3.0×** | R24 (30-min intensity) | 🔧 2026-05-07 |
| `MIN_BREAKOUT_VOL_RATIO` | 1.5× | 1.5× | R24 (legacy ref only) | |
| `MAX_CLOSE_FROM_HIGH_PCT` | 5% | 5% | R25 / ADR3 | |
| `MIN_ADR_BREAKOUT_MULT` | — | **0.5×** | ADR1 | 🔧 2026-05-11 |
| `MIN_ADR_BREAKOUT_30MIN_VOL_RATIO` | — | **2.0×** | ADR2 (30-min intensity) | 🔧 2026-05-11 |
| `MAX_RUNNER_FROM_20D_HIGH` | — (hardcoded 15%) | **10%** | R_RUN1 | 🔧 2026-05-06 |
| `RUNNER_REQUIRE_PRIOR_MOVE` | — (false) | **true** | R_RUN2 | 🔧 2026-05-06 |
| `MIN_RUNNER_PRICE` | — ($5 Stage 1 floor) | **$10** | R_RUN3 | 🔧 2026-05-16 |
| `MIN_RUNNER_AVG_VOLUME` | — (300k Stage 1 floor) | **500k** | R_RUN4 | 🔧 2026-05-16 |
| `INTRADAY_VOL_BASELINE_LOOKBACK_DAYS` | — (new) | **20** | R24 / ADR2 | 🔧 2026-07-08 |
| `ENABLE_MARKET_FILTER` | — (new) | **true** | R43 / R45 | 🔧 2026-07-08 |
| `MAX_VIX_LEVEL` | — (new) | **30.0** | R45 | 🔧 2026-07-08 |
| `ACCOUNT_SIZE` | — (new) | **$500,000** | R33 / R34 | 🔧 2026-07-08 |
| `MAX_POSITION_PCT` | — (new) | **20%** | R33 | 🔧 2026-07-08 |
| `MAX_PCT_OF_ADV` | — (new) | **1.0%** | R34 | 🔧 2026-07-08 |
| `MAX_CONCURRENT_POSITIONS` | — (new) | **10** | Position selection | 🔧 2026-07-08 |

---

## Stage Flow

```
R1–R5    Universe Filter         → price ≥ $5, vol ≥ 300k, ADR ≥ 3%
    ↓
R6a–R6c  Momentum Trend (Stage 2)→ up ≥5%/15%/30% over 1M/3M/6M — NEVER AGES OUT (🔧 2026-04-29)
    ↓
R6–R10   Prior Move (Stage 2b)   → ≥25% in 60 days w/ vol surge — bonus grading only (🔧 2026-04-29)
    ↓
R11–R18  Base Quality            → tight consolidation 5–40 days, ≤20% depth (🔧 was 15%)
    ↓
R19–R22  Volume Contraction      → bonus grading only, not a gate (🔧 demoted 2026-04-29)
    ↓
         Watchlist Trigger       → within 8% of pivot → add to watchlist (🔧 was 5%)
    ↓
R23–R28  Breakout (base-pivot) → price > pivot + 30-min vol ≥ 3× avg + strong candle
ADR1–3   Breakout (ADR path)  → move ≥ 0.5× ADR% from prev close + 30-min vol ≥ 2× avg 30-min + near session high
         (both paths run in parallel; base-pivot takes precedence if both fire)
    ↓
R29–R35  Position Sizing      → stop below base low, 0.5% account risk, ≥2:1 R/R
                                 (R33/R34 advisory sizing via select_trades.py, 🔧 2026-07-08)
    ↓
R36–R42  Exit Management      → scale out at 2R/3R (alert-only via check_profit_targets.py,
                                 🔧 2026-07-08), trail 10d MA (live via schwab_stop_loss.py),
                                 exit failed breakouts
    ↓
R43–R46  Market Filter        → S&P above MAs + low VIX now GATE new alerts (🔧 2026-07-08,
                                 was metadata-only/broken); distribution phase + sector
                                 uptrend (R44/R46) still not implemented
```

---

## Criteria Change Log

| Date | Parameter | Original Value | New Value | Reason |
|------|-----------|----------------|-----------|--------|
| 2026-04-27 | `MIN_PRIOR_MOVE_PCT` | 30% | 25% | Analysis of 516 tickers showed 25 additional stocks would qualify; prior move still confirmed with volume surge (R7) |
| 2026-04-27 | `MAX_PRIOR_MOVE_DAYS` | 40 days | 60 days | Analysis showed 29 additional stocks would qualify; valid setups often form 10–12 weeks after the explosive move |
| 2026-04-27 | `MAX_BASE_VOL_RATIO` | 60% | 75% | After prior move changes, Stage 4 became the binding constraint; loosened to capture setups with adequate but not extreme volume contraction |
| 2026-04-27 | `MAX_BASE_DEPTH_PCT` | 15% | 20% | 21 stocks failing Stage 3 due to depth > 15%; energy/commodity stocks form wider bases by nature. Analysis showed +12 additional stocks at 20% threshold |
| 2026-04-29 | `MAX_DIST_FROM_PIVOT_PCT` | 5% | **8%** | SNDK was 6.3% below its pivot after a brief pullback from all-time high — a valid pre-breakout setup excluded by the old 5% trigger |
| 2026-04-29 | `find_prior_explosive_move` logic | uncapped end_idx | capped at `len-1-MIN_BASE_DAYS` | WDC peaked 4 days ago; uncapped loop set peak_date=today leaving <5 days for base detection. Both SNDK and WDC were silently dropped at Stage 3 |
| 2026-04-29 | Stage 2 gate | Prior explosive move (ages out after 60d) | **Multi-timeframe momentum** (1M/3M/6M — never ages out) | CVNA fell off watchlist when its initial move aged past the 60d window despite being a market leader. Prior move demoted to Stage 2b bonus grading. |
| 2026-04-29 | `MIN_MOMENTUM_1M_PCT` | — (new) | **10%** | New Stage 2 gate parameter |
| 2026-04-29 | `MIN_MOMENTUM_3M_PCT` | — (new) | **20%** | New Stage 2 gate parameter |
| 2026-04-29 | `MIN_MOMENTUM_6M_PCT` | — (new) | **30%** | New Stage 2 gate parameter |
| 2026-04-29 | `MIN_MOMENTUM_1M_PCT` | 10% | **5%** | Diagnostic: 112/174 stocks failing 1M gate alone; consolidating stocks have naturally flat 1M |
| 2026-04-29 | `MIN_MOMENTUM_3M_PCT` | 20% | **15%** | Recovers ~20 additional stocks with strong 6M trends but moderate 3M |
| 2026-04-29 | `MAX_BASE_VOL_RATIO` | 0.75 | **0.85** | 13 stocks (KLAC, MRVL, BKR, JBL, FIX etc.) failing Stage 4 with ratios 0.76–0.85 |
| 2026-04-29 | Stage 4 gate | Hard gate (drops stock) | **Bonus grading only** | 17/20 Stage 3 stocks dropped at vol contraction; consistent with Stage 2b philosophy — use quality signals for ranking, not exclusion |
| 2026-04-30 | Ticker universe source | Wikipedia (S&P 500 + Nasdaq-100, ~600 tickers) | **yahoo_fin** (S&P 500 + full Nasdaq, ~3,000+ tickers) | Wikipedia scrape was fragile (403 errors, lxml dep); yahoo_fin is cleaner and covers far more stocks |
| 2026-04-30 | Data fetch method | Sequential `fetch_history()` (1 request/ticker) | **`bulk_fetch_history()`** (200 tickers/request) + **ThreadPoolExecutor** criteria eval | Sequential scan of 3,000 tickers was ~45 min; bulk+parallel brings it to ~5 min |
| 2026-04-30 | S&P 500 source | yahoo_fin (Wikipedia scrape, 403 on EC2) | yahoo_fin → GitHub CSV fallback (`datasets/s-and-p-500-companies`) | EC2 IP blocked by Wikipedia; GitHub raw serves CSV without auth |
| 2026-04-30 | Telegram large watchlist | Single message (fails at 4096 chars) | `_send_chunked()` splits on blank lines into ≤4000-char parts | 53-stock watchlist caused 400 Bad Request from Telegram API |
| 2026-04-30 | `bulk_fetch_history` single-ticker batch | `raw.copy()` (flat DF assumed) | `raw[ticker].copy()` always | yfinance ≥1.x returns MultiIndex even for 1-ticker batches; caused silent skip of SNDK, WDC, and any `--ticker` run |
| 2026-04-30 | Stage 3 failure handling | Stock silently dropped | **Runners list** -- `check_runner_state()` captures markup-phase stocks in `runner_entries` | SNDK, WDC pass S1+S2 but have no base; now tracked as runners until they consolidate |
| 2026-04-30 | Runner performance | Not tracked | `runner_performance` table -- 1d/5d/10d/20d/60d outcomes + `did_set_up` + `days_to_setup` | Mirrors watchlist_performance; enables analysis of how long runners take to set up |
| 2026-04-30 | Breakout scanner scope | Watchlist only | **Watchlist + Runners** -- `check_runner_breakout()` runs every 30 min against runner_entries | Catches same-day runner->base->breakout transitions the morning scan would miss |
| 2026-05-06 | Runner gates tightened | MAX_RUNNER_FROM_20D_HIGH=15%, RUNNER_REQUIRE_PRIOR_MOVE=false | **10% proximity + prior move required** | Performance data showed runner list had too many generic momentum stocks with no known catalyst |
| 2026-05-07 | R24 volume check | Cumulative daily vol >= 1.25x 20d avg | **Last 30-min candle >= 3x avg 30-min vol** | At 10 AM cumulative vol is ~1/13th of daily total -- intraday intensity is the correct intraday proxy |
| 2026-05-11 | ADR breakout path added | Base-pivot only | **Parallel ADR path** -- move >= 0.5x ADR% + 30-min vol >= 2x avg + near session high | Catches episodic pivots and news surges without requiring a prior base |
| 2026-05-16 | Watchlist dedup | Plain INSERT (allowed duplicates) | **WHERE NOT EXISTS guard** in `insert_watchlist_entry()` | Performance analysis found many duplicate (scan_date, ticker) rows inflating counts |
| 2026-05-16 | `MIN_RUNNER_PRICE` | -- ($5 Stage 1 floor) | **$10** | Micro-caps $5-$10 produced noisy signals with extreme 3M% (e.g. +1294%) from tiny base |
| 2026-05-16 | `MIN_RUNNER_AVG_VOLUME` | -- (300k Stage 1 floor) | **500k** | Low-float runners are illiquid and hard to trade at meaningful size |
| 2026-05-16 | `MIN_BREAKOUT_GRADE` | None (all grades alerted) | **B** -- C excluded from breakout alerts | Backtest: C-grade has lower BO rate (50%) and high variance; not worth intraday monitoring |
| 2026-05-16 | `MIN_HTF_BREAKOUT_GRADE` | None (all HTF grades alerted) | **A** -- HTF/B excluded from breakout alerts | Backtest: HTF/B averages -0.40% at 5d with 36% BO rate; HTF/A+ is best combo in dataset (+12.4% avg 20d) |
| 2026-07-08 | `fetch_intraday()` avg_30min_volume (R24/ADR2) | Mean of today's own 30-min bars (self-referential) | **Historical per-time-slot baseline** -- avg volume per time-of-day slot over trailing 20 trading days | Self-reference made the >=3x/2x ratio mathematically near-impossible early in the day; root cause of zero rows in `breakout_entries` from table inception (2026-04-30) through 2026-07-08 |
| 2026-07-08 | `compute_indicators()` | ma10, ma20, ma50 only | **+ ma200** | `get_sp500_context()` referenced `last["ma200"]`, threw KeyError on every call, silently fell back to `{}` -- R43 metadata was NULL on every breakout entry ever recorded |
| 2026-07-08 | SPY context fetch window | 250 calendar days | **400 calendar days** | 250 days was not reliably enough trading days for a valid 200-day rolling MA |
| 2026-07-08 | R43/R45 (Stage 8 market filter) | Recorded as metadata only, never gated a trade | **Actual gate** in `breakout_scanner.py` -- unfavorable conditions suppress new alerts (still logged, tagged SUPPRESSED) | Backtest showed choppy-market periods (Q1 2026, avg 20d only +0.22%) are exactly what this gate should filter; previously had zero effect |
| 2026-07-08 | `vix_level` | Hardcoded `None` | **Fetched via `^VIX`** | Needed for R45 to actually function |
| 2026-07-08 | `grade_setup()` pattern bonus | `+1` for `pattern_type in ("VCP", "HTF")` | **`+1` for VCP only** | HTF getting the same bonus as VCP undermined `MIN_HTF_BREAKOUT_GRADE=A`, letting weak HTF setups cross into grade A; live trade simulation showed HTF as the worst-performing pattern by avg P&L despite the bonus |
| 2026-07-08 | R36-R38 (profit-taking) | Not implemented anywhere | **Alert-only** via new `check_profit_targets.py` -- Telegram alert at 2R/3R, no auto-execution | R29 (initial stop) and R39 (trailing stop) already had live execution via `schwab_stop_loss.py`; profit-taking had none. Live order placement was explicitly deferred (user chose alert-only over full automation) |
| 2026-07-08 | R33/R34 (position sizing / concentration) | Not implemented -- every qualifying alert fired regardless of account size | **`select_trades.py`** -- advisory report that ranks a day's alerts and sizes each to `min(20% of account, 1% of ADV)` within `ACCOUNT_SIZE`/`MAX_CONCURRENT_POSITIONS` | System had no concept of account size; ~10-50 alerts/day is not tradable by one account without a selection layer |
| 2026-07-08 | `watchlist_entries(scan_date, ticker)` index | Non-unique (`WHERE NOT EXISTS` app-level guard only) | **UNIQUE index** (DB-level backstop) | Verified zero existing duplicates before upgrading; closes a known tech-debt gap (app-level guard was the only protection) |
| 2026-07-08 | `is_market_open()` | Weekday check only, no holiday awareness | **+ NYSE holiday calendar** (`is_market_holiday()`, no new dependency) -- does not yet handle early-close days | Known tech debt; verified against 8 known 2026 holidays including Good Friday (Easter-based) and the July 4th Saturday->Friday-observed shift |
| 2026-07-08 | Performance tracking entry price | Stored once at scan/breakout time, never adjusted for later stock splits | **Re-derived from the same split-adjusted fetch used for exit prices** (`rebase_for_splits()` in `performance_tracker.py`) | yfinance retroactively adjusts an entire history for splits on every fetch; comparing an old unadjusted stored price against newly-adjusted closes produced fake cliffs (KLAC's 2026-06-12 10-for-1 split showed as a fake -90% "loss") |
| 2026-07-08 | `max_gain_pct` (watchlist/runner/breakout performance) | Best-case only; no worst-case equivalent | **+ `max_drawdown_pct`/`max_drawdown_date`** (worst CLOSE within the 20-day window) | No way to simulate realistic stop-outs without a worst-case metric; used by `trade_simulator.py` |
