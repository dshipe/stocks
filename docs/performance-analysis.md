# Performance Analysis

---

## Backtest — 1 Year (May 2025 – Apr 2026, S&P 500)

*Run: 2026-05-16 | `backtest_scanner.py --years 1 --universe sp500`*
*2,353 qualifying entries across 122 unique tickers, 241 trading days*

### Overall

| Metric | All Grades | A+/A/B Only |
|--------|-----------|-------------|
| Avg 5d | +0.85% | +0.45% |
| Avg 10d | +1.75% | +0.77% |
| Avg 20d | +4.69% | +4.29% |
| BO Rate | 47% | 43% |
| Win Rate (5d > 0) | 53% | 52% |

Filtering to A+/A/B slightly lowers short-term averages because C-grade was contributing positively at 5d. The filter is correct for risk and signal clarity — not for raw return maximization.

### By Grade

| Grade | N | Avg 5d | Avg 10d | Avg 20d | Max Gain | BO% | Win 5d |
|-------|---|--------|---------|---------|---------|-----|--------|
| **A+** | 14 | +3.83% | +7.14% | +12.42% | +19.79% | 71% | 79% |
| A | 162 | +0.42% | +0.81% | +5.46% | +11.62% | 44% | 54% |
| B | 828 | +0.40% | +0.66% | +3.92% | +10.49% | 42% | 51% |
| C | 1,349 | +1.14% | +2.49% | +4.99% | +12.20% | 50% | 54% |

A+ is the clear leader at every interval. A and B perform nearly identically — the grading rubric is not differentiating them meaningfully. C actually outperforms A and B at short timeframes, which suggests the grading formula needs recalibration.

### By Pattern (All Grades)

| Pattern | N | Avg 5d | Avg 10d | Avg 20d | BO% | Win 5d |
|---------|---|--------|---------|---------|-----|--------|
| FlatBase | 601 | +1.67% | +3.24% | +7.08% | 54% | 55% |
| Pennant | 730 | +1.28% | +2.60% | +5.35% | 53% | 58% |
| VCP | 201 | +0.39% | +2.54% | +6.18% | 35% | 52% |
| **HTF** | 821 | **-0.02%** | **-0.28%** | +1.98% | 40% | 47% |

HTF is the only pattern negative at 5d and 10d. Drilling in reveals it's entirely concentrated in HTF/B.

### HTF Deep Dive

| Grade | N | Avg 5d | Avg 20d | BO% | Win 5d |
|-------|---|--------|---------|-----|--------|
| HTF/A+ | 14 | +3.83% | +12.42% | 71% | 79% |
| HTF/A | 156 | +0.37% | +5.35% | 44% | 53% |
| **HTF/B** | **499** | **-0.40%** | **+1.11%** | **36%** | **42%** |
| HTF/C | 152 | +0.47% | +0.45% | 45% | 51% |

**HTF/A+ is the single best grade-pattern combination in the dataset.** HTF/B is the worst — 499 entries averaging -0.40% at 5d with only 42% win rate. HTF/B is now excluded from breakout alerts by default (`MIN_HTF_BREAKOUT_GRADE=A`).

### By Pattern (A+/A/B Only)

| Pattern | N | Avg 5d | Avg 10d | Avg 20d | BO% | Win 5d |
|---------|---|--------|---------|---------|-----|--------|
| **FlatBase** | 30 | +4.56% | +9.02% | +11.52% | 73% | 70% |
| **Pennant** | 170 | +1.86% | +2.35% | +8.21% | 59% | 69% |
| VCP | 135 | +0.62% | +3.27% | +7.42% | 36% | 55% |
| HTF | 669 | -0.13% | -0.51% | +2.33% | 39% | 46% |

FlatBase (A+/A/B) is exceptional — +11.52% avg 20d, 73% BO, 70% win — but only 30 entries across the year. When a FlatBase earns an A or A+ grade, it is genuinely rare and should be treated as highest priority.

### By Quarter

| Quarter | N | Avg 5d | Avg 10d | Avg 20d | BO% |
|---------|---|--------|---------|---------|-----|
| 2025-Q2 | 90 | -0.07% | +1.51% | +4.99% | 47% |
| **2025-Q3** | 447 | **+2.34%** | **+4.13%** | **+7.14%** | **58%** |
| 2025-Q4 | 804 | +0.46% | +1.57% | +6.25% | 43% |
| **2026-Q1** | 854 | **+0.37%** | **+0.34%** | **+0.22%** | 45% |
| 2026-Q2* | 158 | +1.70% | +3.77% | +13.80% | 49% |

Q3 2025 was the strongest quarter (strong tape, momentum stocks leading). Q1 2026 nearly flat at 20d — the tariff/macro volatility period when S&P was below its 50-day MA. **Market regime dominates setup quality.** The system should effectively shut down during confirmed downtrends.

### Proximity to Pivot (A+/A/B)

| Distance from Pivot | N | Avg 20d | BO% |
|---------------------|---|---------|-----|
| 0–2% | 310 | +3.93% | **67%** |
| 2–4% | 312 | +4.03% | 42% |
| 4–6% | 238 | +4.72% | 29% |
| 6–8% | 143 | +4.91% | 15% |

Stocks within 2% of the pivot break out 67% of the time within 5 days. Stocks 6–8% away only break out 15% of the time but deliver similar 20d returns when they eventually move. **The proximity filter narrows timing, not outcome quality.** Trade stocks closest to the pivot for fastest execution; farther entries require patience.

### Best Recurring Tickers (A+/A/B, 5+ appearances)

| Ticker | Days | Avg 5d | Avg 20d | Note |
|--------|------|--------|---------|------|
| WDC | 10 | +4.18% | +25.38% | Storage cycle winner |
| MU | 27 | +7.73% | +18.76% | Semiconductor — consistent |
| CIEN | 39 | +3.36% | +18.63% | Networking infrastructure |
| ALB | 18 | +6.65% | +18.14% | Lithium/battery |
| TER | 50 | +1.73% | +17.65% | Semiconductor equipment |
| KEYS | 13 | +14.76% | +17.26% | Test & measurement |
| STX | 12 | +7.70% | +15.53% | Storage — multiple legs |
| AMAT | 43 | -1.93% | +7.92% | Slow developer — needs time |

Semiconductors and storage dominated the best performers. AMAT is negative at 5d but +7.92% at 20d — it requires the full cycle to pay off.

### Top 10 Individual Setups (A+/A/B, by 20d)

| Date | Ticker | Grade | Pattern | 5d | 10d | 20d |
|------|--------|-------|---------|-----|-----|-----|
| 2025-12-30 | MU | B | Pennant | +16.0% | +13.9% | +48.9% |
| 2025-12-31 | MU | B | Pennant | +14.6% | +17.9% | +45.4% |
| 2026-04-02 | INTC | C* | FlatBase | +23.8% | +36.0% | +97.7% |
| 2025-08-22 | STX | A | VCP | +5.1% | +18.9% | +44.0% |
| 2026-01-27 | TER | B | VCP | +18.4% | +27.6% | +43.5% |
| 2025-10-14 | SNDK | C* | FlatBase | +17.3% | +37.9% | +113.4% |

*C-grade entries not monitored by the breakout scanner under current settings.

### Worst 10 Individual Setups (A+/A/B, by 20d)

| Date | Ticker | Grade | Pattern | 20d | Note |
|------|--------|-------|---------|-----|------|
| 2026-01-22 | EPAM | B | HTF | -36.6% | Jan 2026 macro selloff |
| 2026-01-28 | EPAM | B | HTF | -36.5% | Same environment |
| 2026-01-26 | CVNA | B | Pennant | -31.4% | Jan 2026 |
| 2026-01-22 | CVNA | B | Pennant | -29.6% | Jan 2026 |
| 2025-08-04 | SMCI | B | Pennant | -30.0% | Earnings/accounting issues |

January 2026 (S&P below 50d MA) accounts for the majority of the worst setups. The market regime filter would have blocked most of these.

---

## Live Performance — First 3 Weeks (Apr 27 – May 15, 2026)

*Run: 2026-05-16 | `check_performance.py`*
*Very early data — 20d returns not yet available*

| Metric | Watchlist | Runners |
|--------|-----------|---------|
| Total entries | 818 (post-dedup) | 586 |
| Entries with 5d data | 181 | 104 |
| Avg 5d return | +various by grade | +6.8% |
| BO rate | 78–89% | 66% |
| Avg days to setup (runners) | — | 6d |

Live watchlist breakout rates (78–89%) are significantly higher than the backtest (42–71%), suggesting the live period (May 2026) is a strong tape. Full comparison will be possible when 20d data fills in around June 12, 2026.

---

## Live Performance — 2026-07-08 Snapshot

*Run: 2026-07-08 | `check_performance.py`, `trade_simulator.py`, manual DB investigation*

**`breakout_entries` had zero rows since table inception (2026-04-30).** Root cause: a
self-referential bug in `fetch_intraday()`'s `avg_30min_volume` calculation made R24/ADR2's
volume-intensity checks mathematically near-impossible to satisfy (see
`docs/breakout-scanner-plan.md`, issue #11). `watchlist_entries` (3,844) and `runner_entries`
(1,829) had been populating normally the entire time — only the breakout confirmation step
was silently broken. Fixed same day.

**Grade wasn't discriminating as well as the backtest implied.** A $50k-position, rules-based
trade simulation over 2,402 confirmed breakouts (`did_break_out=1` in `watchlist_performance`,
used as a retrospective proxy since `breakout_entries` was empty) showed:

| Grade | N | Total P&L | Avg P&L | Win % |
|---|---|---|---|---|
| A+ | 3 | +$7,243 | +$2,414 | 100% |
| A | 143 | +$131,007 | +$916 | 53.1% |
| B | 653 | +$702,594 | +$1,076 | 53.1% |
| C | 1,603 | +$2,492,671 | +$1,555 | 52.9% |

A vs. C win rate was statistically indistinguishable, and C had a *higher* average $ P&L
than A — contradicting the backtest's A+ = 79% win rate / +12.4% avg 20d expectation. Root
cause found: `grade_setup()`'s pattern bonus rewarded HTF equally with VCP, letting weak HTF
setups artificially cross the `MIN_HTF_BREAKOUT_GRADE=A` floor meant to exclude them (see
`docs/watchlist-plan.md`, issue #18). Fixed same day — bonus restricted to VCP only.
**This resolves the "Recalibrate A vs B grading rubric" action item below**, though full
validation needs a fresh backtest run once enough live data accumulates under the fix.

**Data-quality artifacts found in split-affected tickers.** KLAC, MULL, INTW, and PSIG all
showed fabricated ~-90% "losses" in tracked performance. Root cause: `performance_tracker.py`
compared a stored (pre-split) entry price against freshly-fetched (post-split-adjusted)
exit prices — confirmed against KLAC's real 10-for-1 split on 2026-06-12. Fixed via
`rebase_for_splits()`, and all four tickers' historical rows were repaired via a new
`--ticker` force-reprocess flag on `performance_tracker.py` (normal runs only touch
"pending"/incomplete rows, so already-fully-populated corrupted rows needed an explicit
reprocess). KLAC verified: 5d return went from a fake -89.97% to a real ~0.0%.

**Added `max_drawdown_pct`/`max_drawdown_date`** (worst CLOSE within the 20-day window,
mirroring the existing `max_gain_pct`) to all three performance tables — closes the
"no worst-case metric" gap that previously made realistic stop-loss simulation impossible.
`trade_simulator.py` now uses it to detect stop-outs across the whole window, not just the
four sampled 1d/5d/10d/20d checkpoints.

---

## Action Items

| Priority | Item | Status |
|----------|------|--------|
| Done | Exclude C-grade from breakout alerts | `MIN_BREAKOUT_GRADE=B` |
| Done | Exclude HTF/B from breakout alerts | `MIN_HTF_BREAKOUT_GRADE=A` |
| Done | Add runner quality floor ($10 price, 500k vol) | `MIN_RUNNER_PRICE`, `MIN_RUNNER_AVG_VOLUME` |
| Done | Fix watchlist entry deduplication | `WHERE NOT EXISTS` guard + 2026-07-08: upgraded to a DB-level UNIQUE index |
| Done (2026-07-08) | Recalibrate A vs B grading rubric | `grade_setup()` pattern bonus was rewarding HTF same as VCP — restricted to VCP only. Needs a fresh backtest to confirm improvement. |
| Done (2026-07-08) | Add market regime gate (S&P 50d MA) | Was recorded but silently broken (`ma200` never computed) and never enforced — now fetches VIX too and actually gates new alerts (R43/R45) |
| Pending | Investigate HTF pattern detection | HTF/A+ excellent, HTF/B systematically poor — grading fix (above) should help, but root pattern-detection quality is untouched |
| Done (2026-07-08) | Fix zero rows in `breakout_entries` | `avg_30min_volume` self-referential bug in `fetch_intraday()` — see snapshot above |
| Done (2026-07-08) | Fix split-adjustment data corruption (KLAC, MULL, INTW, PSIG) | `rebase_for_splits()` in `performance_tracker.py`; historical rows repaired |
| Done (2026-07-08) | Add worst-case (drawdown) performance metric | `max_drawdown_pct`/`max_drawdown_date` added to all 3 performance tables |
| Done (2026-07-08) | Implement R33/R34 position sizing | `select_trades.py` — advisory report, not a live scanner gate |
| Done (2026-07-08) | Implement R36-R38 profit-taking | `check_profit_targets.py` — alert-only, no live order placement |
| Pending | Re-run `backtest_scanner.py` after the grading fix | Confirm grade discrimination actually improved with real data, not just the boundary-case test used to verify the fix |
| Pending | Decide `check_profit_targets.py` cadence and schedule it | Currently not in `cron_setup.sh` — intraday vs. daily is an open choice |

---

*Next review: ~2026-05-29 (10d data), ~2026-06-12 (20d data), ~2026-07-08 findings above*
*See also: `docs/how-to-trade.md`, `docs/Rules-Reference.MD`, `scan/backtest_scanner.py`, `scan/trade_simulator.py`*
