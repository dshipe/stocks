# Performance Analysis

## 2026-05-16 — First 3-Week Read (2026-04-27 to 2026-05-15)

### Data Coverage

| List | Entries | 5d data | 10d data | 20d data |
|------|---------|---------|---------|---------|
| Watchlist | 877 | 240 | 26 | 0 |
| Runners | 586 | 104 | — | 0 |

20d is entirely blank and 10d is thin (26 entries). All conclusions below are provisional — revisit when 10d fills in (~2026-05-29) and 20d matures (~2026-06-12).

---

### Watchlist — By Grade

| Grade | N | Avg 5d | Avg 10d | Max Gain | BO% |
|-------|---|--------|---------|---------|-----|
| A+ | 3 | -8.8% | — | -2.5% | 0% |
| A | 28 | +4.3% | +14.3% | +11.8% | 89% |
| B | 71 | +4.6% | +2.0% | +11.9% | 85% |
| C | 138 | +6.2% | +17.2% | +12.4% | 78% |

**Observations:**
- Grade ordering is inverted — C is outperforming A+ on both 5d and 10d. A+ has only 3 entries so that's noise, not signal.
- B and C have similar 5d returns (+4.6% vs +6.2%) with large sample sizes, suggesting the grading rubric isn't yet strongly differentiating outcomes. Needs more data.
- Breakout rates (78–89% across all grades) are high and consistent — the pivot proximity filter is working. Stocks flagged as near a pivot really are close enough to break out.

---

### Watchlist — By Pattern

| Pattern | N | Avg 5d | Avg 10d | BO% |
|---------|---|--------|---------|-----|
| VCP | 17 | +2.8% | +19.0% | 94% |
| FlatBase | 79 | +5.2% | +19.0% | 80% |
| Pennant | 64 | +8.0% | +14.7% | 80% |
| HTF | 80 | +3.8% | -0.9% | 79% |

**Observations:**
- VCP and FlatBase both show +19% at 10d — best quality patterns by this metric.
- Pennant has the best 5d return (+8.0%) but trails at 10d (+14.7%).
- **HTF is the red flag:** 79% breakout rate but -0.9% at 10d. Breaking out and then reversing. The HTF detector (`base_depth <= 10%`, `duration <= 15d`) may be triggering on extended stocks rather than genuinely tight setups. Investigate individual HTF entries — if the pattern is being over-detected, consider tightening the depth or duration thresholds.

---

### Runners

| Metric | Value |
|--------|-------|
| Entries | 586 (2026-04-30 to 2026-05-15) |
| Avg 5d return | +6.8% |
| Avg max gain (20d window) | +15.8% |
| % eventually set up | 38% |
| % broke out | 66% |
| Avg days to setup | 6d |

**Observations:**
- Runners are the strongest signal so far. +6.8% avg 5d with +15.8% max gain is well above the watchlist averages.
- 66% breakout rate vs 38% setup rate means many runners break out intraday via the breakout scanner directly, without ever forming a multi-day base. That's the system working as designed.
- 6-day average time to setup is fast — runners don't stay in markup long before consolidating.

---

### Key Caveats

- **Market environment:** The 3-week window (late April to mid-May 2026) was generally a strong tape. All numbers could look materially different in a choppy or declining market.
- **Sample sizes:** A+ (3 entries) and VCP (17 entries) are too small to draw firm conclusions. B, C, FlatBase, and HTF have sufficient samples.
- **No 20d data yet:** The most important return interval for this style of trading (give a setup 3-4 weeks to develop) is entirely blank. All conclusions here are based on short-term momentum only.

---

### Action Items

| Priority | Item |
|----------|------|
| High | Investigate HTF entries — check if pattern detector is over-triggering on extended stocks |
| Medium | Re-run this analysis in 2 weeks when 10d data is fuller |
| Medium | Re-run in 4 weeks when first 20d data arrives |
| Low | Once 60+ 10d entries exist, compare grade A vs C more rigorously — current inversion may resolve |

---

*Generated: 2026-05-16*
*Data source: `watchlist_performance`, `runner_performance` tables via `scan/check_performance.py`*
*Next review: ~2026-05-29 (10d data), ~2026-06-12 (20d data)*
