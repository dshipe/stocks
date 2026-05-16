"""
criteria.py — Qullamaggie breakout setup criteria (Stages 1–5).

Each function corresponds to a numbered rule set in:
    docs/watchlist-plan.md and docs/breakout-scanner-plan.md

Rules reference (e.g. R6) match the table in qullamaggie/breakouts/Rules.MD.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as cfg

logger = logging.getLogger(__name__)


# ─── Stage 1: Universe Filter ─────────────────────────────────────────────────

def check_universe_filter(df: pd.DataFrame, ticker: str) -> dict | None:
    """
    Stage 1: Minimum requirements for a stock to be worth evaluating.

    Rules applied: R1 (price >= $5), R2 (avg vol >= 300k), R3 (ADR% >= 3%)

    Returns dict with filter values, or None if the stock fails.
    """
    if df is None or len(df) < 20:
        return None

    last = df.iloc[-1]

    current_price = float(last["Close"])
    avg_vol_20d   = float(last["avg_vol_20d"]) if not pd.isna(last["avg_vol_20d"]) else 0
    adr_pct       = float(last["adr_pct"])     if not pd.isna(last["adr_pct"])     else 0

    # R1: Minimum price
    if current_price < cfg.MIN_PRICE:
        return None

    # R2: Minimum average daily volume
    if avg_vol_20d < cfg.MIN_AVG_VOLUME:
        return None

    # R3: Minimum ADR% (daily movement potential)
    if adr_pct < cfg.MIN_ADR_PCT:
        return None

    return {
        "current_price": current_price,
        "avg_vol_20d":   avg_vol_20d,
        "adr_pct":       adr_pct,
    }



# ─── Stage 2: Momentum Trend Filter ──────────────────────────────────────────

def check_momentum_trend(df: pd.DataFrame) -> dict | None:
    """
    Stage 2: Multi-timeframe momentum trend filter.

    Ensures the stock is a current market leader by measuring actual price
    performance over 1M (20d), 3M (60d), and 6M (120d) windows.
    This never ages out — it measures current state, not a past event.

    Rules applied:
        R6a — 1M (20d) gain >= MIN_MOMENTUM_1M_PCT%
        R6b — 3M (60d) gain >= MIN_MOMENTUM_3M_PCT%
        R6c — 6M (120d) gain >= MIN_MOMENTUM_6M_PCT%
        R9  — within MAX_FROM_52W_HIGH% of 52-week high

    Added 2026-04-29: Replaces find_prior_explosive_move() as the Stage 2 gate.
    Prior explosive move (find_prior_explosive_move) is still run as Stage 2b
    and used as bonus scoring in grade_setup() — but failing it does NOT exclude
    the stock from the watchlist.

    Returns dict with performance metrics, or None if any threshold is missed.
    """
    if len(df) < 120:
        return None

    price = float(df["Close"].iloc[-1])

    def pct_gain(days: int) -> float | None:
        if len(df) < days:
            return None
        old = float(df["Close"].iloc[-days])
        return ((price - old) / old * 100) if old > 0 else None

    pct_1m = pct_gain(20)
    pct_3m = pct_gain(60)
    pct_6m = pct_gain(120)

    if pct_1m is None or pct_1m < cfg.MIN_MOMENTUM_1M_PCT:
        return None
    if pct_3m is None or pct_3m < cfg.MIN_MOMENTUM_3M_PCT:
        return None
    if pct_6m is None or pct_6m < cfg.MIN_MOMENTUM_6M_PCT:
        return None

    # R9: Must be near 52-week high
    high_52w = float(df["High"].tail(252).max())
    pct_from_52w = ((high_52w - price) / high_52w * 100) if high_52w > 0 else 100.0
    if pct_from_52w > cfg.MAX_FROM_52W_HIGH:
        return None

    return {
        "pct_1m":            round(pct_1m, 2),
        "pct_3m":            round(pct_3m, 2),
        "pct_6m":            round(pct_6m, 2),
        "pct_from_52w_high": round(pct_from_52w, 2),
    }




# ─── Runner State Check ──────────────────────────────────────────────────────────────────

def check_runner_state(
    df: pd.DataFrame,
    universe: dict,
    momentum: dict,
    prior_move: dict | None = None,
) -> dict | None:
    """
    Determine if a stock that passed Stage 1+2 but failed Stage 3 is in a
    clean markup/runner phase worth monitoring.

    A runner is a stock still in active uptrend that has not yet paused to
    form a consolidation base.  Called only when find_consolidation_base()
    returns None.

    Args:
        prior_move: Result of find_prior_explosive_move() for this ticker.
                    Used to enforce RUNNER_REQUIRE_PRIOR_MOVE gate (added 2026-05-06).
                    Pass None if prior move was not computed.

    Returns runner detail dict, or None if the stock is not in markup phase.
    """
    last  = df.iloc[-1]
    price = universe["current_price"]

    # R_RUN3: Price floor — tighter than Stage 1 to filter micro-caps (added 2026-05-16).
    # Micro-caps trading $5-$10 produce noisy extreme-% signals from a tiny base.
    if price < cfg.MIN_RUNNER_PRICE:
        return None

    # R_RUN4: Volume floor — tighter than Stage 1 to ensure liquidity (added 2026-05-16).
    if universe["avg_vol_20d"] < cfg.MIN_RUNNER_AVG_VOLUME:
        return None

    # R_RUN2: Require a prior explosive move (added 2026-05-06).
    # Ensures runners have a known catalyst — not just generic momentum.
    # To remove this gate: set RUNNER_REQUIRE_PRIOR_MOVE=false in scan/.env
    if cfg.RUNNER_REQUIRE_PRIOR_MOVE and prior_move is None:
        return None

    # Must be in clean uptrend: price > MA20 > MA50
    ma20 = float(last["ma20"]) if not pd.isna(last["ma20"]) else None
    ma50 = float(last["ma50"]) if not pd.isna(last["ma50"]) else None
    if ma20 is None or ma50 is None:
        return None
    if price < ma20:
        return None   # price broke below 20d MA — not in clean markup
    if ma20 < ma50:
        return None   # 20d MA crossed below 50d MA — trend broken

    # R_RUN1: Must be within MAX_RUNNER_FROM_20D_HIGH of recent high (added 2026-05-06,
    # tightened from hardcoded 15% to cfg.MAX_RUNNER_FROM_20D_HIGH).
    # Rationale: stocks pulling back further have likely completed their immediate move.
    # To loosen: raise MAX_RUNNER_FROM_20D_HIGH in config.py or scan/.env
    high_20d = float(df["High"].tail(20).max())
    pct_from_20d_high = round(((high_20d - price) / high_20d * 100), 2) if high_20d > 0 else 0
    if pct_from_20d_high > cfg.MAX_RUNNER_FROM_20D_HIGH:
        return None

    return {
        "pct_from_52w_high": momentum["pct_from_52w_high"],
        "pct_from_20d_high": pct_from_20d_high,
        "pct_1m":            momentum["pct_1m"],
        "pct_3m":            momentum["pct_3m"],
        "pct_6m":            momentum["pct_6m"],
        "price_above_ma20":  True,
        "ma20_above_ma50":   True,
    }

# ─── Stage 2b: Prior Explosive Move (bonus — not a gate) ──────────────────────
# ─── Stage 2b: Prior Explosive Move (bonus grading only) ────────────────────────

def find_prior_explosive_move(df: pd.DataFrame) -> dict | None:
    """
    Stage 2: Detect if the stock made a powerful prior move of >= 30% within
    the last 40 trading days. Looks back further to allow for base formation.

    Rules applied: R6 (30%+ in 40 days), R7 (1+ day with 2x volume during move),
                   R9 (within 20% of 52-week high)

    Returns dict with move details or None if no qualifying move found.
    """
    if len(df) < cfg.MAX_PRIOR_MOVE_DAYS + 10:
        return None

    # Look back up to 80 trading days to find a qualifying move
    lookback_df = df.iloc[-80:].copy()
    closes  = lookback_df["Close"].values
    volumes = lookback_df["Volume"].values
    avg_vols = lookback_df["avg_vol_20d"].values

    best_move = None

    # Slide a window of up to MAX_PRIOR_MOVE_DAYS to find the best qualifying move.
    # Cap end_idx so the detected peak always has at least MIN_BASE_DAYS trading days
    # of data after it — otherwise find_consolidation_base returns None immediately.
    max_end_idx = len(lookback_df) - 1 - cfg.MIN_BASE_DAYS
    for end_idx in range(max_end_idx, cfg.MAX_PRIOR_MOVE_DAYS, -1):
        for start_idx in range(max(0, end_idx - cfg.MAX_PRIOR_MOVE_DAYS), end_idx - 4):
            low_price  = closes[start_idx]
            high_price = closes[end_idx]

            if low_price <= 0:
                continue

            move_pct  = ((high_price - low_price) / low_price) * 100
            move_days = end_idx - start_idx

            if move_pct < cfg.MIN_PRIOR_MOVE_PCT:
                continue

            # R7: At least one day with volume >= 2x average during the move
            move_volumes = volumes[start_idx:end_idx + 1]
            move_avg_vols = avg_vols[start_idx:end_idx + 1]
            vol_surges = [
                v for v, av in zip(move_volumes, move_avg_vols)
                if av > 0 and v >= cfg.MIN_VOL_SURGE_RATIO * av
            ]
            if not vol_surges:
                continue

            # Track best move found (highest %)
            if best_move is None or move_pct > best_move["move_pct"]:
                peak_date = lookback_df.index[end_idx].date()
                best_move = {
                    "move_pct":         round(move_pct, 2),
                    "move_days":        move_days,
                    "peak_date":        peak_date,
                    "peak_price":       round(high_price, 4),
                    "trough_price":     round(low_price, 4),
                    "vol_surge_days":   len(vol_surges),
                }

    if best_move is None:
        return None

    # R9: Stock must be within MAX_FROM_52W_HIGH% of its 52-week high
    high_52w = float(df["High"].tail(252).max())
    current  = float(df["Close"].iloc[-1])
    if high_52w > 0:
        pct_from_52w_high = ((high_52w - current) / high_52w) * 100
        if pct_from_52w_high > cfg.MAX_FROM_52W_HIGH:
            return None
        best_move["pct_from_52w_high"] = round(pct_from_52w_high, 2)

    return best_move


# ─── Stage 3: Base / Consolidation ────────────────────────────────────────────

def find_consolidation_base(df: pd.DataFrame, peak_date: date) -> dict | None:
    """
    Stage 3: Find a tight consolidation base that formed after the explosive move.

    Rules applied: R11 (5-40 trading days), R12 (base depth <= 15%),
                   R14 (above 50d MA), R15/R16 (10d MA above 20d MA)

    Returns dict with base details or None if no valid base found.
    """
    # Slice from peak date to present
    df_after = df[df.index.date >= peak_date].copy()

    if len(df_after) < cfg.MIN_BASE_DAYS:
        return None
    if len(df_after) > cfg.MAX_BASE_DAYS + 5:
        # Use the most recent MAX_BASE_DAYS window
        df_after = df_after.iloc[-cfg.MAX_BASE_DAYS:]

    base_duration = len(df_after)
    if base_duration < cfg.MIN_BASE_DAYS or base_duration > cfg.MAX_BASE_DAYS:
        return None

    base_high = float(df_after["High"].max())
    base_low  = float(df_after["Low"].min())

    if base_high <= 0:
        return None

    base_depth_pct = ((base_high - base_low) / base_high) * 100

    # R12: Base must be tight (depth <= MAX_BASE_DEPTH_PCT)
    if base_depth_pct > cfg.MAX_BASE_DEPTH_PCT:
        return None

    last = df_after.iloc[-1]

    # R14: Price should not have closed below 50d MA during the base
    # Check last bar as a proxy (full scan would be expensive)
    ma50    = last["ma50"]    if not pd.isna(last["ma50"])    else None
    ma10    = last["ma10"]    if not pd.isna(last["ma10"])    else None
    ma20    = last["ma20"]    if not pd.isna(last["ma20"])    else None
    close   = float(last["Close"])

    above_50d_ma   = (close >= ma50) if ma50 else True
    ma10_above_ma20 = (ma10 >= ma20) if (ma10 and ma20) else True  # R16

    # Find the high bar date (pivot price)
    pivot_idx  = df_after["High"].idxmax()
    pivot_date = pivot_idx.date()

    return {
        "base_high":          round(base_high, 4),
        "base_low":           round(base_low, 4),
        "base_depth_pct":     round(base_depth_pct, 2),
        "base_start_date":    df_after.index[0].date(),
        "base_end_date":      df_after.index[-1].date(),
        "base_duration_days": base_duration,
        "pivot_price":        round(base_high, 4),  # pivot = top of base
        "above_50d_ma":       above_50d_ma,
        "ma10_above_ma20":    ma10_above_ma20,
    }


# ─── Stage 4: Volume Contraction ──────────────────────────────────────────────

def check_volume_contraction(df: pd.DataFrame, base_start_date: date) -> dict | None:
    """
    Stage 4 (bonus grading — not a gate since 2026-04-29):
    Confirm that volume dried up during the consolidation base.
    Result used to boost grade (A+/A/B/C) but a None return no longer
    drops the stock from the watchlist.

    Rules applied: R19 (base avg vol <= MAX_BASE_VOL_RATIO of 50d avg),
                   R20 (>= MIN_CONSEC_LOW_VOL_DAYS consecutive low-vol days)

    Returns dict with contraction metrics or None if criteria not met.
    """
    df_base = df[df.index.date >= base_start_date].copy()

    if df_base.empty:
        return None

    base_avg_vol = float(df_base["Volume"].mean())
    last_50d_avg = float(df.iloc[-1]["avg_vol_50d"]) if not pd.isna(df.iloc[-1]["avg_vol_50d"]) else 0

    if last_50d_avg == 0:
        return None

    contraction_ratio = base_avg_vol / last_50d_avg

    # R19: Average volume in base must be <= MAX_BASE_VOL_RATIO of 50d average
    if contraction_ratio > cfg.MAX_BASE_VOL_RATIO:
        return None

    # R20: Count consecutive below-average volume days at the end of the base
    recent_vols = df_base["Volume"].tail(10).values
    consec_low = 0
    for v in reversed(recent_vols):
        if v < last_50d_avg:
            consec_low += 1
        else:
            break

    if consec_low < cfg.MIN_CONSEC_LOW_VOL_DAYS:
        return None

    return {
        "base_avg_vol":        int(base_avg_vol),
        "avg_vol_50d":         int(last_50d_avg),
        "contraction_ratio":   round(contraction_ratio, 3),
        "consecutive_low_vol_days": consec_low,
    }


# ─── Pattern Detection ────────────────────────────────────────────────────────

def detect_pattern_type(df: pd.DataFrame, base: dict) -> str:
    """
    Identify the chart pattern formed during consolidation.

    Patterns: VCP, HTF, FlatBase, Pennant
    Based on: tightness of base, number of contraction legs, prior move magnitude.
    """
    base_depth = base.get("base_depth_pct", 15)
    duration   = base.get("base_duration_days", 10)

    # High-Tight Flag: very short, very tight, after a huge move
    if base_depth <= 10 and duration <= 15:
        return "HTF"

    # VCP: tight with visible volume contractions (depth 5-15%, medium duration)
    if base_depth <= 12 and 10 <= duration <= 35:
        return "VCP"

    # Flat Base: very tight depth, longer duration
    if base_depth <= 8 and duration >= 10:
        return "FlatBase"

    # Pennant / triangle: moderate depth, shorter duration
    if base_depth <= 15 and duration <= 20:
        return "Pennant"

    return "FlatBase"


def grade_setup(
    prior_move: dict | None,
    base: dict,
    vol_contraction: dict | None,
    pattern_type: str,
    momentum: dict | None = None,
) -> str:
    """
    Assign a quality grade (A+, A, B, C) to the setup.

    Grading rubric from qullamaggie/breakouts/Index.MD:
        A+: 60%+ prior move (or 3M momentum), 4+ VCP contractions, volume near zero
        A : 40%+ prior move (or 3M momentum), good volume dry-up
        B : 30%+ prior move (or 3M momentum), adequate contraction
        C : borderline

    prior_move is optional (Stage 2b bonus); falls back to 3M momentum for scoring.
    """
    score = 0

    # Prior move scoring — use prior_move if found, else 3M momentum as proxy
    if prior_move:
        move_pct = prior_move.get("move_pct", 0)
        if move_pct >= 60:
            score += 3
        elif move_pct >= 40:
            score += 2
        elif move_pct >= 30:
            score += 1
    elif momentum:
        pct_3m = momentum.get("pct_3m", 0)
        if pct_3m >= 60:
            score += 3
        elif pct_3m >= 40:
            score += 2
        elif pct_3m >= 20:
            score += 1

    # Base depth scoring
    depth = base.get("base_depth_pct", 15)
    if depth <= 5:
        score += 3
    elif depth <= 8:
        score += 2
    elif depth <= 12:
        score += 1

    # Volume contraction scoring (bonus — not a gate since 2026-04-29)
    if vol_contraction:
        ratio = vol_contraction.get("contraction_ratio", 1.0)
        if ratio <= 0.30:
            score += 3
        elif ratio <= 0.45:
            score += 2
        elif ratio <= 0.60:
            score += 1
        # Bonus for consecutive quiet days
        consec = vol_contraction.get("consecutive_low_vol_days", 0)
        if consec >= 5:
            score += 1
    # No vol_contraction → no bonus, stock still qualifies

    # Pattern bonus
    if pattern_type in ("VCP", "HTF"):
        score += 1

    # MA alignment bonus
    if base.get("ma10_above_ma20"):
        score += 1

    # Map score to grade
    if score >= 9:
        return "A+"
    elif score >= 7:
        return "A"
    elif score >= 5:
        return "B"
    else:
        return "C"


# ─── Stage 5: Breakout Detection ──────────────────────────────────────────────

def check_breakout(intraday: dict, base: dict, avg_vol_20d: float) -> dict | None:
    """
    Stage 5: Confirm an active breakout using intraday data.

    Rules applied:
        R23 — price above base high (pivot)
        R24 — last 30-min candle volume >= 3x average 30-min volume (intensity check)
        R25 — current price within 5% of session high (strong candle)

    **OPTIMIZATION (2026-05-07):** Changed R24 from cumulative daily volume to intraday
    30-min volume intensity. At 10:00 AM, we can't predict final daily volume, but we
    can check if the LAST 30-MIN CANDLE shows strong institutional buying (3x avg).
    This is a better predictor of real conviction than waiting for daily volume.

    Returns dict with breakout details or None if not breaking out.
    """
    if not intraday or not base:
        return None

    pivot_price      = base.get("pivot_price", 0)
    current_price    = intraday.get("current_price", 0)
    cum_volume       = intraday.get("cum_volume", 0)
    candle_close_pct = intraday.get("candle_close_pct", 999)
    last_30min_vol   = intraday.get("last_30min_volume", 0)
    avg_30min_vol    = intraday.get("avg_30min_volume", 0)

    if pivot_price <= 0 or current_price <= 0:
        return None

    # R23: Price must be above the pivot (base high)
    if current_price <= pivot_price:
        return None

    # R24 (UPDATED): 30-min volume intensity must be >= 3x average 30-min volume
    # This checks if the MOST RECENT 30-MIN candle shows strong institutional interest
    # vs. the historical 30-min average. Avoids the problem of not knowing final daily volume.
    if avg_30min_vol <= 0:
        return None
    volume_ratio = last_30min_vol / avg_30min_vol if avg_30min_vol > 0 else 0
    if volume_ratio < cfg.MIN_BREAKOUT_30MIN_VOL_RATIO:  # R24: last 30-min candle >= 3x avg 30-min vol
        return None

    # R25: Price must be close to session high (strong candle — not reversing)
    if candle_close_pct > cfg.MAX_CLOSE_FROM_HIGH_PCT:
        return None

    pct_above_pivot = ((current_price - pivot_price) / pivot_price) * 100

    return {
        "breakout_price":    round(current_price, 4),
        "pivot_price":       round(pivot_price, 4),
        "pct_above_pivot":   round(pct_above_pivot, 2),
        "breakout_volume":   cum_volume,
        "volume_ratio":      round(volume_ratio, 2),  # 30-min intensity ratio (not daily)
        "candle_close_pct":  round(candle_close_pct, 2),
        "last_30min_volume": last_30min_vol,
        "avg_30min_volume":  avg_30min_vol,
    }


# ─── ADR-Based Breakout (parallel path) ──────────────────────────────────────

def check_adr_breakout(intraday: dict, df: pd.DataFrame) -> dict | None:
    """
    Parallel breakout path: detects pure momentum moves without requiring a base or pivot.

    Catches episodic pivots, news-driven surges, and any stock that moves a meaningful
    multiple of its normal daily range on above-average volume — regardless of whether
    it was consolidating beforehand.

    Rules applied:
        ADR1 — intraday move from prev close >= MIN_ADR_BREAKOUT_MULT × ADR%
                Scales with each stock's own volatility. ADR=4%, mult=0.5 → need 2%+ move.
        ADR2 — cumulative day volume >= MIN_ADR_BREAKOUT_VOL_RATIO × avg daily volume (20d)
                Uses full-day cumulative volume (not 30-min intensity) because the signal
                here is sustained buying, not a single candle surge.
        ADR3 — price within MAX_CLOSE_FROM_HIGH_PCT% of session high (shared with R25)
                Ensures the move isn't reversing intraday.

    Uses df.iloc[-2]["Close"] as prev_close (yesterday's close) so the function is
    safe to call during market hours when df.iloc[-1] may be today's partial bar.

    Returns dict with breakout details or None if conditions not met.
    Added: 2026-05-11
    """
    if not intraday or df is None or len(df) < 3:
        return None

    last        = df.iloc[-1]
    prev_close  = float(df.iloc[-2]["Close"])
    adr_pct     = float(last["adr_pct"])     if not pd.isna(last["adr_pct"])     else 0
    avg_vol_20d = float(last["avg_vol_20d"]) if not pd.isna(last["avg_vol_20d"]) else 0

    if adr_pct <= 0 or avg_vol_20d <= 0 or prev_close <= 0:
        return None

    current_price    = intraday.get("current_price", 0)
    cum_volume       = intraday.get("cum_volume", 0)
    candle_close_pct = intraday.get("candle_close_pct", 999)
    last_30min_vol   = intraday.get("last_30min_volume", 0)
    avg_30min_vol    = intraday.get("avg_30min_volume", 0)

    if current_price <= 0:
        return None

    # ADR1: Move from prev close must be >= N × ADR%
    move_pct      = ((current_price - prev_close) / prev_close) * 100
    adr_threshold = cfg.MIN_ADR_BREAKOUT_MULT * adr_pct
    if move_pct < adr_threshold:
        return None

    # ADR2: Last 30-min candle intensity >= threshold × avg 30-min volume.
    # Cumulative daily volume cannot be used at 10 AM — it will never reach
    # yesterday's full-day total. Same approach as R24 in check_breakout().
    if avg_30min_vol <= 0:
        return None
    volume_ratio = last_30min_vol / avg_30min_vol
    if volume_ratio < cfg.MIN_ADR_BREAKOUT_30MIN_VOL_RATIO:
        return None

    # ADR3: Price near session high (not reversing) — reuses R25 threshold
    if candle_close_pct > cfg.MAX_CLOSE_FROM_HIGH_PCT:
        return None

    return {
        "breakout_price":    round(current_price, 4),
        "pivot_price":       round(prev_close, 4),      # prev close is the reference level
        "pct_above_pivot":   round(move_pct, 2),
        "breakout_volume":   cum_volume,
        "volume_ratio":      round(volume_ratio, 2),    # 30-min intensity ratio
        "candle_close_pct":  round(candle_close_pct, 2),
        "adr_pct":           round(adr_pct, 2),
        "adr_mult":          round(move_pct / adr_pct, 2),
        "last_30min_volume": last_30min_vol,
        "avg_30min_volume":  avg_30min_vol,
    }


# ─── Qualification Reasons ────────────────────────────────────────────────────

def build_qualification_reasons(
    prior_move: dict | None,
    base: dict,
    vol_contraction: dict | None,
    pattern_type: str,
    grade: str,
    momentum: dict | None = None,
) -> str:
    """
    Build a JSON array of human-readable qualification reasons for the database.

    Returns a JSON string (list of reason strings), most important first.
    Stored in watchlist_entries.qualification_reasons and breakout_entries.qualification_reasons.

    prior_move is optional (Stage 2b bonus); momentum is the Stage 2 gate result.
    Both may be None — the function handles all combinations gracefully.
    """
    reasons = []

    # Stage 2b: prior explosive move (most specific signal — lead with it)
    if prior_move:
        reasons.append(
            f"Prior move: +{prior_move['move_pct']:.1f}% in {prior_move['move_days']}d"
            f" (peak {prior_move['peak_date']})"
        )

    # Stage 2: momentum trend (always present for watchlist entries)
    if momentum:
        reasons.append(
            f"Momentum: 1M {momentum['pct_1m']:+.1f}%  "
            f"3M {momentum['pct_3m']:+.1f}%  "
            f"6M {momentum['pct_6m']:+.1f}%"
        )

    # Stage 3: base quality
    reasons.append(
        f"Base: {base['base_depth_pct']:.1f}% depth over {base['base_duration_days']}d"
    )
    if base.get("above_50d_ma"):
        reasons.append("Above 50d MA")
    if base.get("ma10_above_ma20"):
        reasons.append("10d MA above 20d MA")

    # Stage 4: volume contraction (bonus — may be None)
    if vol_contraction:
        reasons.append(
            f"Vol contraction: {vol_contraction['contraction_ratio']:.0%} of 50d avg"
            f" ({vol_contraction['consecutive_low_vol_days']}d consecutive)"
        )

    # Pattern and grade
    reasons.append(f"Pattern: {pattern_type}  Grade: {grade}")

    return json.dumps(reasons)
