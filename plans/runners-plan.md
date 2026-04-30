# Runners Watchlist — Plan

> Capture strong momentum stocks that pass Stage 1 + Stage 2 but have **not yet**
> formed a consolidation base. These are "runners" — stocks in active markup that
> will eventually pause and set up. The goal is to have them on your radar **before**
> the base forms, so you're ready when the setup appears.

---

## Problem

The daily watchlist scanner only surfaces stocks that are *already* consolidating near
a pivot. Stocks like SNDK and WDC that are in strong uptrends but haven't paused yet
are silently dropped at Stage 3 — and you miss them entirely until they eventually
set up (which could be days or weeks later).

**Missed opportunity flow (current):**
```
SNDK passes S1 ✅  passes S2 ✅  fails S3 ❌  → silently dropped
```

**With runners list:**
```
SNDK passes S1 ✅  passes S2 ✅  fails S3 ❌  → captured as runner 🏃
→ Next week: SNDK starts base  → main scanner picks it up automatically
```

---

## Runner Criteria

A stock makes the Runners list if it passes **Stage 1 + Stage 2** AND:

| Check | Criterion | Rationale |
|-------|-----------|-----------|
| **Price > MA20** | Current price above 20-day MA | Still in uptrend, not breaking down |
| **MA20 > MA50** | 20-day MA above 50-day MA | Trend structure intact |
| **Near recent high** | Within 15% of 20-day high | Still trending up, not pulling back hard |
| **No base detected** | Stage 3 fails — stock has NOT consolidated | Distinguishes runners from setups |

Stocks that pass Stage 3 are NOT runners — they go to the main watchlist instead.

---

## Stage Flow (Runners Extension)

```
Stage 1  check_universe_filter()     → pass required
Stage 2  check_momentum_trend()      → pass required
Stage 3  find_consolidation_base()   → FAIL (no base yet)
Runner   check_runner_state()        → price > MA20 > MA50, near recent high
         → add to runner_entries table
```

The main watchlist flow is unchanged. Runners are a parallel output from the same scan.

---

## What Happens Next

Runners require **no manual follow-up**. When a runner eventually forms a base:
- The existing `find_consolidation_base()` will detect it
- The stock naturally flows into `watchlist_entries` on that future scan day
- You'll receive the normal watchlist Telegram alert at that point

The runners list is purely informational — it tells you *"watch these, they're setting up
to set up"*.

---

## Output

### Console (appended to existing scan summary)

```
  RUNNERS (Stage 1+2 ✅ — no base yet, still marking up)
  ─────────────────────────────────────────────────────────────────────────
  Ticker    Price     1M      3M      6M     52wH%   Prior Move
  ─────────────────────────────────────────────────────────────────────────
  SNDK    $1064.21  +31.2%  +95.3%  +180%   -2.1%  +220%/45d
  WDC      $412.76  +18.4%  +67.1%  +140%   -4.3%  +165%/52d
  ...
  ─────────────────────────────────────────────────────────────────────────
  12 runners identified — monitor for base formation
```

### Telegram

Runners are appended to the daily Telegram notification as a compact section —
less prominent than the main watchlist, since no action is needed today.

```
🏃 Runners (no base yet) — 12 stocks
  SNDK $1064 | 1M+31% 3M+95% | -2% from 52wH
  WDC  $413  | 1M+18% 3M+67% | -4% from 52wH
  ...
```

---

## Database Table: `runner_entries`

One row per ticker per scan day. Deduplicated on `(scan_date, ticker)`.

```sql
CREATE TABLE runner_entries (
    id                  INT IDENTITY PRIMARY KEY,
    scan_date           DATE NOT NULL,
    ticker              VARCHAR(10) NOT NULL,
    price_at_scan       DECIMAL(10,4),
    pct_1m              DECIMAL(6,2),
    pct_3m              DECIMAL(6,2),
    pct_6m              DECIMAL(6,2),
    pct_from_52w_high   DECIMAL(6,2),
    pct_from_20d_high   DECIMAL(6,2),
    prior_move_pct      DECIMAL(6,2),
    prior_move_days     INT,
    adr_pct             DECIMAL(5,2),
    avg_daily_volume    INT,
    created_at          DATETIME DEFAULT GETDATE()
);
```

### Useful Queries

```sql
-- Today's runners
SELECT ticker, price_at_scan, pct_1m, pct_3m, pct_6m, pct_from_52w_high
FROM   runner_entries
WHERE  scan_date = CAST(GETDATE() AS DATE)
ORDER  BY pct_3m DESC;

-- How long has a stock been a runner before setting up?
SELECT r.ticker,
       MIN(r.scan_date) AS first_runner_date,
       MIN(w.scan_date) AS first_watchlist_date,
       DATEDIFF(day, MIN(r.scan_date), MIN(w.scan_date)) AS days_to_base
FROM   runner_entries r
JOIN   watchlist_entries w ON r.ticker = w.ticker
WHERE  w.scan_date > r.scan_date
GROUP  BY r.ticker
ORDER  BY days_to_base;
```

---

## Implementation

### Files Changed

| File | Change |
|------|--------|
| `scan/shared/criteria.py` | Add `check_runner_state()` |
| `scan/watchlist_scanner.py` | Collect runners in `run_scan()`, print + write to DB |
| `scan/shared/db_writer.py` | Add `insert_runner_entry()` |
| `scan/shared/telegram_notify.py` | Add `send_runners_summary()` |
| `scan/db_setup.sql` | Add `runner_entries` table (idempotent) |

### Key Design Decisions

- **Same scan, no extra downloads** — runners are identified during the existing bulk fetch.
  Zero additional network cost.
- **Not a gate, not graded** — runners have no grade. They're informational only.
- **Natural promotion** — no code needed to "promote" a runner to watchlist. The existing
  Stage 3 check handles it automatically once the base forms.
- **`check_runner_state()` returns None** if the stock is pulling back hard (>15% below
  20d high) or has broken its MA structure — avoiding noise from failing stocks.

---

*Created: 2026-04-30*
*See also: `plans/watchlist-plan.md`, `scan/shared/criteria.py`*
