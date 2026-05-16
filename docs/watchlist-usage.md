# Daily Watchlist — Usage Guide

> How to run, read, tune, and act on the daily watchlist scanner.

---

## What the Watchlist Is

The watchlist is a list of stocks that are:
- In a **strong uptrend** (momentum: 1M ≥ 5%, 3M ≥ 15%, 6M ≥ 30%)
- **Consolidating tightly** near their highs (base depth ≤ 20%)
- **Volume drying up** during the consolidation (quality signal — improves grade)
- **Close to breaking out** (within 8% of the pivot price)

These are stocks to **watch today**. They haven't broken out yet — they're set up and coiling.
The breakout scanner monitors these throughout the day and alerts when one triggers.

---

## Running the Scanner

### Automatic (Cron — Recommended)
The scanner runs automatically at **8:00 AM EST every weekday**.
No action needed once cron is installed.

After each run, results are automatically sent to **Telegram**. You'll receive a formatted summary with every setup found, grades, pivots, and stage funnel counts.

Check the log after it runs:
```bash
tail -50 /home/ubuntu/.openclaw/workspace/stocks-repo/scan/logs/watchlist.log
```

### Manual Run
```bash
cd /home/ubuntu/.openclaw/workspace/stocks-repo/scan

# Full scan — writes to database
python3 watchlist_scanner.py

# Full scan — print only, no DB write
python3 watchlist_scanner.py --dry-run

# Scan a specific ticker
python3 watchlist_scanner.py --ticker NVDA
python3 watchlist_scanner.py --ticker NVDA --dry-run
```

---

## Reading the Output

```
=================================================================
  DAILY WATCHLIST SCAN — 2026-04-28
  Universe: 516 tickers | Dry run: False
=================================================================

  SCAN SUMMARY
  ────────────────────────────────────────
  Total tickers scanned     : 2847
  Data fetched              : 2610   ← tickers with sufficient history
  Passed Stage 1 filter     : 540    ← meet price/volume/ADR minimums
  Passed Stage 2 (momentum) : 98     ← up ≥5%/15%/30% over 1M/3M/6M
  + also had prior move (2b): 41     ← bonus grading only
  Passed Stage 3 (base)     : 22     ← formed a tight base after move
  Had vol contraction (4)   : 11     ← bonus grading only
  On watchlist today        : 7      ← within 8% of pivot — watch these

  ─────────────────────────────────────────────────────────────────────────────────────────
  Ticker   Grade  Price     Pivot    %Away  Pattern      Prior Move   Top Reason
  ─────────────────────────────────────────────────────────────────────────────────────────
  CELH     A+     $ 48.20  $ 49.00   1.6%  VCP          +67%/22d     Prior move: +67.3%...
  AXON     A      $312.50  $320.00   2.3%  FlatBase     +41%/30d     Prior move: +41.1%...
  ─────────────────────────────────────────────────────────────────────────────────────────

  Written to DB: 2/2 entries
```

### Column Definitions

| Column | Meaning |
|--------|---------|
| **Ticker** | Stock symbol |
| **Grade** | Setup quality: A+ (best) → A → B → C |
| **Price** | Last closing price |
| **Pivot** | Top of the consolidation base — the breakout level |
| **%Away** | How far current price is below the pivot (lower = closer to triggering) |
| **Pattern** | VCP, HTF (High-Tight Flag), FlatBase, or Pennant |
| **Prior Move** | The explosive move that qualified the stock (% gain / days taken) |
| **Top Reason** | First qualifying reason string from the database |

### Setup Grades Explained

| Grade | What It Means | Action |
|-------|---------------|--------|
| **A+** | 60%+ prior move, very tight base, volume nearly zero, strong MA alignment | High priority — watch closely |
| **A** | 40%+ prior move, good volume contraction, clean base | Watch |
| **B** | 30%+ prior move, adequate setup | Watch with lower conviction |
| **C** | Borderline — meets minimum thresholds only | Optional — lower priority |

---

## How to Use the Watchlist

### Step 1 — Review at 8 AM
Check the log or run manually with `--dry-run` to see today's list.

### Step 2 — Set Price Alerts
For each watchlist stock, set a price alert in your broker at the **pivot price**.
The pivot is the exact price where a breakout triggers.

> The breakout scanner does this automatically — but setting broker alerts
> gives you a second line of notification with no dependency on the server.

### Step 3 — Watch Volume During the Day
A valid breakout requires the **most recent 30-minute candle to show ≥ 3× the average 30-min volume** (the scanner measures intensity, not cumulative daily volume — which can't be known early in the session).
Monitor volume during and after the pivot cross.
If price crosses the pivot but the 30-min bars are thin — wait. It may be a false break.

### Step 4 — Entry Rules
**Intraday entry (aggressive):**
- Price breaks above pivot
- Volume is expanding (≥ 1.5× average by midday)
- Enter near the breakout candle
- Stop: just below the base low

**End-of-day entry (conservative):**
- Confirm the stock closes above the pivot
- Volume confirms on the daily candle
- Enter on next day's open

### Step 5 — Position Sizing
```
Dollar Risk   = Account Size × 0.5%
Stop Distance = Entry Price − Stop Price
Share Count   = Dollar Risk ÷ Stop Distance
Max Position  = Account Size × 20%  (cap per trade)
```

---

## Querying Watchlist History

Connect to the `python` database on `ec2-35-172-202-150.compute-1.amazonaws.com` and use these queries.

### Today's Watchlist
```sql
SELECT ticker, pattern_grade, price_at_scan, pivot_price, pct_from_pivot,
       pattern_type, prior_move_pct, prior_move_days,
       base_depth_pct, volume_contraction_ratio
FROM   watchlist_entries
WHERE  scan_date = CAST(GETDATE() AS DATE)
ORDER  BY pattern_grade, pct_from_pivot;
```

### This Week's Watchlist
```sql
SELECT scan_date, ticker, pattern_grade, price_at_scan, pivot_price,
       pattern_type, prior_move_pct
FROM   watchlist_entries
WHERE  scan_date >= DATEADD(day, -7, CAST(GETDATE() AS DATE))
ORDER  BY scan_date DESC, pattern_grade;
```

### Best Performing Setups (by 10-day return)
```sql
SELECT e.ticker, e.scan_date, e.pattern_type, e.pattern_grade,
       e.prior_move_pct, e.base_depth_pct, e.volume_contraction_ratio,
       p.pct_change_10d, p.max_gain_pct
FROM   watchlist_entries e
JOIN   watchlist_performance p ON e.id = p.watchlist_id
WHERE  p.pct_change_10d IS NOT NULL
ORDER  BY p.pct_change_10d DESC;
```

### Win Rate by Pattern Type
```sql
SELECT e.pattern_type,
       COUNT(*) AS total,
       AVG(p.pct_change_10d) AS avg_10d_return,
       SUM(CASE WHEN p.pct_change_10d > 5 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS win_rate_pct
FROM   watchlist_entries e
JOIN   watchlist_performance p ON e.id = p.watchlist_id
WHERE  p.pct_change_10d IS NOT NULL
GROUP  BY e.pattern_type
ORDER  BY avg_10d_return DESC;
```

### Stocks That Eventually Broke Out vs. Didn't
```sql
SELECT did_break_out,
       COUNT(*) AS count,
       AVG(pct_change_5d) AS avg_5d_return
FROM   watchlist_performance
WHERE  did_break_out IS NOT NULL
GROUP  BY did_break_out;
```

---

## Tuning the Criteria

All thresholds are in `scan/config.py`. Change values there and the next run uses them immediately.
You can also add a `.env` file in `scan/` to override without editing code.

### Tighten to Improve Quality (fewer but stronger setups)
```env
MIN_MOMENTUM_3M_PCT=25      # was 15 — require stronger 3M momentum
MIN_MOMENTUM_6M_PCT=40      # was 30 — require stronger 6M momentum
MAX_BASE_DEPTH_PCT=10       # was 20 — require tighter base
MAX_BASE_VOL_RATIO=0.60     # was 0.85 — require more volume contraction
MIN_CONSEC_LOW_VOL_DAYS=5   # was 3 — require longer vol dry-up
```

### Loosen to Increase Universe (more setups, lower average quality)
```env
MIN_MOMENTUM_1M_PCT=2       # was 5
MIN_MOMENTUM_3M_PCT=10      # was 15
MAX_BASE_DEPTH_PCT=25       # was 20
MAX_DIST_FROM_PIVOT_PCT=10  # was 8 — catch stocks further from pivot
```

### After 30+ Days of Data: Run Analysis
Use the SQL queries above to see which thresholds produced the best results,
then adjust `config.py` accordingly.

---

## Telegram Notifications

Both scanners send results to Telegram automatically.

### Watchlist Scanner
After every full scan, you receive a summary like:

```
📋 Watchlist — 2026-04-28  (3 setups)

🔥 CELH  [A+]  VCP
   Price $48.20 → Pivot $49.00  (1.6% away)
   Prior move: +67% in 22d

⭐ AXON  [A]  FlatBase
   Price $312.50 → Pivot $320.00  (2.3% away)
   Prior move: +41% in 30d

Scanned 516 tickers — S1:181  S2:52  S3:8  S4:3
```

### Breakout Scanner
Each confirmed breakout triggers an immediate alert:

```
🚨 BREAKOUT — CELH  🔥 [A+]

   Price: $49.15  (pivot $49.00)
   Volume: 2.4× avg
   Pattern: VCP  |  Prior move: +67% / 22d
   Stop: $44.20  |  R/R: 3.2:1
```

### Configuration
Notifications use the OpenClaw Telegram bot by default. To override:
```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

Single-ticker scans (`--ticker AAPL`) and `--dry-run` do **not** send Telegram notifications.

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| Watchlist is empty every day | Market may be in correction — fewer setups in downtrends. Check `Stage 2 (momentum)` count — if low, most stocks underperforming on 3M/6M timeframes. |
| Scanner found 0 tickers | Run `--dry-run --ticker NVDA` to confirm data is fetching. |
| "No module named X" error | Run `pip3 install --break-system-packages -r requirements.txt` |
| Database write errors | Check `ai-agent` can reach the server: `python3 -c "from shared.db_writer import test_connection; print(test_connection())"` |
| Ticker universe is tiny (fallback list) | `get_ticker_universe()` falls back to hardcoded ~150 tickers if yahoo_fin fails. Check logs for `Falling back to hardcoded starter universe`. |
| "No module named yahoo_fin" | `pip3 install --break-system-packages yahoo-fin` |
| Tickers showing as delisted | yfinance sometimes lags on symbol changes. These are caught and skipped automatically. |

---

## Log Location

```
scan/logs/watchlist.log      ← cron output (auto-rotated by cron redirect)
```

Check the last run:
```bash
tail -60 /home/ubuntu/.openclaw/workspace/stocks-repo/scan/logs/watchlist.log
```

---

*Last updated: 2026-05-16 (R24 30-min intensity; runner gates; ADR breakout path)*
*See also: `breakout-scanner-usage.md`, `watchlist-plan.md`*
