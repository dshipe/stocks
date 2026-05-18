# How to Trade the Scanner

> Practical guide to using the daily watchlist, breakout alerts, and runners list.
> Based on Qullamaggie momentum breakout methodology + 1-year backtest (May 2025 – Apr 2026).

---

## The Three Outputs

| Output | What it is | When to act |
|--------|-----------|-------------|
| **Watchlist** (8 AM) | Stocks within 8% of their pivot, in a tight base | Prepare — set alerts, size positions. Do NOT buy yet. |
| **Breakout alert** (intraday) | Watchlist stock crossing its pivot on strong volume | This is your entry signal. Buy if the candle confirms. |
| **Runners list** (8 AM) | Strong stocks still in markup — no base formed yet | Watch only. Wait for them to set up and appear on the watchlist. |

---

## Daily Workflow

### 8:00 AM — Review the Watchlist

After the scan runs, a Telegram summary arrives. For each stock on the list:

1. **Pull up the chart.** Does the base look clean? Is the stock near the pivot?
2. **Note the pivot price.** That is your buy trigger for the day.
3. **Pre-calculate position size:**
   ```
   Dollar Risk   = Account Size × 0.5%
   Stop Distance = Entry Price − Stop Price  (stop = base low × 0.995)
   Share Count   = Dollar Risk ÷ Stop Distance
   Max Position  = Account Size × 20%  (hard cap per stock)
   ```
4. **Set a price alert in Schwab** at the pivot price for each A and A+ setup.

You do not buy just because something is on the watchlist. It is coiling near a breakout level — it has not done anything yet.

---

### During the Day — Act on Breakout Alerts

When a Telegram alert fires:

```
🚨 BREAKOUT — CELH  🔥 [A+]

   Price: $49.40  (pivot $49.00)
   Volume: 4.2× avg
   Pattern: VCP  |  Prior move: +67% / 22d
   Stop: $44.20  |  R/R: 3.2:1
```

**Before buying, check three things:**

1. **Is the candle still strong?** Price should be within 5% of its session high. If it has reversed back below the pivot, skip it — that is a failed breakout.
2. **Is volume still expanding?** Look at the 5-minute bars. Volume should be accelerating, not fading.
3. **Is the market healthy?** If the S&P 500 is below its 50-day MA, consider skipping or going half size. The backtest showed Q1 2026 (tariff volatility, S&P below 50d) averaged only +0.22% at 20 days vs +7% in Q3 2025 when the tape was strong.

**If all three check out — buy near the current price and place your stop immediately.**

Do not chase more than 2–3% above the pivot. If you missed the entry, let it go — there will be another setup.

---

### How to Size by Grade

Backed by 2,353 entries across the 1-year backtest:

| Grade | Avg 20d | BO Rate | Win Rate | Suggested Sizing |
|-------|---------|---------|----------|-----------------|
| **A+** | +12.4% | 71% | 79% | Full size — highest conviction |
| **A** | +5.5% | 45% | 54% | Full size |
| **B** | +3.9% | 42% | 51% | Half to full size |
| **C** | +5.0% | 50% | 54% | No intraday alert — visible on morning Telegram summary only |

A+ is rare — only ~14 per year in the S&P 500 universe. When one fires, treat it as highest priority.

> **Note:** C-grade entries are written to the watchlist and appear in the morning Telegram summary, but the breakout scanner will not monitor them or send alerts. If you want to trade a C-grade setup manually, you can set your own price alert in Schwab.

---

### Pattern Guidance

| Pattern | Avg 20d | BO Rate | Notes |
|---------|---------|---------|-------|
| **FlatBase (A/A+)** | +11.5% | 73% | Exceptional when graded A or above. Rare — only ~30/year in S&P 500 backtest. |
| **Pennant (A/A+)** | +8.2% | 59% | Best win rate (69% at 5d). Reliable at every timeframe. |
| **VCP** | +6.2% | 35% | Low immediate BO rate — needs time to develop. Give it the full 20 days. |
| **HTF (A/A+)** | +12.4% | 71% | Highest conviction when graded A+. Act on every A+ HTF alert. |
| **HTF (B)** | +1.1% | 36% | **No alert sent** — excluded by default. Backtest: -0.40% avg 5d, 42% win rate. |

---

## Exit Rules

### Rule 1 — Stop loss (non-negotiable)

Exit the full position if price touches `base_low × 0.995`. Pre-calculated for every setup and stored in `breakout_entries.stop_price`. No exceptions, no averaging down.

### Rule 2 — Failed breakout (3-day rule)

If price closes back **below the pivot** within 3 trading days of entry, exit immediately — do not wait for the stop. A close below the pivot means institutional buyers did not follow through. The database tracks `was_failed_breakout` for every entry to measure how often this occurs.

### Rule 3 — Scale out on the way up

| Target | Action |
|--------|--------|
| Up **2R** (2× your initial risk) | Sell 1/3 to 1/2 of position. Move stop to breakeven. |
| Up **3R** (3× your initial risk) | Sell another 1/4. Tighten the trail. |
| Stock closes below **10-day MA** | Sell the remainder — trend is breaking. |
| Stock closes below **20-day MA** | Exit if still holding during an extended trend. |

R = entry price − stop price. Example: bought at $50, stop at $47 → R = $3. 2R target = $56, 3R target = $59.

### Rule 4 — Earnings

Exit before earnings unless you have a **30%+ cushion** above your entry. Earnings introduce binary risk that invalidates the technical setup entirely.

### Rule 5 — Time stop (informal)

If a watchlist stock has been sitting within 8% of its pivot for **5+ days without breaking out**, the setup is stalling. Consider dropping it and rotating to fresher setups. The backtest showed stocks 6–8% from pivot only broke out 15% of the time within 5 days.

### Why holding matters

The backtest return profile accelerates sharply over time — selling within 5 days captures almost none of the actual edge:

| Interval | Avg return (A+/A/B) | Win rate | Capture ratio |
|----------|---------------------|----------|---------------|
| 1 day | +0.07% | 52% | 17% of peak |
| 5 days | +0.45% | 52% | 22% of peak |
| 10 days | +0.77% | **49%** — dips below 50% | 27% of peak |
| 20 days | +4.29% | **60%** | 49% of peak |
| Peak max | +10.80% | 91% | 100% |

The 10-day MA trail keeps you in winners long enough to capture the full move while cutting losers quickly.

---

### Backtest findings — what the data says about exit timing

**You are capturing less than half the move.** The average setup reaches a peak of +10.8% within the 20-day window but closes at only +4.3% by day 20 — a **6.5% average give-back** from peak to close. A trailing stop anchored to the 10-day MA should theoretically capture significantly more.

**Do not cut losers at day 5.** 48% of A+/A/B positions are negative at day 5. Of those, 47% recover to positive by day 20, averaging +8.1%. Cutting at day 5 when red would eliminate nearly half of eventual winners. The failed breakout rule (close below pivot within 3 days) is the correct early exit signal — not P&L being negative at day 5.

**Day 10 is the worst time to check P&L.** Win rate falls from 52% at day 5 to 49% at day 10 before recovering to 60% at day 20. Positions that look like losers at day 10 frequently recover. Do not exit based solely on being down at the 10-day mark.

#### Give-back by pattern

| Pattern | Avg 20d | Peak gain | Give-back | Win 20d |
|---------|---------|-----------|-----------|---------|
| FlatBase | +11.5% | +22.5% | **-11.0%** | 77% |
| Pennant | +8.2% | +15.0% | -6.8% | 66% |
| VCP | +7.4% | +12.4% | **-5.0%** | 65% |
| HTF | +2.3% | +8.9% | -6.5% | 57% |

FlatBase setups reach the biggest peaks (+22.5% avg max) but give back the most. They likely need holding beyond 20 days — a 30–40 day window would capture more of the move. VCP has the tightest give-back (5%), meaning those positions trend most smoothly after the breakout and respond well to a 10-day MA trail.

HTF has the worst avg 20d return (+2.3%) but accounts for 47% of all big winners (max gain > 20%). HTF is a high-variance, bimodal pattern: most stall, but a meaningful minority run hard. Benefit most from sizing down while letting the rare winner run long.

#### Three adjustments from the data

1. **FlatBase: use the 20-day MA trail instead of the 10-day MA.** FlatBase moves in longer waves and the 10-day MA will shake you out too early.
2. **Never exit based on day-10 P&L alone.** If no technical level has been violated (pivot intact, above MAs), hold.
3. **HTF: take partial profits at 1.5R, not 2R.** HTF setups have high give-back and don't trend as smoothly — locking gains earlier reduces the risk of the common reversal pattern.

---

## The Runners List

Runners are stocks that pass Stage 1 + Stage 2 (strong momentum) but have not yet consolidated. They are **not a buy signal.**

**What to do with runners:**
- Glance at the list each morning for context — these are the market's strongest names
- Do not chase them. There is no defined pivot or stop.
- Wait for them to appear on the watchlist. The scanner promotes them automatically when a base forms (average: 6 days)
- The breakout scanner also watches runners intraday for same-day base → breakout transitions. If one sets up and breaks out the same day, you will get a Telegram alert automatically.

**The value of the runners list:** if STX has been a runner for two weeks and then appears on the watchlist one morning, you go in with much higher conviction than a stock you have never tracked.

---

## Querying Your History

Connect to the `python` database on `ec2-35-172-202-150.compute-1.amazonaws.com`.

### Breakouts that fired
```sql
SELECT scan_date, ticker, breakout_price, pivot_price, volume_ratio,
       pattern_type, pattern_grade, stop_price, suggested_rr_ratio,
       sp500_above_50d_ma
FROM   breakout_entries
ORDER  BY scan_date DESC, created_at DESC;
```

### How your watchlist setups performed
```sql
SELECT e.scan_date, e.ticker, e.pattern_grade, e.pattern_type,
       e.pivot_price, e.price_at_scan,
       p.pct_change_5d, p.pct_change_10d, p.pct_change_20d,
       p.max_gain_pct, p.did_break_out
FROM   watchlist_entries e
JOIN   watchlist_performance p ON e.id = p.watchlist_id
WHERE  p.pct_change_5d IS NOT NULL
ORDER  BY p.pct_change_20d DESC;
```

### Win rate by grade (live data)
```sql
SELECT e.pattern_grade,
       COUNT(*)                                                        AS n,
       AVG(p.pct_change_20d)                                          AS avg_20d,
       SUM(CASE WHEN p.pct_change_5d > 0 THEN 1 ELSE 0 END) * 100.0
           / COUNT(*)                                                  AS win_rate_pct,
       SUM(CASE WHEN p.did_break_out = 1 THEN 1 ELSE 0 END) * 100.0
           / COUNT(*)                                                  AS breakout_rate_pct
FROM   watchlist_entries e
JOIN   watchlist_performance p ON e.id = p.watchlist_id
WHERE  p.pct_change_5d IS NOT NULL
GROUP  BY e.pattern_grade
ORDER  BY e.pattern_grade;
```

---

## Key Numbers to Remember

| Parameter | Value |
|-----------|-------|
| Max risk per trade | 0.5% of account |
| Max position size | 20% of account |
| Stop placement | Base low × 0.995 |
| Minimum R/R target | 2:1 |
| Volume required (breakout) | Last 30-min candle ≥ 3× avg 30-min volume |
| Watchlist trigger proximity | Within 8% of pivot |
| Market filter | Prefer S&P 500 above 50-day MA |

---

## What the Backtest Showed (1 Year, S&P 500, May 2025 – Apr 2026)

- **2,353 qualifying setups** across 122 unique tickers
- **A+ grade:** +12.4% avg 20d, 79% win rate — act on every alert (only ~14/year)
- **HTF/A+:** the single best grade-pattern combo in the dataset
- **HTF/B:** -0.40% avg 5d, 36% BO rate — now excluded from alerts by default
- **FlatBase (A/A+):** +11.5% avg 20d, 73% BO rate — rare but exceptional
- **Pennant (A/A+):** +8.2% avg 20d, 69% win rate — most reliable at 5d
- **VCP:** lower BO rate (35%) but +6.2% avg 20d — slow to develop, not a quick trade
- **Q1 2026 (choppy tape, S&P below 50d MA):** avg 20d only +0.22% — market regime dominates
- **Best recurring names:** STX, MU, CIEN, TER, WDC, GEV (+15–25% avg 20d across many appearances)
- **Proximity matters:** within 2% of pivot → 67% BO rate; 6–8% away → only 15% BO rate

Full analysis: `docs/performance-analysis.md`

---

*Based on: Qullamaggie momentum breakout methodology*
*Backtest: May 2025 – Apr 2026, S&P 500 universe, 1-year window*
*Updated: 2026-05-16 (HTF/B excluded; grade filter added; backtest findings incorporated)*
*See also: `docs/Rules-Reference.MD`, `docs/watchlist-plan.md`, `docs/breakout-scanner-plan.md`*
