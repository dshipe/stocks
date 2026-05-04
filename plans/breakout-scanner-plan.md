# Breakout Scanner — Plan

> A system to detect stocks exhibiting live breakout signals based on Qullamaggie methodology,
> maintain a history of breakout candidates with exact qualifying reasons, and track performance
> to continuously refine breakout detection criteria.

---

## Overview

The breakout scanner differs from the watchlist in one key way:
- **Watchlist** = stocks *approaching* a breakout (setting up within **8%** of pivot)
- **Breakout scanner** = stocks that are **breaking out RIGHT NOW** (price crossing the pivot on volume)

The scanner runs every **30 minutes during market hours** and checks:
1. **Today's watchlist** (`watchlist_entries`) — the 8 AM pre-qualified candidates
2. **Today's runners** (`runner_entries`) — Stage 1+2 passes still in markup (no base yet), via `check_runner_breakout()`. This catches same-day runner→base→breakout transitions the morning scan would miss.

This keeps the scan fast and focused — no full-universe screen intraday.

---

## Breakout Criteria (What Constitutes a Breakout)

Based on Stages 5–8 of `qullamaggie/breakouts/Rules.MD`:

### Required (Hard Rules — checked at breakout time)
| Rule | Criterion |
|------|-----------|
| R23 | Price has broken above the high of the consolidation base (pivot price) |
| R24 | Breakout volume ≥ 150% of 20-day average volume |
| R25 | Breakout candle closes within 5% of its high (strong close) |

> **Note:** R6–R10 (prior move), R11–R12 (base depth/duration), and R19 (volume contraction)
> are **setup criteria** evaluated by the watchlist scanner at 8 AM — not re-checked intraday.
> Since 2026-04-29 they are also bonus grading signals, not hard gates. A stock on the
> watchlist already satisfied Stage 1+2+3 before the market opened.

### Preferred (Adds Confidence)
| Rule | Criterion |
|------|-----------|
| R26 | No earnings within 3 trading days |
| R27 | S&P 500 / NASDAQ in uptrend |
| R16 | 10-day MA above 20-day MA |
| R46 | Sector in uptrend |
| R45 | VIX < 30 |

### Pattern Types Detected
- High-Tight Flag (HTF)
- Flat Base / Rectangle
- Volatility Contraction Pattern (VCP)
- Pennant / Symmetrical Triangle
- Episodic Pivot (gap-up on catalyst)

---

## Should This Be a Python Script or an AI Prompt?

### ✅ Recommendation: Python Script

**Verdict: Build the Python script.**

Here is the full comparison:

| Factor | Python Script | AI Prompt (Claude/GPT) |
|--------|--------------|------------------------|
| **Anthropic token cost** | None — runs locally | ~$0.50–$5.00+ per daily scan |
| **Speed** | Scans 3,000+ stocks in minutes | Slow — sequential API calls |
| **Consistency** | Deterministic, same rules every time | Can vary between runs |
| **Auditability** | Exact rule values logged | Harder to trace reasoning |
| **Scalability** | Trivial to add new tickers | Cost scales linearly with scope |
| **History/DB writes** | Native Python → SQL Server | Requires extra tooling |
| **Maintenance** | Edit `criteria.py` to tune rules | Update prompt wording |
| **Explainability** | Logs exact criterion values | Returns natural language |

**Why Python wins here:**
The breakout criteria are **quantitative and rule-based** (e.g., "volume ≥ 150% of 20-day avg").
These are exactly the kinds of computations Python excels at. An AI prompt would add cost,
latency, and non-determinism without adding value for the detection step.

**Where AI (Bedrock) makes sense:**
Use AWS Bedrock for the *analysis layer* — not detection. Specifically:
- Summarizing which patterns are working best (natural language insight from SQL data)
- Drafting weekly performance summaries
- Answering ad-hoc questions like "which breakout setups from the last 30 days had the best 10-day return?"

This hybrid approach gets the best of both: Python for detection + Bedrock for insight.

---

## Architecture

```
breakout_scanner/
├── breakout_scanner.py        # Main scanner — detects live breakouts
├── criteria.py                # Shared criteria logic (can import from watchlist/)
├── data_fetcher.py            # Pulls OHLCV + intraday data
├── db_writer.py               # Writes to SQL Server
├── performance_tracker.py     # Tracks post-breakout price performance
├── analysis_report.py         # Optional: Bedrock-powered weekly insight report
├── config.py                  # Thresholds, DB connection, API keys
├── requirements.txt
└── cron_setup.sh
```

---

## Python Code Plan: `breakout_scanner.py`

```python
# Pseudocode for main breakout scanner flow

1. Check market hours — exit immediately if market is closed or holiday
2. Load today's watchlist from SQL Server
   → SELECT ticker, pivot_price, pattern_type, pattern_grade
     FROM watchlist_entries WHERE scan_date = TODAY
   → If watchlist is empty (8 AM job hasn't run yet), exit and log warning
3. For each ticker on today's watchlist:
   a. Fetch latest intraday price + cumulative volume (via yfinance or Polygon)
   b. Fetch daily OHLCV history (for MA / ATR calculations)
   c. Skip if already logged as a breakout today (avoid duplicate alerts)
   d. CHECK BREAKOUT:
      - Is current price > pivot_price? (price crossed the base high)
      - Is cumulative intraday volume ≥ 150% of 20-day average volume?
      - Is current candle within 5% of its intraday high?
   e. If breakout confirmed:
      - Identify pattern type (inherited from watchlist entry)
      - Compute exact values: volume ratio, % above pivot, current price
      - Record ALL exact reasons with values (e.g., "Volume = 287% of 20d avg")
      - Compute stop price (base low − 0.5%), R/R ratio
      - Write to SQL Server breakout_entries (link to watchlist_entry_id)
      - Send notification (SMS/email)
4. Log run summary: X stocks checked, Y new breakouts detected
```

### Key Logic: Avoid Duplicate Alerts
```python
# Before writing a breakout, check if it was already recorded today
existing = db.query(
    "SELECT id FROM breakout_entries WHERE ticker = ? AND scan_date = ?",
    [ticker, today]
)
if existing:
    continue  # Already alerted — skip
```

---

## When to Run

The scanner runs **every 30 minutes during market hours** (9:30 AM – 4:00 PM EST, weekdays).
It only checks the stocks on today's watchlist, so each run is fast (typically < 30 seconds).

### Market Hours Schedule

| Run | EST | UTC |
|-----|-----|-----|
| Open | 9:30 AM | 14:30 |
| Every 30 min | 10:00, 10:30 … 3:30 PM | 15:00–20:30 |
| Final (close) | 4:00 PM | 21:00 |

### Cron Job (runs every 30 min, Mon–Fri, 9:30 AM–4:00 PM EST)

```bash
# 9:30 AM – 4:00 PM EST = 14:30 – 21:00 UTC
# Run at :00 and :30 past the hour, between 14:00–21:00 UTC
0,30 14-20 * * 1-5 /usr/bin/python3 /path/to/breakout_scanner/breakout_scanner.py >> /var/log/breakout_scanner.log 2>&1
# Extra run at 21:00 UTC (4:00 PM EST close)
0 21 * * 1-5 /usr/bin/python3 /path/to/breakout_scanner/breakout_scanner.py >> /var/log/breakout_scanner.log 2>&1
```

> **Note:** The script should check `datetime.now()` at startup and exit immediately if
> the market is closed or it's a market holiday — this prevents unnecessary runs.

### Intraday Data Source
Since the scanner runs during market hours it needs **live or delayed intraday prices**.
Recommended options (in order of preference):

| Source | Cost | Delay | Notes |
|--------|------|-------|-------|
| `yfinance` | Free | ~15 min | Good enough for 30-min polling |
| Polygon.io Starter | $29/mo | Real-time | Best for production |
| Alpaca (free tier) | Free | Real-time | Requires brokerage account |

---

## History Database: SQL Server

SQL Server is the right choice for structured breakout history. AWS Bedrock is a
generative AI platform and cannot store structured relational data — do not use it as a database.

### Connection Details

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

### Table: `breakout_entries`

```sql
CREATE TABLE breakout_entries (
    id              INT IDENTITY PRIMARY KEY,
    scan_date       DATE NOT NULL,
    ticker          VARCHAR(10) NOT NULL,
    company_name    VARCHAR(100),

    -- Breakout details
    breakout_price      DECIMAL(10,2),   -- price at breakout candle
    pivot_price         DECIMAL(10,2),   -- base high (the breakout level)
    breakout_volume     BIGINT,
    avg_volume_20d      BIGINT,
    volume_ratio        DECIMAL(5,2),    -- breakout_volume / avg_volume_20d
    candle_close_pct    DECIMAL(5,2),    -- how close close was to candle high

    -- Preceding setup details
    prior_move_pct          DECIMAL(5,2),
    prior_move_days         INT,
    base_depth_pct          DECIMAL(5,2),
    base_duration_days      INT,
    volume_contraction_ratio DECIMAL(5,2),
    adr_pct                 DECIMAL(5,2),
    avg_daily_volume        INT,
    ma10_above_ma20         BIT,
    above_50d_ma            BIT,

    -- Risk management at time of breakout
    stop_price          DECIMAL(10,2),   -- base low - 0.5%
    atr_14              DECIMAL(8,4),
    risk_per_share      DECIMAL(8,4),    -- breakout_price - stop_price
    suggested_rr_ratio  DECIMAL(4,2),    -- minimum 2:1

    -- Pattern and grade
    pattern_type        VARCHAR(50),     -- 'VCP', 'HTF', 'FlatBase', etc.
    pattern_grade       VARCHAR(2),      -- 'A+', 'A', 'B', 'C'
    is_episodic_pivot   BIT,             -- gap-up catalyst breakout
    catalyst_notes      NVARCHAR(500),   -- e.g. "Earnings beat Q1 +45% EPS"

    -- Market conditions at breakout
    sp500_above_50d_ma  BIT,
    sp500_above_200d_ma BIT,
    vix_level           DECIMAL(5,2),
    sector_trend        VARCHAR(20),     -- 'Uptrend', 'Neutral', 'Downtrend'

    -- Exact qualifying reasons (JSON array)
    qualification_reasons   NVARCHAR(MAX),

    -- Was this stock on the prior-day watchlist?
    was_on_watchlist    BIT,
    watchlist_entry_id  INT,             -- FK to watchlist_entries if applicable

    created_at          DATETIME DEFAULT GETDATE()
);
```

### Table: `breakout_performance`

```sql
CREATE TABLE breakout_performance (
    id              INT IDENTITY PRIMARY KEY,
    breakout_id     INT FOREIGN KEY REFERENCES breakout_entries(id),
    ticker          VARCHAR(10),
    breakout_date   DATE,
    breakout_price  DECIMAL(10,2),
    stop_price      DECIMAL(10,2),

    -- Price tracking
    price_1d        DECIMAL(10,2),
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

    -- Trade outcome simulation
    hit_stop        BIT,             -- did price ever hit stop_price?
    hit_stop_date   DATE,
    max_r_multiple  DECIMAL(5,2),    -- max (price - entry) / (entry - stop) achieved
    max_gain_pct    DECIMAL(6,2),
    max_gain_date   DATE,

    was_failed_breakout BIT,         -- closed back below pivot within 3 days

    updated_at      DATETIME DEFAULT GETDATE()
);
```

---

## Performance Analysis Queries

Once you have 30+ breakout records, run these to refine criteria:

```sql
-- Which patterns produce the best 10-day returns?
SELECT
    pattern_type,
    COUNT(*) AS total,
    AVG(p.pct_change_10d) AS avg_10d_return,
    AVG(p.max_r_multiple) AS avg_max_r,
    SUM(CASE WHEN p.pct_change_10d > 5 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS win_rate_5pct
FROM breakout_entries e
JOIN breakout_performance p ON e.id = p.breakout_id
GROUP BY pattern_type
ORDER BY avg_10d_return DESC;

-- Does higher breakout volume = better outcomes?
SELECT
    CASE
        WHEN volume_ratio >= 3.0 THEN '3x+ volume'
        WHEN volume_ratio >= 2.0 THEN '2x-3x volume'
        WHEN volume_ratio >= 1.5 THEN '1.5x-2x volume'
        ELSE '<1.5x volume'
    END AS vol_bucket,
    COUNT(*) AS count,
    AVG(p.pct_change_10d) AS avg_10d_return,
    AVG(p.max_r_multiple) AS avg_max_r
FROM breakout_entries e
JOIN breakout_performance p ON e.id = p.breakout_id
GROUP BY
    CASE
        WHEN volume_ratio >= 3.0 THEN '3x+ volume'
        WHEN volume_ratio >= 2.0 THEN '2x-3x volume'
        WHEN volume_ratio >= 1.5 THEN '1.5x-2x volume'
        ELSE '<1.5x volume'
    END
ORDER BY avg_10d_return DESC;

-- Breakouts that were also on watchlist vs. not
SELECT
    CASE WHEN was_on_watchlist = 1 THEN 'Was on watchlist' ELSE 'Not on watchlist' END AS watchlist_status,
    COUNT(*) AS count,
    AVG(p.pct_change_10d) AS avg_10d_return
FROM breakout_entries e
JOIN breakout_performance p ON e.id = p.breakout_id
GROUP BY was_on_watchlist;

-- Failed breakouts by condition
SELECT
    pattern_type,
    sp500_above_50d_ma,
    COUNT(*) AS total,
    SUM(CASE WHEN was_failed_breakout = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct
FROM breakout_entries e
JOIN breakout_performance p ON e.id = p.breakout_id
GROUP BY pattern_type, sp500_above_50d_ma
ORDER BY failure_rate_pct DESC;
```

---

## AWS Bedrock: Where It Fits

AWS Bedrock should NOT replace the SQL Server for storage. It can add value in the following ways:

### Weekly Insight Report (`analysis_report.py`)
- Query SQL Server for the past week's breakout performance
- Pass summary stats to Bedrock (Claude on Bedrock)
- Ask: "Based on this data, which criteria are most predictive of a 10-day gain > 10%?"
- Receive natural language insight and recommendations

```python
# Example Bedrock call
import boto3, json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

stats_summary = load_weekly_stats_from_sql()   # returns dict

response = client.invoke_model(
    modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": f"Here are last week's breakout scan results:\n\n{stats_summary}\n\nWhich criteria combinations had the best outcomes? What should I adjust?"
        }]
    })
)
```

This way Bedrock is used sparingly (once/week) for strategic analysis, keeping costs minimal.

---

## Scheduling (Full System)

```bash
# 1. Watchlist generator — 8:00 AM EST (13:00 UTC), weekdays
0 13 * * 1-5 /usr/bin/python3 /path/to/watchlist/watchlist_scanner.py >> /var/log/watchlist.log 2>&1

# 2. Breakout scanner — every 30 min during market hours (9:30 AM–4:00 PM EST)
#    14:30–21:00 UTC = market hours
0,30 14-20 * * 1-5 /usr/bin/python3 /path/to/breakout_scanner/breakout_scanner.py >> /var/log/breakout_scanner.log 2>&1
0 21 * * 1-5 /usr/bin/python3 /path/to/breakout_scanner/breakout_scanner.py >> /var/log/breakout_scanner.log 2>&1

# 3. Performance tracker — 4:30 PM EST (21:30 UTC), weekdays
30 21 * * 1-5 /usr/bin/python3 /path/to/breakout_scanner/performance_tracker.py >> /var/log/breakout_perf.log 2>&1
```

### Daily Timeline

```
08:00 AM EST  → Watchlist scanner runs — loads today's candidates into SQL Server
09:30 AM EST  → Market opens — breakout scanner starts polling every 30 min
09:30–04:00   → Scanner checks watchlist stocks every 30 min for breakout signals
               → Alerts fire immediately when a breakout is detected
04:00 PM EST  → Market closes — final breakout scan run
04:30 PM EST  → Performance tracker updates prior breakout entries with today's close
```

---

## Python Package Installation

```bash
# Core dependencies
pip install yfinance                  # Stock OHLCV data (free)
pip install pandas                    # Data analysis
pip install numpy                     # Numerical computations
pip install pyodbc                    # SQL Server driver
pip install sqlalchemy                # DB abstraction layer
pip install pandas-ta                 # Technical indicators (MA, ATR, RSI, ADR)
pip install requests                  # HTTP / API calls
pip install python-dotenv             # Environment variable management

# Optional: better intraday data
pip install polygon-api-client        # Polygon.io real-time + historical
pip install alpaca-trade-api          # Alpaca (free tier available)

# Optional: AWS Bedrock weekly insight reports
pip install boto3                     # AWS SDK

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
boto3>=1.34.0
```

---

## Output: Per-Run Breakout Alerts

Each 30-minute run produces:

1. **Database records** — full detail per breakout with all criteria values (written once per ticker per day)
2. **Immediate notification** — SMS or email when a new breakout is detected mid-day
3. **Console/log summary** for each run:

```
=== BREAKOUT SCAN — 2026-04-28 10:30 AM EST ===
Watchlist stocks checked: 14
New breakouts detected: 2

Ticker  Grade  Pattern    Price    Volume%  Pivot    %Above  R/R    Alert
------  -----  ---------  ------   -------  ------   ------  -----  ------
CELH    A+     VCP        $48.30   312%     $47.50   +1.7%   3.2:1  ✅ BREAKOUT
SMCI    A      FlatBase   $29.10   198%     $28.80   +1.0%   2.8:1  ✅ BREAKOUT

Already alerted today: NVDA (10:00 AM)
No trigger yet: AAPL, TSLA, CRWD (+9 others)
```

---

## Phased Rollout

| Phase | Work | Outcome |
|-------|------|---------|
| 1 | Build watchlist scanner (see watchlist-plan.md) | Daily candidate list in SQL Server |
| 2 | Build `data_fetcher.py` — intraday price + volume | Can fetch live quotes for a ticker |
| 3 | Build `breakout_scanner.py` — reads watchlist from SQL | Detects breakouts against today's watchlist |
| 4 | Connect SQL Server, write `db_writer.py` | Breakout history captured with dedup logic |
| 5 | Install cron jobs (8 AM watchlist + 30-min scanner) | Fully automated intraday monitoring |
| 6 | Add SMS/email notifications | Real-time alerts when breakout fires |
| 7 | Build `performance_tracker.py` | Tracking post-breakout outcomes |
| 8 | Run analysis SQL queries | Start refining criteria |
| 9 | Add Bedrock weekly report (optional) | AI-assisted criteria refinement |

---

## Relationship to Watchlist

These two systems are now tightly coupled:

```
Watchlist (8:00 AM)         → Scans full market, identifies setup candidates, loads into SQL Server
Breakout Scanner (every 30 min) → Reads today's watchlist from SQL, monitors only those stocks

Data flow:
  watchlist_scanner.py  →  watchlist_entries (SQL)  →  breakout_scanner.py  →  breakout_entries (SQL)
```

Every breakout entry is linked to its watchlist entry via `watchlist_entry_id`, so you can
always trace back exactly why a stock was being watched when it broke out.

**What if the watchlist hasn't run yet?**
If `breakout_scanner.py` starts before 8 AM has completed (rare edge case), it will find
no rows for today in `watchlist_entries` and exit cleanly with a log message:
`"No watchlist entries for today — skipping run."`

---

---

## Implementation Issues & Resolutions

Same environment as watchlist scanner (Ubuntu 24.04, Python 3.12, SQL Server 2016).
Issues specific to the breakout scanner are noted below; shared issues are documented
in `watchlist-plan.md`.

### 1. Base Detection Occasionally Fails on Intraday Run
**Issue:** `find_consolidation_base()` uses the peak date from the prior move to slice
daily history forward. When called intraday, the most recent bars may not yet reflect a
completed session, causing the base window to be 1 day short of the minimum threshold.

**Resolution:** Added a fallback in `breakout_scanner.py`: if base detection fails for a
watchlist ticker, the pivot price stored in `watchlist_entries` (set at 8 AM) is used
directly. This ensures the breakout check can still run using the pre-computed pivot.

### 2. NaN Propagation in Intraday avg_vol_20d
**Issue:** `compute_indicators()` uses a 20-day rolling average. When only intraday
(1-minute) data is fetched, there are insufficient rows for a 20-day rolling window,
returning NaN for `avg_vol_20d`, which caused the volume ratio check to be skipped.

**Resolution:** `breakout_scanner.py` fetches 60 days of daily history separately
(in addition to the intraday snapshot) to compute reliable `avg_vol_20d`. The intraday
fetch is only used for current price, session high, and cumulative volume.

### 3. NaN Comparison Errors in Python
**Issue:** Pandas NaN values don't behave like regular Python `None` — `nan != nan` is True,
causing silent bugs in conditional checks like `if not last["avg_vol_20d"]`.

**Resolution:** Added explicit NaN guards throughout `breakout_scanner.py`:
```python
avg_vol_20d = float(last["avg_vol_20d"]) if last["avg_vol_20d"] == last["avg_vol_20d"] else 0
```
Future improvement: use `pd.notna()` consistently across all indicator reads.

### 4. Duplicate Breakout Alerts
**Issue:** With the scanner running every 30 minutes, the same breakout would fire
multiple times per day without a deduplication check.

**Resolution:** `breakout_already_logged_today(ticker)` is called before processing each
watchlist stock. If a breakout entry already exists for that ticker today, the stock is
skipped and reported in the "Already alerted today" summary line.

### 5. market_open Check Timezone Accuracy
**Issue:** The server runs UTC. Without `pytz`, the market hours check uses a hardcoded
UTC-4 offset (EDT), which is incorrect during Eastern Standard Time (UTC-5, Nov–Mar).

**Resolution:** `pytz` is installed and used when available. The `is_market_open()`
function in `data_fetcher.py` uses `pytz.timezone("America/New_York")` which automatically
handles DST transitions. The UTC-4 fallback remains as a last resort.

### 6. S&P 500 Context Fetch Overhead
**Issue:** `get_sp500_context()` fetches 250 days of SPY data on every 30-minute run,
adding ~2 seconds of latency per scan cycle.

**Mitigation:** SPY data is fetched once per run and reused for all tickers. Future
optimisation: cache SPY context to disk with a 4-hour TTL to avoid repeated fetches.

### 7. Runner Breakout Detection Added (2026-04-30)
**Change:** The breakout scanner now also scans `runner_entries` (stocks in markup with no
base yet) via `check_runner_breakout()`. If a runner forms a base intraday and immediately
breaks out, the scanner catches it — something the 8 AM watchlist scan would miss entirely.

This means the breakout scanner checks two sources on each 30-minute run:
1. `watchlist_entries` (pre-qualified base setups from the morning scan)
2. `runner_entries` (Stage 1+2 passes still in markup — same-day base→breakout only)

---

*Last updated: 2026-04-30*
*Based on: `qullamaggie/breakouts/Rules.MD`, `qullamaggie/breakouts/Summary.MD`, `qullamaggie/breakouts/vcp_setup.MD`*
*Implemented: 2026-04-27 on Ubuntu 24.04 AWS EC2, Python 3.12, SQL Server 2016*
