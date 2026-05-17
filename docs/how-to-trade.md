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

| Trigger | Action |
|---------|--------|
| Stop price hit (base low × 0.995) | Exit full position immediately |
| Price closes back below pivot within 3 days | Failed breakout — exit |
| Up 2× your risk (2R) | Sell 1/3 to 1/2, move stop to breakeven |
| Up 3× your risk (3R) | Sell another 1/4, tighten trail |
| Stock closes below 10-day MA | Trail stop — sell remaining position |
| Earnings within 3 days | Exit before earnings unless ≥ 30% cushion |

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
