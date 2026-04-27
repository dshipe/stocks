# Daily Watchlist Generator — Plan

> A Python-based system to scan the stock market every weekday at 8 AM EST, identify stocks
> meeting Qullamaggie-style watchlist criteria, and maintain a structured history for
> performance tracking and criteria refinement.

---

## Overview

The goal is a fully automated, scheduled Python script that:
1. Pulls daily market data at 8 AM EST (pre-market, before the open)
2. Screens the full market universe against Qullamaggie watchlist criteria
3. Outputs the day's watchlist with exact reasons each stock qualifies
4. Stores the watchlist and reasons in a persistent history database
5. Tracks subsequent price performance to identify which criteria produce the best results

---

## Watchlist Criteria (What Makes the List)

These are based on the Qullamaggie rules documented in `qullamaggie/breakouts/Rules.MD`.
A stock enters the daily watchlist if it passes **all Stage 1-4 checks** and is **approaching
a breakout** (within 2–5% of pivot):

### Stage 1: Universe Filter
- Price ≥ $5.00
- 20-day average daily volume ≥ 300,000 shares
- Average Daily Range (ADR%) ≥ 3%
- Not OTC / pink sheets

### Stage 2: Prior Explosive Move
- Gained ≥ 30% from a low within the last 40 trading days
- At least 1 day during the move with volume ≥ 2× its 20-day average
- Currently within 20% of its 52-week high

### Stage 3: Tight Base Formation
- Consolidation duration: 5–40 trading days
- Base depth (high-to-low): ≤ 15%
- Price has not closed below the 50-day MA during the base
- 10-day MA is above the 20-day MA

### Stage 4: Volume Contraction
- Average volume during base ≤ 60% of 50-day average
- At least 3 consecutive below-average volume days recently

### Watchlist Trigger: Near the Pivot
- Current price is within 5% of the base high (pivot price)
- A breakout alert will be set at the pivot price

---

## Data Source

**Recommended: `yfinance` (Yahoo Finance)**
- Free, no API key required
- Covers full US market (NYSE, NASDAQ, AMEX)
- Provides OHLCV daily data, 52-week high, moving averages

**Alternative: `polygon.io` (paid, more reliable)**
- Better for production use
- Real-time and historical data
- $29/month starter tier covers this use case

**Stock Universe Source**
- Use `pandas_datareader` or a static CSV of S&P 500 + Russell 2000 tickers
- Or pull from `finviz` via `finviz` Python library for pre-filtered screening

---

## Architecture

```
watchlist/
├── watchlist_scanner.py       # Main scanner — runs daily
├── criteria.py                # All watchlist criteria logic (reusable)
├── data_fetcher.py            # Pulls OHLCV + fundamentals
├── db_writer.py               # Writes results to SQL Server
├── performance_tracker.py     # Tracks price change after watchlist date
├── config.py                  # API keys, DB connection string, thresholds
├── requirements.txt           # Python dependencies
└── cron_setup.sh              # Cron job installer script
```

---

## Python Code Plan: `watchlist_scanner.py`

```python
# Pseudocode for main scanner flow

1. Load ticker universe (e.g., S&P 500 + Russell 2000)
2. For each ticker:
   a. Fetch 1 year of daily OHLCV data
   b. Compute: 20-day avg vol, 50-day MA, 10-day MA, 20-day MA, ATR, ADR%
   c. Run Stage 1 universe filter → skip if fail
   d. Detect prior explosive move (R6–R10)
   e. Identify consolidation base (R11–R18)
   f. Check volume contraction (R19–R22)
   g. Check distance to pivot (within 5%)
   h. Record ALL reasons the stock qualifies (each criterion met)
3. Compile watchlist
4. Write to SQL Server: watchlist_entries table
5. Write watchlist to CSV / send summary notification
```

---

## History Database: SQL Server

SQL Server is the recommended choice over AWS Bedrock for structured history.
Bedrock is a generative AI platform — it is not a database and would be inappropriate
for storing structured tabular history. SQL Server is ideal here.

### Table: `watchlist_entries`

```sql
CREATE TABLE watchlist_entries (
    id              INT IDENTITY PRIMARY KEY,
    scan_date       DATE NOT NULL,
    ticker          VARCHAR(10) NOT NULL,
    company_name    VARCHAR(100),
    price_at_scan   DECIMAL(10,2),
    pivot_price     DECIMAL(10,2),
    pct_from_pivot  DECIMAL(5,2),

    -- Criteria met (stored as flags + values for analysis)
    prior_move_pct          DECIMAL(5,2),   -- e.g. 45.3
    prior_move_days         INT,
    base_depth_pct          DECIMAL(5,2),
    base_duration_days      INT,
    volume_contraction_ratio DECIMAL(5,2),  -- base avg vol / 50d avg
    adr_pct                 DECIMAL(5,2),
    avg_daily_volume        INT,
    distance_to_pivot_pct   DECIMAL(5,2),
    ma10_above_ma20         BIT,
    above_50d_ma            BIT,
    volume_contraction_days INT,            -- consecutive low-vol days

    -- Free-text exact reasons (for audit + LLM analysis later)
    qualification_reasons   NVARCHAR(MAX),  -- JSON array of reason strings

    -- Pattern detected
    pattern_type    VARCHAR(50),            -- 'VCP', 'HTF', 'FlatBase', 'Pennant', etc.
    pattern_grade   VARCHAR(2),             -- 'A+', 'A', 'B', 'C'

    created_at      DATETIME DEFAULT GETDATE()
);
```

### Table: `watchlist_performance`

```sql
CREATE TABLE watchlist_performance (
    id              INT IDENTITY PRIMARY KEY,
    watchlist_id    INT FOREIGN KEY REFERENCES watchlist_entries(id),
    ticker          VARCHAR(10),
    scan_date       DATE,

    -- Price tracking (filled in by performance_tracker.py daily)
    price_1d        DECIMAL(10,2),   -- closing price 1 trading day later
    price_3d        DECIMAL(10,2),
    price_5d        DECIMAL(10,2),
    price_10d       DECIMAL(10,2),
    price_20d       DECIMAL(10,2),
    price_60d       DECIMAL(10,2),

    pct_change_1d   DECIMAL(6,2),
    pct_change_5d   DECIMAL(6,2),
    pct_change_10d  DECIMAL(6,2),
    pct_change_20d  DECIMAL(6,2),
    pct_change_60d  DECIMAL(6,2),

    did_break_out   BIT,             -- did price exceed pivot within 5 days?
    max_gain_pct    DECIMAL(6,2),    -- max gain achieved within 20 trading days
    max_gain_date   DATE,

    updated_at      DATETIME DEFAULT GETDATE()
);
```

---

## Scheduling: Cron Job (8 AM EST Weekdays)

Run on a Linux server or WSL. 8 AM EST = 13:00 UTC.

```bash
# Add to crontab (run: crontab -e)
# Weekdays at 8:00 AM EST (13:00 UTC)
0 13 * * 1-5 /usr/bin/python3 /path/to/watchlist/watchlist_scanner.py >> /var/log/watchlist.log 2>&1
```

**cron_setup.sh** (auto-installer):
```bash
#!/bin/bash
SCRIPT_PATH=$(realpath watchlist_scanner.py)
CRON_JOB="0 13 * * 1-5 /usr/bin/python3 $SCRIPT_PATH >> /var/log/watchlist.log 2>&1"
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
echo "Cron job installed."
```

> **Note for Windows users:** Use Task Scheduler instead of cron.
> Set trigger to daily, weekdays only, at 8:00 AM, and point to `python watchlist_scanner.py`.

---

## Performance Tracking & Criteria Refinement

`performance_tracker.py` runs daily (can be added to the same cron schedule, offset by a few minutes)
and fills in the `watchlist_performance` table with price data for past watchlist entries.

Once you have 30+ days of data, you can run SQL queries like:

```sql
-- Which criteria combinations produce the best 5-day returns?
SELECT
    pattern_type,
    AVG(p.pct_change_5d) AS avg_5d_return,
    COUNT(*) AS sample_size,
    SUM(CASE WHEN p.pct_change_5d > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS win_rate_pct
FROM watchlist_entries e
JOIN watchlist_performance p ON e.id = p.watchlist_id
GROUP BY pattern_type
ORDER BY avg_5d_return DESC;

-- Which volume contraction thresholds work best?
SELECT
    CASE
        WHEN volume_contraction_ratio < 0.4 THEN 'Very Tight (<40%)'
        WHEN volume_contraction_ratio < 0.6 THEN 'Tight (40-60%)'
        ELSE 'Loose (>60%)'
    END AS vol_category,
    AVG(p.pct_change_10d) AS avg_10d_return,
    COUNT(*) AS count
FROM watchlist_entries e
JOIN watchlist_performance p ON e.id = p.watchlist_id
GROUP BY
    CASE
        WHEN volume_contraction_ratio < 0.4 THEN 'Very Tight (<40%)'
        WHEN volume_contraction_ratio < 0.6 THEN 'Tight (40-60%)'
        ELSE 'Loose (>60%)'
    END
ORDER BY avg_10d_return DESC;
```

Use results to tighten or loosen individual criteria thresholds in `config.py`.

---

## Python Package Installation

```bash
# Core dependencies
pip install yfinance                  # Stock data (free, no API key)
pip install pandas                    # Data manipulation
pip install numpy                     # Numerical calculations
pip install pyodbc                    # SQL Server connection
pip install sqlalchemy                # ORM / DB abstraction
pip install pandas-ta                 # Technical indicators (MA, ATR, RSI)
pip install requests                  # HTTP requests
pip install python-dotenv             # .env file for secrets

# Optional: better data sources
pip install polygon-api-client        # Polygon.io (paid, production-grade)
pip install finviz                    # Finviz screener integration

# Optional: notifications
pip install twilio                    # SMS alerts
pip install sendgrid                  # Email alerts
```

**requirements.txt:**
```
yfinance>=0.2.18
pandas>=2.0.0
numpy>=1.24.0
pyodbc>=5.0.0
sqlalchemy>=2.0.0
pandas-ta>=0.3.14b
requests>=2.31.0
python-dotenv>=1.0.0
```

---

## Config: `.env` File

```env
# SQL Server
DB_SERVER=your-server.database.windows.net
DB_NAME=stocks
DB_USER=your_username
DB_PASSWORD=your_password

# Optional: Polygon.io
POLYGON_API_KEY=your_key_here

# Optional: Notifications
TWILIO_SID=...
TWILIO_TOKEN=...
NOTIFY_PHONE=+1...
```

---

## Output: Daily Watchlist

Each run produces:
1. **Database record** — full criteria detail per stock
2. **CSV file** — `watchlist_YYYY-MM-DD.csv` — human-readable daily snapshot
3. **Console summary** — top 10 stocks with grade and % from pivot

Example console output:
```
=== DAILY WATCHLIST — 2026-04-28 ===
Found 14 stocks meeting watchlist criteria.

Ticker  Grade  Price    Pivot    %Away  Pattern        Top Reasons
------  -----  ------   ------   -----  ----------     ---------------------------
AAPL    A+     $189.20  $191.00  0.9%   VCP            30d prior move +52%, 4 VCP legs, vol -68%, A10>MA20
NVDA    A      $127.50  $130.00  1.9%   FlatBase       45d prior move +38%, base depth 8%, vol -55%
...
```

---

## Phased Rollout

| Phase | Work | Outcome |
|-------|------|---------|
| 1 | Set up data fetcher + criteria.py | Can scan stocks manually |
| 2 | Build watchlist_scanner.py | Full daily scan working |
| 3 | Connect SQL Server, write db_writer.py | History being recorded |
| 4 | Install cron job | Fully automated at 8 AM |
| 5 | Build performance_tracker.py | Tracking outcomes |
| 6 | Run analysis queries | Start refining criteria |

---

*Last updated: 2026-04-27*
*Based on: `qullamaggie/breakouts/Rules.MD` and `qullamaggie/breakouts/Summary.MD`*
