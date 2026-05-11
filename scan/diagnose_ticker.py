#!/usr/bin/env python3
"""
diagnose_ticker.py — Run a single ticker through all stages and explain exactly
why it is or isn't on the watchlist, runner list, or showing as a breakout.

Usage:
    python3 diagnose_ticker.py SNDK
    python3 diagnose_ticker.py NVDA
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta
from shared.data_fetcher import fetch_history, compute_indicators
from shared.criteria import (
    check_universe_filter, check_momentum_trend,
    find_prior_explosive_move, find_consolidation_base,
    check_volume_contraction, check_runner_state,
    grade_setup, detect_pattern_type,
)
import config as cfg

def diagnose(ticker: str):
    ticker = ticker.upper()
    print(f"\n{'='*60}")
    print(f"  DIAGNOSIS: {ticker}  —  {date.today()}")
    print(f"{'='*60}\n")

    # ── Fetch data ─────────────────────────────────────────────────────────────
    df = fetch_history(ticker, days=400)
    if df is None or len(df) < 30:
        print("ERROR: no data returned from yfinance — check ticker symbol")
        return

    df = compute_indicators(df)
    close = float(df["Close"].iloc[-1])
    print(f"  Last close : ${close:.2f}  ({df.index[-1].date()})")
    print(f"  Data rows  : {len(df)}\n")

    # ── Stage 1 ────────────────────────────────────────────────────────────────
    u = check_universe_filter(df, ticker)
    if u is None:
        last = df.iloc[-1]
        price     = float(last["Close"])
        vol       = float(last["avg_vol_20d"]) if last["avg_vol_20d"] > 0 else 0
        adr       = float(last["adr_pct"])     if last["adr_pct"] > 0 else 0
        print(f"FAIL  Stage 1 — Universe filter")
        print(f"  price=${price:.2f} (need >={cfg.MIN_PRICE})")
        print(f"  avg vol={vol:,.0f} (need >={cfg.MIN_AVG_VOLUME:,})")
        print(f"  ADR={adr:.1f}% (need >={cfg.MIN_ADR_PCT}%)")
        return
    print(f"PASS  Stage 1 — price=${u['current_price']:.2f}  "
          f"vol={u['avg_vol_20d']:,.0f}  ADR={u['adr_pct']:.1f}%")

    # ── Stage 2 ────────────────────────────────────────────────────────────────
    m = check_momentum_trend(df)
    price = u["current_price"]
    pct_1m  = (price - float(df["Close"].iloc[-20]))  / float(df["Close"].iloc[-20])  * 100 if len(df) >= 20  else None
    pct_3m  = (price - float(df["Close"].iloc[-60]))  / float(df["Close"].iloc[-60])  * 100 if len(df) >= 60  else None
    pct_6m  = (price - float(df["Close"].iloc[-120])) / float(df["Close"].iloc[-120]) * 100 if len(df) >= 120 else None
    high_52w = float(df["High"].tail(252).max())
    pct_52wh = (high_52w - price) / high_52w * 100

    if m is None:
        print(f"FAIL  Stage 2 — Momentum trend")
        print(f"  1M  = {pct_1m:+.1f}%  (need >= {cfg.MIN_MOMENTUM_1M_PCT}%)"  if pct_1m  is not None else "  1M  = N/A (insufficient history)")
        print(f"  3M  = {pct_3m:+.1f}%  (need >= {cfg.MIN_MOMENTUM_3M_PCT}%)"  if pct_3m  is not None else "  3M  = N/A")
        print(f"  6M  = {pct_6m:+.1f}%  (need >= {cfg.MIN_MOMENTUM_6M_PCT}%)"  if pct_6m  is not None else "  6M  = N/A")
        print(f"  52wH = {pct_52wh:.1f}% away (need <= {cfg.MAX_FROM_52W_HIGH}%)")
        return
    print(f"PASS  Stage 2 — 1M={m['pct_1m']:+.1f}%  3M={m['pct_3m']:+.1f}%  "
          f"6M={m['pct_6m']:+.1f}%  52wH={m['pct_from_52w_high']:.1f}% away")

    # ── Stage 2b ───────────────────────────────────────────────────────────────
    pm = find_prior_explosive_move(df)
    if pm:
        print(f"PASS  Stage 2b — prior move +{pm['move_pct']:.1f}% in "
              f"{pm['move_days']}d  (peak {pm['peak_date']})")
    else:
        print(f"MISS  Stage 2b — no prior explosive move found "
              f"(>={cfg.MIN_PRIOR_MOVE_PCT}% in {cfg.MAX_PRIOR_MOVE_DAYS}d with vol surge)")
        print(f"       → bonus only — stock still qualifies for Stage 3")

    # ── Stage 3 ────────────────────────────────────────────────────────────────
    if pm:
        base_anchor = pm["peak_date"]
    else:
        base_anchor = df["High"].tail(252).idxmax().date()
        cap = date.today() - timedelta(days=cfg.MIN_BASE_DAYS + 2)
        if base_anchor > cap:
            base_anchor = date.today() - timedelta(days=cfg.MAX_BASE_DAYS)

    base = find_consolidation_base(df, base_anchor)
    if base is None:
        print(f"FAIL  Stage 3 — no consolidation base  (anchor={base_anchor})")

        # Explain runner eligibility
        last     = df.iloc[-1]
        ma20     = float(last["ma20"])
        ma50     = float(last["ma50"])
        high_20d = float(df["High"].tail(20).max())
        pct_20dh = (high_20d - price) / high_20d * 100

        print(f"\n  Runner check:")
        print(f"    price > MA20?  ${price:.2f} > ${ma20:.2f} → {'YES' if price > ma20 else 'NO'}")
        print(f"    MA20 > MA50?   ${ma20:.2f} > ${ma50:.2f} → {'YES' if ma20 > ma50 else 'NO'}")
        print(f"    20d-high prox? {pct_20dh:.1f}% below ${high_20d:.2f} "
              f"(gate={cfg.MAX_RUNNER_FROM_20D_HIGH}%) → "
              f"{'PASS' if pct_20dh <= cfg.MAX_RUNNER_FROM_20D_HIGH else 'FAIL'}")
        print(f"    prior move?    {'YES' if pm else 'NO'}  "
              f"(required={cfg.RUNNER_REQUIRE_PRIOR_MOVE}) → "
              f"{'PASS' if (not cfg.RUNNER_REQUIRE_PRIOR_MOVE or pm) else 'FAIL'}")

        runner = check_runner_state(df, u, m, pm)
        print(f"\n  → {'RUNNER (in runner_entries)' if runner else 'NOT on watchlist or runner list'}")
        return

    print(f"PASS  Stage 3 — depth={base['base_depth_pct']:.1f}%  "
          f"dur={base['base_duration_days']}d  "
          f"pivot=${base['pivot_price']:.2f}")

    # ── Volume contraction (Stage 4 — bonus) ──────────────────────────────────
    vc = check_volume_contraction(df, base["base_start_date"])
    if vc:
        print(f"PASS  Stage 4 — vol contraction {vc['contraction_ratio']:.2f}x  "
              f"{vc['consecutive_low_vol_days']} consec quiet days  (grade bonus)")
    else:
        print(f"MISS  Stage 4 — no volume contraction  (grade bonus only, not a gate)")

    # ── Pivot proximity / watchlist trigger ───────────────────────────────────
    pivot    = base["pivot_price"]
    pct_away = (pivot - price) / pivot * 100

    pt    = detect_pattern_type(df, base)
    grade = grade_setup(pm, base, vc, pt, m)

    print(f"\n  Pattern : {pt}  |  Grade : {grade}")
    print(f"  Pivot   : ${pivot:.2f}  |  Price : ${price:.2f}  |  Distance : {pct_away:.1f}%")

    if pct_away < 0:
        print(f"\n  → ALREADY ABOVE PIVOT by {abs(pct_away):.1f}% — "
              f"broke out, no longer a setup trigger")
        print(f"     (would be in breakout_entries if vol/candle confirmed)")
    elif pct_away > cfg.MAX_DIST_FROM_PIVOT_PCT:
        print(f"\n  → TOO FAR from pivot ({pct_away:.1f}% > {cfg.MAX_DIST_FROM_PIVOT_PCT}% gate) "
              f"— not yet a watchlist trigger")
    else:
        print(f"\n  → ON WATCHLIST  {pct_away:.1f}% from pivot  "
              f"[{grade}] {pt}")

    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 diagnose_ticker.py <TICKER>")
        sys.exit(1)
    diagnose(sys.argv[1])
