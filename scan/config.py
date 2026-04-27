"""
config.py — Central configuration for the stock scanning system.

All thresholds are based on Qullamaggie methodology documented in plans/.
Override any value via a .env file in the scan/ directory.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── SQL Server ────────────────────────────────────────────────────────────────
DB_SERVER   = os.getenv("DB_SERVER",   "ec2-35-172-202-150.compute-1.amazonaws.com")
DB_NAME     = os.getenv("DB_NAME",     "python")
DB_USER     = os.getenv("DB_USER",     "ai-agent")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Welcome100!")
DB_DRIVER   = os.getenv("DB_DRIVER",   "ODBC Driver 18 for SQL Server")

DB_CONNECTION_STRING = (
    f"DRIVER={{{DB_DRIVER}}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASSWORD};"
    "TrustServerCertificate=yes;"
)

# ─── Stage 1: Universe Filter ──────────────────────────────────────────────────
MIN_PRICE           = float(os.getenv("MIN_PRICE",      "5.0"))    # R1
MIN_AVG_VOLUME      = int(os.getenv("MIN_AVG_VOLUME",   "300000")) # R2
MIN_ADR_PCT         = float(os.getenv("MIN_ADR_PCT",    "3.0"))    # R3

# ─── Stage 2: Prior Explosive Move ────────────────────────────────────────────
MIN_PRIOR_MOVE_PCT  = float(os.getenv("MIN_PRIOR_MOVE_PCT",  "30.0")) # R6
MAX_PRIOR_MOVE_DAYS = int(os.getenv("MAX_PRIOR_MOVE_DAYS",   "40"))   # R6
MIN_VOL_SURGE_RATIO = float(os.getenv("MIN_VOL_SURGE_RATIO", "2.0"))  # R7
MAX_FROM_52W_HIGH   = float(os.getenv("MAX_FROM_52W_HIGH",   "20.0")) # R9 — within 20% of 52w high

# ─── Stage 3: Base / Consolidation ────────────────────────────────────────────
MIN_BASE_DAYS       = int(os.getenv("MIN_BASE_DAYS",    "5"))     # R11
MAX_BASE_DAYS       = int(os.getenv("MAX_BASE_DAYS",    "40"))    # R11
MAX_BASE_DEPTH_PCT  = float(os.getenv("MAX_BASE_DEPTH_PCT", "15.0")) # R12

# ─── Stage 4: Volume Contraction ──────────────────────────────────────────────
MAX_BASE_VOL_RATIO      = float(os.getenv("MAX_BASE_VOL_RATIO",      "0.60")) # R19
MIN_CONSEC_LOW_VOL_DAYS = int(os.getenv("MIN_CONSEC_LOW_VOL_DAYS",   "3"))    # R20

# ─── Watchlist Trigger ─────────────────────────────────────────────────────────
MAX_DIST_FROM_PIVOT_PCT = float(os.getenv("MAX_DIST_FROM_PIVOT_PCT", "5.0"))  # within 5% of pivot

# ─── Stage 5: Breakout Confirmation ───────────────────────────────────────────
MIN_BREAKOUT_VOL_RATIO  = float(os.getenv("MIN_BREAKOUT_VOL_RATIO",  "1.50")) # R24 — 150% of avg
MAX_CLOSE_FROM_HIGH_PCT = float(os.getenv("MAX_CLOSE_FROM_HIGH_PCT", "5.0"))  # R25 — close within 5% of candle high

# ─── Notifications (optional) ─────────────────────────────────────────────────
TWILIO_SID      = os.getenv("TWILIO_SID",   "")
TWILIO_TOKEN    = os.getenv("TWILIO_TOKEN", "")
NOTIFY_PHONE    = os.getenv("NOTIFY_PHONE", "")
TWILIO_FROM     = os.getenv("TWILIO_FROM",  "")

# ─── Market Hours (EST) ────────────────────────────────────────────────────────
MARKET_OPEN_HOUR    = 9
MARKET_OPEN_MINUTE  = 30
MARKET_CLOSE_HOUR   = 16
MARKET_CLOSE_MINUTE = 0
MARKET_TIMEZONE     = "America/New_York"
