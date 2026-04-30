# Stock Scanner — Quick Start Guide

Automated Qullamaggie-style watchlist and breakout detection system.

## What It Does

| Script | When | What |
|--------|------|------|
| `watchlist_scanner.py` | 8:00 AM EST daily | Scans full market for stocks setting up near a pivot |
| `breakout_scanner.py`  | Every 30 min, 9:30 AM–4 PM EST | Checks today's watchlist stocks for live breakouts |
| `performance_tracker.py` | 4:30 PM EST daily | Records 1d/5d/10d/20d/60d price outcomes |

---

## Prerequisites

- Python 3.9+
- **ODBC Driver 17 for SQL Server** — [Download here](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)

Install on Ubuntu/Debian:
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17
```

---

## Installation

**Step 1 — Install Python packages:**
```bash
cd scan/
pip install -r requirements.txt
```

**Step 2 — Create database tables:**

Connect to SQL Server and run `db_setup.sql`:
```bash
# Via sqlcmd
sqlcmd -S ec2-35-172-202-150.compute-1.amazonaws.com -U ai-agent -P 'Welcome100!' -d python -i db_setup.sql

# Or paste into SQL Server Management Studio / Azure Data Studio
```

**Step 3 — Install cron jobs:**
```bash
chmod +x cron_setup.sh
./cron_setup.sh
```

---

## Configuration

All settings are in `config.py`. Override any value by creating a `.env` file in `scan/`:

```env
# .env — optional overrides (do not commit to git)
MIN_PRIOR_MOVE_PCT=40       # raise to tighten criteria
MAX_BASE_DEPTH_PCT=10       # tighter bases only
MIN_BREAKOUT_VOL_RATIO=2.0  # require stronger volume confirmation
```

---

## Manual Testing

Test each script without writing to the database:

```bash
# Scan full universe (dry run — no DB writes)
python watchlist_scanner.py --dry-run

# Scan a single ticker
python watchlist_scanner.py --ticker NVDA --dry-run

# Run breakout scanner (ignores market hours check)
python breakout_scanner.py --force --dry-run

# Run performance tracker
python performance_tracker.py --dry-run
```

---

## File Structure

```
scan/
├── README.md                  ← This file
├── requirements.txt           ← pip dependencies
├── cron_setup.sh              ← Installs all cron jobs
├── db_setup.sql               ← Creates all 4 SQL Server tables
├── config.py                  ← All thresholds and DB settings
│
├── watchlist_scanner.py       ← 8 AM daily market scan
├── breakout_scanner.py        ← 30-min intraday breakout checker
├── performance_tracker.py     ← End-of-day price outcome recorder
│
└── shared/
    ├── __init__.py
    ├── data_fetcher.py        ← yfinance data + indicator computation
    ├── criteria.py            ← Qullamaggie Stage 1–5 logic
    └── db_writer.py           ← All SQL Server read/write functions
```

---

## Understanding the Output

### Watchlist Scanner (`watchlist_scanner.py`)

```
=================================================================
  DAILY WATCHLIST SCAN — 2026-04-28
  Universe: 2847 tickers | Dry run: False
=================================================================

  SCAN SUMMARY
  ────────────────────────────────────────
  Total tickers scanned     : 2847
  Data fetched              : 2610   ← tickers with sufficient history
  Passed Stage 1 filter     : 540    ← price/volume/ADR filter
  Passed Stage 2 (momentum) : 98     ← up ≥5%/15%/30% over 1M/3M/6M
  + also had prior move (2b): 41     ← bonus grading only
  Passed Stage 3 (base)     : 22     ← tight consolidation base
  Had vol contraction (4)   : 11     ← bonus grading only
  On watchlist today        : 7      ← within 8% of pivot

  ───────────────────────────────────────────────────────────────────────────────────────────────
  Ticker   Grade  Price     Pivot    %Away  Pattern      Prior Move   Top Reason
  ───────────────────────────────────────────────────────────────────────────────────────────────
  CELH     A+     $ 48.20  $ 49.00   1.6%  VCP          +67%/22d     Prior move: +67.3% in 22 days
  NVDA     A      $126.50  $130.00   2.7%  FlatBase     +41%/30d     Prior move: +41.1% in 30 days
  ...
```

### Breakout Scanner (`breakout_scanner.py`)

```
=================================================================
  BREAKOUT SCAN — 2026-04-28 10:30 EST
=================================================================
  Watchlist stocks to check: 6

  ✅ BREAKOUT: CELH     $49.40 | Vol: 3.1x | +0.8% above pivot | VCP/A+

  ─────────────────────────────────────────────────────────
  Stocks checked       : 6
  New breakouts        : 1
  Already alerted today: 0
  No trigger yet       : NVDA, AAPL, TSLA, META, SMCI
```

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `watchlist_entries` | One row per stock per day on the watchlist |
| `watchlist_performance` | Price outcomes 1d/5d/10d/20d/60d after watchlist date |
| `breakout_entries` | One row per confirmed breakout |
| `breakout_performance` | Price outcomes + stop hits + R multiples after breakout |

---

## Useful Analysis Queries

```sql
-- Which patterns produce the best 10-day returns?
SELECT pattern_type,
       COUNT(*) AS total,
       AVG(p.pct_change_10d) AS avg_10d_return
FROM watchlist_entries e
JOIN watchlist_performance p ON e.id = p.watchlist_id
GROUP BY pattern_type
ORDER BY avg_10d_return DESC;

-- Breakout win rate by volume ratio
SELECT
    CASE WHEN volume_ratio >= 3.0 THEN '3x+'
         WHEN volume_ratio >= 2.0 THEN '2x-3x'
         ELSE '1.5x-2x' END AS vol_tier,
    COUNT(*) AS count,
    AVG(p.pct_change_10d) AS avg_10d
FROM breakout_entries e
JOIN breakout_performance p ON e.id = p.breakout_id
GROUP BY
    CASE WHEN volume_ratio >= 3.0 THEN '3x+'
         WHEN volume_ratio >= 2.0 THEN '2x-3x'
         ELSE '1.5x-2x' END
ORDER BY avg_10d DESC;
```

---

## Methodology

Based on Kristjan Kullamägi (Qullamaggie) momentum breakout methodology:
- **Stage 1** — Universe filter: price ≥ $5, avg vol ≥ 300k, ADR ≥ 3%
- **Stage 2** — Momentum trend: 1M ≥ 5%, 3M ≥ 15%, 6M ≥ 30% — *never ages out*
- **Stage 2b** — Prior explosive move (≥25% in 60d) — *bonus grading only, not a gate*
- **Stage 3** — Tight consolidation base (≤20% depth, 5–40 days)
- **Stage 4** — Volume contraction — *bonus grading only, not a gate*
- **Stage 5** — Breakout confirmation (price + volume + candle strength)

Full methodology: `qullamaggie/breakouts/Rules.MD`
