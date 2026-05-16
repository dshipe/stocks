# Breakout Scanner — Usage Guide

> How to run, read, respond to, and tune the intraday breakout scanner.

---

## What the Breakout Scanner Does

The breakout scanner runs **every 30 minutes during market hours** and checks two lists:
1. **Today's watchlist** (`watchlist_entries`) — stocks from the 8 AM scan already in a base near the pivot
2. **Today's runners** (`runner_entries`) — Stage 1+2 passes in active markup (no base yet), checked for same-day base→breakout transitions via `check_runner_breakout()`

A breakout is confirmed when ALL of the following are true (base-pivot path):
1. **Price > pivot** — current price has crossed above the base high
2. **Last 30-min candle ≥ 3× avg 30-min volume** — institutional buying intensity detected intraday
3. **Candle is strong** — current price is within 5% of the session high (not reversing)

A parallel **ADR breakout path** also runs for every stock (watchlist + runners):
- Move from prev close ≥ 0.5× ADR% (scales with the stock's own volatility)
- Last 30-min candle ≥ 2× avg 30-min volume
- Price within 5% of session high
Base-pivot alerts are labelled `[WL]`/`[RN]`; ADR alerts use `[WL-ADR]`/`[RN-ADR]`.

When a breakout fires, it is:
- Written to `breakout_entries` in SQL Server (once per ticker per day)
- Logged in `scan/logs/breakout.log`
- Sent via Telegram (always) and SMS via Twilio (if configured)

---

## Schedule

| Time (EST) | What Happens |
|------------|--------------|
| 8:00 AM | Watchlist scanner runs — loads today's candidates into SQL Server |
| 9:30 AM | Market opens — breakout scanner starts |
| Every :00 and :30 | Breakout scanner checks all watchlist stocks |
| 4:00 PM | Final scan at market close |
| 4:30 PM | Performance tracker runs |

The scanner exits immediately if run outside market hours (no wasted cycles).

---

## Running the Scanner

### Automatic (Cron — Recommended)
Runs automatically every 30 minutes during market hours. No action needed.

Check the log:
```bash
tail -50 /home/ubuntu/.openclaw/workspace/stocks-repo/scan/logs/breakout.log
```

### Manual Run
```bash
cd /home/ubuntu/.openclaw/workspace/stocks-repo/scan

# Normal run (respects market hours check)
python3 breakout_scanner.py

# Force run even outside market hours (for testing)
python3 breakout_scanner.py --force

# Dry run — check for breakouts but don't write to DB
python3 breakout_scanner.py --force --dry-run
```

> **Note:** The scanner will print `Market is closed. Exiting.` if run outside
> 9:30 AM–4:00 PM EST on a weekday. Use `--force` to override this.

---

## Reading the Output

### Normal Run — No Breakouts
```
=================================================================
  BREAKOUT SCAN — 2026-04-28 10:30 EST
=================================================================
  Watchlist stocks to check: 5

  ─────────────────────────────────────────────────────────────
  Stocks checked       : 5
  New breakouts        : 0
  Already alerted today: 0
  No trigger yet       : CELH, AXON, NVDA, SMCI, CRWD
```

### Run With a Breakout Detected
```
=================================================================
  BREAKOUT SCAN — 2026-04-28 11:00 EST
=================================================================
  Watchlist stocks to check: 5

  ✅ BREAKOUT: CELH     $49.80 | Vol: 3.1x | +1.6% above pivot | VCP/A+

  ─────────────────────────────────────────────────────────────
  Stocks checked       : 5
  New breakouts        : 1
  Already alerted today: 0
  No trigger yet       : AXON, NVDA, SMCI, CRWD
```

### Later Run (After First Alert)
```
=================================================================
  BREAKOUT SCAN — 2026-04-28 11:30 EST
=================================================================
  Stocks checked       : 5
  New breakouts        : 0
  Already alerted today: 1
  No trigger yet       : AXON, NVDA, SMCI, CRWD
  Previously alerted   : CELH (11:00 AM)
```

### Column Definitions (Breakout Line)

| Field | Meaning |
|-------|---------|
| `$49.80` | Current price at time of detection |
| `Vol: 3.1x` | Last 30-min candle volume ÷ average 30-min volume (3.1× = 310% of avg 30-min bar) |
| `+1.6% above pivot` | How far price is above the base high (base-pivot path) or prev close (ADR path) |
| `VCP/A+` | Pattern type / setup grade (base-pivot) or `ADR_MOMENTUM / NxADR` (ADR path) |

---

## How to Act on a Breakout Alert

### Step 1 — Confirm Volume
Check the alert line: `Vol: X.Xx`. This is volume at time of detection.
- **< 1.5x** — technically below threshold; scanner should not have fired
- **1.5x – 2x** — valid but moderate; use end-of-day entry strategy
- **2x – 3x** — strong; intraday entry viable
- **3x+** — institutional conviction; highest quality breakout

If you're checking manually mid-day, confirm volume is still expanding (not fading).

### Step 2 — Check the Candle
Price should be near its session high. A breakout that immediately pulls back below
the pivot is a **failed breakout** — do not chase.

Look for:
- Price holding above the pivot after the initial cross
- Candle closing in the upper half of its range
- No large wicks to the downside on the breakout candle

### Step 3 — Decide Entry Style

**Intraday Entry (Aggressive)**
- Enter when price first crosses the pivot with volume ≥ 1.5× average
- Stop: just below the base low (or below the day's intraday low)
- Best for A+ and A grade setups with 2x+ volume

**End-of-Day Entry (Conservative)**
- Wait until 30–60 min before close
- Confirm price is still above pivot and volume is elevated on the daily candle
- Enter near the close
- Stop: below the base low

### Step 4 — Position Sizing
```
Dollar Risk   = Account Size × 0.5%
Stop Distance = Entry Price − Stop Price
Share Count   = Dollar Risk ÷ Stop Distance
Max Position  = Account Size × 20%
```
The `stop_price` for each breakout is stored in `breakout_entries` (base low × 0.995).

### Step 5 — Exit Rules
| Trigger | Action |
|---------|--------|
| Stop price hit | Exit full position |
| Price closes back below pivot within 3 days | Failed breakout — exit |
| 2R gain reached (price up 2× your risk) | Sell 1/3 to 1/2 position, move stop to breakeven |
| 3R gain reached | Sell another 1/4, tighten trail |
| Stock closes below 10-day MA | Trail exit — sell remaining |
| Earnings within 3 days | Exit before earnings |

---

## Querying Breakout History

Connect to `ec2-35-172-202-150.compute-1.amazonaws.com`, database `python`.

### Today's Breakouts
```sql
SELECT ticker, breakout_price, pivot_price, volume_ratio,
       pattern_type, pattern_grade, stop_price, suggested_rr_ratio,
       qualification_reasons
FROM   breakout_entries
WHERE  scan_date = CAST(GETDATE() AS DATE)
ORDER  BY created_at;
```

### All Breakouts — Last 30 Days
```sql
SELECT scan_date, ticker, breakout_price, pivot_price,
       volume_ratio, pattern_type, pattern_grade,
       was_on_watchlist, stop_price
FROM   breakout_entries
WHERE  scan_date >= DATEADD(day, -30, CAST(GETDATE() AS DATE))
ORDER  BY scan_date DESC, created_at DESC;
```

### Breakout Outcomes — Which Worked?
```sql
SELECT e.ticker, e.scan_date, e.breakout_price, e.pattern_type, e.pattern_grade,
       e.volume_ratio, e.stop_price,
       p.pct_change_5d, p.pct_change_10d, p.max_gain_pct, p.max_r_multiple,
       p.hit_stop, p.was_failed_breakout
FROM   breakout_entries e
JOIN   breakout_performance p ON e.id = p.breakout_id
WHERE  p.pct_change_10d IS NOT NULL
ORDER  BY e.scan_date DESC;
```

### Win Rate and Average R by Volume Tier
```sql
SELECT
    CASE
        WHEN e.volume_ratio >= 3.0 THEN '3x+ (very strong)'
        WHEN e.volume_ratio >= 2.0 THEN '2x-3x (strong)'
        WHEN e.volume_ratio >= 1.5 THEN '1.5x-2x (valid)'
        ELSE 'Below 1.5x'
    END AS volume_tier,
    COUNT(*) AS total,
    SUM(CASE WHEN p.hit_stop = 0 AND p.pct_change_10d > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS win_rate_pct,
    AVG(p.pct_change_10d) AS avg_10d_return,
    AVG(p.max_r_multiple) AS avg_max_r
FROM   breakout_entries e
JOIN   breakout_performance p ON e.id = p.breakout_id
WHERE  p.pct_change_10d IS NOT NULL
GROUP  BY
    CASE
        WHEN e.volume_ratio >= 3.0 THEN '3x+ (very strong)'
        WHEN e.volume_ratio >= 2.0 THEN '2x-3x (strong)'
        WHEN e.volume_ratio >= 1.5 THEN '1.5x-2x (valid)'
        ELSE 'Below 1.5x'
    END
ORDER  BY avg_10d_return DESC;
```

### Failed Breakout Rate by Market Condition
```sql
SELECT
    CASE WHEN e.sp500_above_50d_ma = 1 THEN 'S&P above 50d MA' ELSE 'S&P below 50d MA' END AS market_condition,
    COUNT(*) AS total,
    SUM(CASE WHEN p.was_failed_breakout = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct,
    AVG(p.pct_change_10d) AS avg_10d_return
FROM   breakout_entries e
JOIN   breakout_performance p ON e.id = p.breakout_id
WHERE  p.was_failed_breakout IS NOT NULL
GROUP  BY e.sp500_above_50d_ma
ORDER  BY failure_rate_pct;
```

### Watchlist Pre-Identification vs. Surprise Breakouts
```sql
SELECT
    CASE WHEN was_on_watchlist = 1 THEN 'Was on morning watchlist' ELSE 'Not on watchlist' END AS source,
    COUNT(*) AS total,
    AVG(p.pct_change_10d) AS avg_10d_return,
    AVG(p.max_r_multiple) AS avg_max_r
FROM   breakout_entries e
JOIN   breakout_performance p ON e.id = p.breakout_id
WHERE  p.pct_change_10d IS NOT NULL
GROUP  BY e.was_on_watchlist;
```

---

## Setting Up SMS Alerts (Optional)

The scanner can send a text message immediately when a breakout fires.

1. Create a [Twilio](https://twilio.com) account (free trial available)
2. Get your Account SID, Auth Token, and a Twilio phone number
3. Add to `scan/.env`:

```env
TWILIO_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_TOKEN=your_auth_token
TWILIO_FROM=+15551234567
NOTIFY_PHONE=+15559876543
```

SMS format:
```
BREAKOUT ALERT: CELH (VCP/A+)
Price: $49.80 | Pivot: $49.00
Vol: 3.1x avg | +1.6% above pivot
```

---

## Tuning the Breakout Criteria

After accumulating 30+ breakout records, use the SQL queries above to identify which
thresholds produce the best outcomes and adjust `scan/config.py` (or `scan/.env`):

### Require Stronger Volume (Higher Quality Signal)
```env
MIN_BREAKOUT_30MIN_VOL_RATIO=4.0   # was 3.0 — require stronger 30-min candle intensity (base-pivot path)
MIN_ADR_BREAKOUT_30MIN_VOL_RATIO=3.0  # was 2.0 — require stronger intensity for ADR path
MIN_ADR_BREAKOUT_MULT=1.0          # was 0.5 — require a full ADR move (not just half)
```

### Require Stronger Candle Close
```env
MAX_CLOSE_FROM_HIGH_PCT=3.0   # was 5.0 — candle must close within 3% of high
```

### Tighten the Underlying Setup
These are watchlist criteria (set at 8 AM) that flow through to breakout quality.
Current defaults are in `scan/config.py`; override via `scan/.env`:
```env
MIN_MOMENTUM_3M_PCT=25     # was 15 — require stronger 3M momentum
MIN_MOMENTUM_6M_PCT=40     # was 30 — require stronger 6M momentum
MAX_BASE_DEPTH_PCT=10      # was 20 — require tighter base
MAX_BASE_VOL_RATIO=0.60    # was 0.85 — require more volume contraction (grading bonus, not a gate)
```

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| `Market is closed. Exiting.` | Use `--force` flag to override, or check the `is_market_open()` timezone logic |
| `No watchlist for today` | Watchlist scanner hasn't run yet, or ran and found nothing. Check `scan/logs/watchlist.log` |
| Breakout fires but stock isn't moving | Volume may be front-loaded early in session; monitor if it sustains. Consider raising `MIN_BREAKOUT_VOL_RATIO` |
| Same stock alerting repeatedly | Dedup logic checks `breakout_already_logged_today()` — if seeing repeats, check DB write is succeeding |
| Scanner runs but produces no output | Check if watchlist table has today's entries: run the watchlist query above |
| SMS not sending | Verify Twilio credentials in `.env`; check `scan/logs/breakout.log` for `Notification failed` messages |

---

## Log Location

```
scan/logs/breakout.log       ← combined log for all 30-min runs
```

View the last few runs:
```bash
tail -100 /home/ubuntu/.openclaw/workspace/stocks-repo/scan/logs/breakout.log
```

---

*Last updated: 2026-05-16 (ADR breakout path added; R24 → 30-min intensity; runner gates; correct config keys)*
*See also: `watchlist-usage.md`, `breakout-scanner-plan.md`, `runners-plan.md`*
