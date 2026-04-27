# Breakout Scanner — Plan

> A system to detect stocks exhibiting live breakout signals based on Qullamaggie methodology,
> maintain a history of breakout candidates with exact qualifying reasons, and track performance
> to continuously refine breakout detection criteria.

---

## Overview

The breakout scanner differs from the watchlist in one key way:
- **Watchlist** = stocks *approaching* a breakout (setting up within 5% of pivot)
- **Breakout scanner** = stocks that are **breaking out RIGHT NOW** (price crossing the pivot on volume)

A stock can appear on the breakout scanner without being on the prior day's watchlist —
for example, it may have been missed in screening or formed a setup very quickly.

---

## Breakout Criteria (What Constitutes a Breakout)

Based on Stages 5–8 of `qullamaggie/breakouts/Rules.MD`:

### Required (Hard Rules)
| Rule | Criterion |
|------|-----------|
| R23 | Price has broken above the high of the consolidation base (pivot price) |
| R24 | Breakout volume ≥ 150% of 20-day average volume |
| R25 | Breakout candle closes within 5% of its high (strong close) |
| R6–R10 | Prior move of ≥ 30% within last 40 trading days |
| R11–R12 | Base depth ≤ 15%, duration 5–40 days |
| R19 | Average base volume ≤ 60% of 50-day average |

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

1. Load ticker universe
2. Fetch previous day's OHLCV data (or intraday if running during market hours)
3. For each ticker:
   a. Compute moving averages, ATR, ADR%, volume averages
   b. Run Stage 1 universe filter → skip if fail
   c. Detect prior explosive move (R6–R10) → skip if none
   d. Identify consolidation base → skip if no valid base
   e. Check volume contraction in base
   f. CHECK BREAKOUT:
      - Did price close above the base high (pivot)?
      - Was volume ≥ 150% of 20-day average?
      - Did candle close within 5% of its high?
   g. If breakout confirmed:
      - Identify pattern type (VCP, HTF, FlatBase, Pennant, EP)
      - Assign grade (A+, A, B, C)
      - Record ALL exact reasons with values (e.g., "Volume = 287% of 20d avg")
      - Compute entry price, stop price, position size suggestions
      - Write to SQL Server
4. Output summary of today's breakouts
5. (Optional) Send notification via SMS/email
```

---

## When to Run

The scanner can run in two modes:

### Mode 1: End-of-Day (Recommended for beginners)
- Run at **4:30 PM EST** after market close
- Uses final daily candle data
- Confirms breakout candles are genuine (full close, not intraday noise)
- Cron: `30 21 * * 1-5` (21:30 UTC)

### Mode 2: Intraday (Advanced)
- Run at **10:00 AM EST** (after first 30 minutes) using intraday data
- Detects Opening Range High (ORH) breakouts
- Requires intraday data source (Polygon.io or Alpaca)
- Allows same-day entry if criteria met
- Cron: `0 15 * * 1-5` (15:00 UTC)

**Suggested approach:** Start with end-of-day, add intraday later once history is building.

---

## History Database: SQL Server

SQL Server is the right choice for structured breakout history. AWS Bedrock is a
generative AI platform and cannot store structured relational data — do not use it as a database.

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

## Scheduling

```bash
# End-of-day breakout scan — 4:30 PM EST (21:30 UTC), weekdays
30 21 * * 1-5 /usr/bin/python3 /path/to/breakout_scanner/breakout_scanner.py >> /var/log/breakout_scanner.log 2>&1

# Performance tracker — 5:00 PM EST (22:00 UTC), weekdays
0 22 * * 1-5 /usr/bin/python3 /path/to/breakout_scanner/performance_tracker.py >> /var/log/breakout_perf.log 2>&1
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

## Output: Daily Breakout Report

Each run produces:

1. **Database records** — full detail per breakout with all criteria values
2. **CSV file** — `breakouts_YYYY-MM-DD.csv`
3. **Console summary:**

```
=== BREAKOUT SCAN — 2026-04-28 (End of Day) ===
Scanned: 3,247 stocks
Breakouts detected: 7

Ticker  Grade  Pattern    Price    Volume%  Prior Move  R/R    Reasons
------  -----  ---------  ------   -------  ----------  -----  -------------------
CELH    A+     VCP        $48.30   312%     +67% / 22d  3.2:1  Vol 3.1x, VCP 4-leg, near 52wk high
SMCI    A      FlatBase   $29.10   198%     +41% / 30d  2.8:1  Base 6% deep, vol contraction -62%
...
```

---

## Phased Rollout

| Phase | Work | Outcome |
|-------|------|---------|
| 1 | Build `data_fetcher.py` + `criteria.py` | Can evaluate any stock |
| 2 | Build `breakout_scanner.py` | Detects breakouts with end-of-day data |
| 3 | Connect SQL Server, write `db_writer.py` | History capturing begins |
| 4 | Install cron job (4:30 PM mode) | Fully automated daily scan |
| 5 | Build `performance_tracker.py` | Tracking post-breakout outcomes |
| 6 | Run analysis SQL queries | Start refining criteria |
| 7 | Add Bedrock weekly report (optional) | AI-assisted criteria refinement |
| 8 | Upgrade to intraday mode (optional) | Same-day ORH entries |

---

## Relationship to Watchlist

These two systems complement each other:

```
Watchlist (8 AM)    → "These stocks are SETTING UP — watch them today"
Breakout Scanner (4:30 PM) → "These stocks BROKE OUT today — log and track"

Cross-reference:    Was today's breakout on yesterday's watchlist?
                    If yes → setup was anticipated (higher quality signal)
                    If no  → fast-forming or missed setup (still valid)
```

Both tables should be linked via `watchlist_entry_id` in `breakout_entries` so you can measure
whether advance watchlist identification improves outcomes.

---

*Last updated: 2026-04-27*
*Based on: `qullamaggie/breakouts/Rules.MD`, `qullamaggie/breakouts/Summary.MD`, `qullamaggie/breakouts/vcp_setup.MD`*
