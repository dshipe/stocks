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
6. Sends a formatted Telegram summary after every scan (watchlist results + stage funnel counts)

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
- Gained ≥ **25%** from a low within the last **60 trading days** *(updated 2026-04-27: was 30% / 40 days)*
- At least 1 day during the move with volume ≥ 2× its 20-day average
- Currently within 20% of its 52-week high

### Stage 3: Tight Base Formation
- Consolidation duration: 5–40 trading days
- Base depth (high-to-low): ≤ **20%** *(updated 2026-04-27: was 15%)*
- Price has not closed below the 50-day MA during the base
- 10-day MA is above the 20-day MA

### Stage 4: Volume Contraction
- Average volume during base ≤ **75%** of 50-day average *(updated 2026-04-27: was 60%)*
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
5. Write watchlist to CSV
6. Send Telegram summary (shared/telegram_notify.py → send_watchlist_summary)
```

---

## History Database: SQL Server

SQL Server is the recommended choice over AWS Bedrock for structured history.
Bedrock is a generative AI platform — it is not a database and would be inappropriate
for storing structured tabular history. SQL Server is ideal here.

### Connection String

```python
# In config.py or .env
DB_SERVER   = "ec2-35-172-202-150.compute-1.amazonaws.com"
DB_NAME     = "python"
DB_USER     = "ai-agent"
DB_PASSWORD = "Welcome100!"

CONNECTION_STRING = (
    f"mssql+pyodbc://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}/{DB_NAME}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
)
```

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

# Notifications
pip install requests                  # already required — used for Telegram Bot API
pip install twilio                    # optional: SMS alerts (only if TWILIO_SID is set)
pip install sendgrid                  # optional: email alerts
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
DB_SERVER=ec2-35-172-202-150.compute-1.amazonaws.com
DB_NAME=python
DB_USER=ai-agent
DB_PASSWORD=Welcome100!

# Optional: Polygon.io
POLYGON_API_KEY=your_key_here

# Telegram notifications (primary — always active)
TELEGRAM_BOT_TOKEN=<openclaw_bot_token>
TELEGRAM_CHAT_ID=<your_chat_id>

# Optional: Twilio SMS (only fires if all three are set)
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

---

## Implementation Issues & Resolutions

Issues encountered during the 2026-04-27 implementation on Ubuntu 24.04 AWS EC2.

### 1. ODBC Driver 17 Not Available on Ubuntu 24.04
**Issue:** The plan specified `ODBC Driver 17 for SQL Server`. Microsoft's Ubuntu 24.04 package
repository only ships `ODBC Driver 18`. The Ubuntu 22.04 repo was added by mistake initially,
causing a GPG signature failure.

**Resolution:** Used the Ubuntu 24.04 Microsoft repo (`packages.microsoft.com/config/ubuntu/24.04/prod.list`)
and installed `msodbcsql18`. Updated `config.py` default from `ODBC Driver 17` → `ODBC Driver 18`.

```bash
curl -fsSL https://packages.microsoft.com/config/ubuntu/24.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

### 2. pip Install Blocked on Ubuntu 24.04
**Issue:** Ubuntu 24.04 enforces PEP 668 — `pip install` refuses to write to system Python
without an explicit override.

**Resolution:** Added `--break-system-packages` flag. A virtual environment is cleaner for
production but not strictly required here:
```bash
pip3 install --break-system-packages -r requirements.txt
```

### 3. lxml Not Installed (Wikipedia Ticker Fetch Failed)
**Issue:** `pd.read_html()` requires `lxml` but it was not included in `requirements.txt`.
The Wikipedia S&P 500 fetch silently fell back to the hardcoded 40-ticker list.

**Resolution:** Added `lxml` to `requirements.txt` and installed it separately.
```bash
pip3 install --break-system-packages lxml
```

### 4. Wikipedia Returns HTTP 403 from Server IP
**Issue:** After `lxml` was installed, `pd.read_html()` calls to Wikipedia returned
`HTTP Error 403: Forbidden`. Wikipedia blocks requests with no User-Agent header,
which is the default for pandas/urllib.

**Resolution:** Rewrote `get_ticker_universe()` in `data_fetcher.py` to use `requests`
with a browser User-Agent header, then passed the HTML string to `pd.read_html()`:
```python
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 ..."})
tables = pd.read_html(StringIO(resp.text), ...)
```

### 5. `ai-agent` SQL Login Lacks CREATE TABLE Permission
**Issue:** The `ai-agent` SQL Server login has only `db_datareader` and `db_datawriter` roles.
Running `db_setup.sql` failed with: `CREATE TABLE permission denied in database 'python'`.

**Resolution:** Used the `sa` account (provided separately) to create the 4 tables and
6 indexes as a one-time operation. All subsequent scanner operations use `ai-agent` exclusively.
The SA account is not stored in `config.py`.

### 6. db_setup.sql GO Batches Failed in Python
**Issue:** The `db_setup.sql` file uses `GO` batch separators (standard for SSMS/sqlcmd).
Splitting on `GO` and executing batches sequentially via pyodbc caused the `CREATE INDEX`
statements to fail because pyodbc didn't always see the committed tables in the same session.

**Resolution:** Replaced the SQL file execution with direct Python `CREATE TABLE` / `CREATE INDEX`
statements using `conn.autocommit = True` and `IF NOT EXISTS` checks per object. The `db_setup.sql`
file remains in the repo for use with SSMS/sqlcmd where GO batches work correctly.

### 7. Disk Space Tight on EC2 Instance
**Issue:** `/dev/root` was 84% full (~1.1 GB free) before package installation.

**Status:** Installation completed successfully. Monitor with `df -h` — if space becomes an issue,
clear pip cache: `pip3 cache purge` or clean apt: `sudo apt-get clean`.

### 8. Delisted / Bad Tickers in yfinance
**Issue:** Some tickers in the hardcoded fallback list (e.g. `SQ`, now trading as `XYZ`)
caused yfinance warnings: `possibly delisted; no timezone found`.

**Resolution:** These are caught by the per-ticker `try/except` in `watchlist_scanner.py`
and skipped silently. The Wikipedia-sourced universe avoids this by staying current.
The fallback list was also updated with more current tickers.

---

### 9. Telegram Notifications Added (2026-04-27)
**Change:** Both scanners now send results to Telegram automatically after each run.

- `shared/telegram_notify.py` added — `send_watchlist_summary()` and `send_breakout_alert()`
- `watchlist_scanner.py` calls `send_watchlist_summary()` at the end of every full scan
- `breakout_scanner.py` calls `send_breakout_alert()` inside `send_notification()` for each breakout
- Uses the OpenClaw Telegram bot token and Dan's chat ID (overridable via `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`)
- Dry-run and single-ticker (`--ticker`) scans skip the Telegram notification
- Twilio SMS remains as an optional secondary channel

---

*Based on: `qullamaggie/breakouts/Rules.MD` and `qullamaggie/breakouts/Summary.MD`*
*Implemented: 2026-04-27 on Ubuntu 24.04 AWS EC2, Python 3.12, SQL Server 2016*

---

### 10. SNDK / WDC Missing from Watchlist — Root Cause & Fix (2026-04-29)
**Reported:** Both SNDK and WDC absent from the daily watchlist despite being in strong
multi-month uptrends and near 52-week highs.

**Root causes (two separate bugs):**

**Bug 1 — `find_prior_explosive_move` sets peak_date too close to today**
The outer loop allowed `end_idx` all the way to the most recent bar. WDC peaked April 24
(4 trading days ago) and SNDK peaked April 27 (1 day ago). When `peak_date` is that recent,
`find_consolidation_base` receives a `df_after` with fewer rows than `MIN_BASE_DAYS=5` and
returns `None` — silently dropping both stocks.

*Fix:* Cap `end_idx` at `len(lookback_df) - 1 - MIN_BASE_DAYS` so any detected peak always
has at least 5 subsequent trading days of data for base formation.

**Bug 2 — `MAX_DIST_FROM_PIVOT_PCT` too tight for SNDK**
After Bug 1 is fixed, the peak shifts back to ~April 21. The new base high (pivot) is the
April 27 all-time high of $1,070. SNDK's current price ($1,002) is 6.3% below the pivot —
just outside the old 5% trigger.

*Fix:* Raise `MAX_DIST_FROM_PIVOT_PCT` from **5% → 8%**. 8% still represents a tight
pre-breakout setup; Qullamaggie's 5% rule is a guideline, not a hard constraint.

**Changes committed:**
- `scan/shared/criteria.py` commit `4f06f18` — peak end_idx cap
- `scan/config.py` commit `a75b6e6` — MAX_DIST_FROM_PIVOT_PCT 5% → 8%

---

---

### 11. Stage 2 Redesign: Momentum Trend Filter (2026-04-29)

**Problem:** The prior explosive move detector is an *event detector* — it looks for
a specific ≥25% move within a sliding 60-day window. Once that window expires, the stock
disappears from the watchlist even if it's still the strongest stock in the market.

**Observed failure:** CVNA was on the watchlist on 2026-04-28 (valid +25% prior move in
43 days). By 2026-04-29 the move had aged out of the 60-day window — Stage 2 returned
None and CVNA was silently dropped. The stock itself hadn't changed; just the detection
window.

**Root cause (design):** Event detection ages out. Performance measurement doesn't.

**Solution: Multi-timeframe momentum as the Stage 2 gate**

Instead of "did a big move happen in the last 60 days?", ask:
"Is this stock still a market leader right now?"

```
check_momentum_trend():
    1M (20d) gain  ≥ 10%   (lenient — healthy consolidation expected)
    3M (60d) gain  ≥ 20%
    6M (120d) gain ≥ 30%
    within 20% of 52-week high
```

This measures *current state*, not a past event. A stock in its 3rd leg up, 90 days
after its initial explosive move, still shows strong 3M/6M momentum and qualifies.

**Prior explosive move → Stage 2b (bonus grading)**

`find_prior_explosive_move()` still runs, but a miss no longer drops the stock.
When found, it contributes to the grade score (A+ vs B). When absent, `grade_setup()`
falls back to 3M momentum for scoring. The prior move data still appears in
`qualification_reasons` when present.

**Base anchor fallback**

When no prior move is found, `find_consolidation_base()` is anchored from the stock's
most recent 52-week high date (capped so ≥5 days of base data exist).

**Files changed:**
- `scan/config.py` — added `MIN_MOMENTUM_1M/3M/6M_PCT`
- `scan/shared/criteria.py` — added `check_momentum_trend()`, updated `grade_setup()` and `build_qualification_reasons()` signatures
- `scan/watchlist_scanner.py` — Stage 2 wired to `check_momentum_trend`, Stage 2b is now optional, stats show both counts

---

*Last updated: 2026-04-29*
