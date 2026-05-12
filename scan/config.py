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

# ─── Stage 2: Momentum Trend Filter (gating condition — added 2026-04-29) ────
# Replaces prior explosive move as the primary Stage 2 gate.
# Measures current performance vs historical — never ages out.
MIN_MOMENTUM_1M_PCT  = float(os.getenv("MIN_MOMENTUM_1M_PCT", "5.0"))   # R6a — 1M (20d) gain >= 5% (lowered from 10% 2026-04-29: 112 stocks were failing on 1M alone)
MIN_MOMENTUM_3M_PCT  = float(os.getenv("MIN_MOMENTUM_3M_PCT", "15.0"))  # R6b — 3M (60d) gain >= 15% (lowered from 20% 2026-04-29: recovers ~20 additional stocks)
MIN_MOMENTUM_6M_PCT  = float(os.getenv("MIN_MOMENTUM_6M_PCT", "30.0"))  # R6c — 6M (120d) gain >= 30%

# ─── Stage 2b: Prior Explosive Move (bonus — grading only, not a gate) ───────
MIN_PRIOR_MOVE_PCT  = float(os.getenv("MIN_PRIOR_MOVE_PCT",  "25.0")) # R6 — lowered from 30% (2026-04-27)
MAX_PRIOR_MOVE_DAYS = int(os.getenv("MAX_PRIOR_MOVE_DAYS",   "60"))   # R6 — extended from 40 days (2026-04-27)
MIN_VOL_SURGE_RATIO = float(os.getenv("MIN_VOL_SURGE_RATIO", "2.0"))  # R7
MAX_FROM_52W_HIGH   = float(os.getenv("MAX_FROM_52W_HIGH",   "20.0")) # R9 — within 20% of 52w high

# ─── Stage 3: Base / Consolidation ────────────────────────────────────────────
MIN_BASE_DAYS       = int(os.getenv("MIN_BASE_DAYS",    "5"))     # R11
MAX_BASE_DAYS       = int(os.getenv("MAX_BASE_DAYS",    "40"))    # R11
MAX_BASE_DEPTH_PCT  = float(os.getenv("MAX_BASE_DEPTH_PCT", "20.0")) # R12 — raised from 15% (2026-04-27)

# ─── Runner Gates (added 2026-05-06) ─────────────────────────────────────────
# Controls which Stage 1+2 stocks without a base qualify as runners.
# Two tighter gates were added to reduce list noise and enforce the
# Qullamaggie definition: actively marking up AND has a known catalyst.
#
# To revert both gates to the original looser behavior:
#   RUNNER_REQUIRE_PRIOR_MOVE=false   in scan/.env  (removes prior-move requirement)
#   MAX_RUNNER_FROM_20D_HIGH=15.0     in scan/.env  (restores original 15% proximity)

MAX_RUNNER_FROM_20D_HIGH  = float(os.getenv("MAX_RUNNER_FROM_20D_HIGH",  "10.0"))
# R_RUN1: Runner must be within 10% of its 20-day high (tightened from hardcoded 15%).
# Rationale: stocks pulling back >10% have likely completed their immediate move.

RUNNER_REQUIRE_PRIOR_MOVE = os.getenv("RUNNER_REQUIRE_PRIOR_MOVE", "true").lower() == "true"
# R_RUN2: Runner must have a prior explosive move on record (Stage 2b).
# Rationale: runners with no catalyst are generic momentum stocks, not high-conviction.
# To disable: RUNNER_REQUIRE_PRIOR_MOVE=false in scan/.env

# ─── Stage 4: Volume Contraction ──────────────────────────────────────────────
MAX_BASE_VOL_RATIO      = float(os.getenv("MAX_BASE_VOL_RATIO",      "0.85")) # R19 — raised from 0.75 (2026-04-29: KLAC, MRVL, BKR etc. failing at 0.75)
MIN_CONSEC_LOW_VOL_DAYS = int(os.getenv("MIN_CONSEC_LOW_VOL_DAYS",   "3"))    # R20

# ─── Watchlist Trigger ─────────────────────────────────────────────────────────
MAX_DIST_FROM_PIVOT_PCT = float(os.getenv("MAX_DIST_FROM_PIVOT_PCT", "8.0"))  # within 8% of pivot (raised from 5% on 2026-04-29: SNDK was 6.4% away and excluded)

# ─── Stage 5: Breakout Confirmation (base-pivot path) ────────────────────────
# R24 (updated 2026-05-07): Now checks last 30-min candle intensity, not cumulative daily volume.
# At 10:00 AM you cannot know if the day will finish at 1.25x daily avg - use intraday intensity instead.
MIN_BREAKOUT_30MIN_VOL_RATIO = float(os.getenv("MIN_BREAKOUT_30MIN_VOL_RATIO", "3.0"))  # R24 - last 30-min candle >= 3x avg 30-min volume
MIN_BREAKOUT_VOL_RATIO  = float(os.getenv("MIN_BREAKOUT_VOL_RATIO",  "1.25")) # legacy - kept for reference, not used in check_breakout()
MAX_CLOSE_FROM_HIGH_PCT = float(os.getenv("MAX_CLOSE_FROM_HIGH_PCT", "5.0"))  # R25 - close within 5% of candle high

# ─── ADR-Based Breakout (parallel path — added 2026-05-11) ───────────────────
# Catches pure momentum moves (episodic pivots, news surges) without requiring
# a base or pivot. Runs in parallel with the base-pivot path in the breakout scanner.
# A stock that fires both paths is reported as base-pivot (higher conviction).
#
# ADR1: intraday move from prev close >= MIN_ADR_BREAKOUT_MULT × ADR%
#        e.g. ADR=4%, mult=0.5 → need a 2%+ move. Scales with the stock's volatility.
# ADR2: cumulative day volume >= MIN_ADR_BREAKOUT_VOL_RATIO × avg daily volume (20d)
# ADR3: price within MAX_CLOSE_FROM_HIGH_PCT% of session high (shared with R25)
#
# To tighten (fewer, higher-conviction signals):
#   MIN_ADR_BREAKOUT_MULT=1.0      (full ADR move required)
#   MIN_ADR_BREAKOUT_VOL_RATIO=2.0 (2x daily avg volume)
# To disable: MIN_ADR_BREAKOUT_MULT=999 in scan/.env
MIN_ADR_BREAKOUT_MULT          = float(os.getenv("MIN_ADR_BREAKOUT_MULT",          "0.5"))  # ADR1
MIN_ADR_BREAKOUT_30MIN_VOL_RATIO = float(os.getenv("MIN_ADR_BREAKOUT_30MIN_VOL_RATIO", "2.0"))  # ADR2 — last 30-min candle >= 2x avg 30-min vol
# Note: daily cumulative volume cannot be used at 10 AM — it will never exceed yesterday's full-day vol.
# The 30-min intensity check (same approach as R24) is the correct intraday proxy.

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
