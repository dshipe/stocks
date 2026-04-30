#!/usr/bin/env python3
"""
watchlist_scanner.py — Daily watchlist generator.

Run every weekday at 8:00 AM EST via cron.
Scans the full market universe for stocks meeting Qullamaggie setup criteria
that are within 8% of their pivot (breakout level).

Stage flow (as of 2026-04-29):
    Stage 1  — Universe filter (price, volume, ADR%)
    Stage 2  — Momentum trend: up ≥10%/20%/30% over 1M/3M/6M (NEVER AGES OUT)
    Stage 2b — Prior explosive move: bonus grading only, not a gate
    Stage 3  — Consolidation base (5–40 days, tight depth)
    Stage 4  — Volume contraction: bonus grading only, not a gate (demoted 2026-04-29)
    Trigger  — Within 8% of pivot

Results are written to SQL Server: watchlist_entries table.

Usage:
    python watchlist_scanner.py
    python watchlist_scanner.py --dry-run       # print results, don't write to DB
    python watchlist_scanner.py --ticker AAPL   # scan a single ticker
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import config as cfg
from shared.data_fetcher import (
    get_ticker_universe,
    fetch_history,
    bulk_fetch_history,
    compute_indicators,
)
from shared.criteria import (
    check_universe_filter,
    check_momentum_trend,
    find_prior_explosive_move,
    find_consolidation_base,
    check_volume_contraction,
    detect_pattern_type,
    grade_setup,
    build_qualification_reasons,
)
from shared.db_writer import insert_watchlist_entry, test_connection
from shared.telegram_notify import send_watchlist_summary

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Main Scanner ──────────────────────────────────────────────────────────────

def scan_ticker(ticker: str) -> dict | None:
    """
    Run full Qullamaggie Stage 1–4 criteria against a single ticker.

    Returns a result dict if the stock makes the watchlist, else None.
    """
    # Fetch daily history
    df = fetch_history(ticker, days=365)
    if df is None:
        return None

    # Compute technical indicators
    df = compute_indicators(df)

    # Stage 1: Universe filter (price, volume, ADR%)
    universe = check_universe_filter(df, ticker)
    if universe is None:
        return None

    # Stage 2: Momentum trend filter (never ages out)
    momentum = check_momentum_trend(df)
    if momentum is None:
        return None

    # Stage 2b: Prior explosive move (bonus grading — not a gate)
    prior_move = find_prior_explosive_move(df)

    # Stage 3: Consolidation base
    # Anchor from prior_move peak if found; otherwise use the recent 52w high date
    if prior_move:
        base_anchor = prior_move["peak_date"]
    else:
        import pandas as _pd
        high_idx    = df["High"].tail(252).idxmax()
        base_anchor = high_idx.date()
        # Cap so there are at least MIN_BASE_DAYS trading days of data after it
        from datetime import date as _date, timedelta as _td
        cap = (_date.today() - _td(days=cfg.MIN_BASE_DAYS + 2))
        if base_anchor > cap:
            base_anchor = (_date.today() - _td(days=cfg.MAX_BASE_DAYS))
    base = find_consolidation_base(df, base_anchor)
    if base is None:
        return None

    # Stage 4: Volume contraction (bonus grading — not a gate)
    vol_contraction = check_volume_contraction(df, base["base_start_date"])
    # None is OK — no contraction bonus but stock still qualifies

    # Watchlist trigger: is the stock within MAX_DIST_FROM_PIVOT_PCT of the pivot?
    current_price = universe["current_price"]
    pivot_price   = base["pivot_price"]
    if pivot_price <= 0:
        return None

    pct_from_pivot = ((pivot_price - current_price) / pivot_price) * 100
    if pct_from_pivot < 0 or pct_from_pivot > cfg.MAX_DIST_FROM_PIVOT_PCT:
        # Either already above pivot (already broke out) or too far away
        return None

    # Determine pattern type and grade
    pattern_type = detect_pattern_type(df, base)
    grade        = grade_setup(prior_move, base, vol_contraction, pattern_type, momentum)

    # Build human-readable qualification reasons for the database
    reasons_json = build_qualification_reasons(
        prior_move, base, vol_contraction, pattern_type, grade, momentum
    )

    # Compute suggested stop and R/R
    stop_price     = round(base["base_low"] * 0.995, 4)  # 0.5% below base low
    risk_per_share = round(current_price - stop_price, 4)
    last           = df.iloc[-1]
    avg_vol_20d    = float(last["avg_vol_20d"]) if last["avg_vol_20d"] > 0 else 0

    return {
        "scan_date":                date.today(),
        "ticker":                   ticker,
        "price_at_scan":            round(current_price, 4),
        "pivot_price":              pivot_price,
        "pct_from_pivot":           round(pct_from_pivot, 2),
        "prior_move_pct":           prior_move["move_pct"] if prior_move else 0,
        "prior_move_days":          prior_move["move_days"] if prior_move else 0,
        "base_depth_pct":           base["base_depth_pct"],
        "base_duration_days":       base["base_duration_days"],
        "volume_contraction_ratio": vol_contraction["contraction_ratio"] if vol_contraction else 0,
        "adr_pct":                  round(universe["adr_pct"], 2),
        "avg_daily_volume":         int(avg_vol_20d),
        "distance_to_pivot_pct":    round(pct_from_pivot, 2),
        "ma10_above_ma20":          base["ma10_above_ma20"],
        "above_50d_ma":             base["above_50d_ma"],
        "volume_contraction_days":  vol_contraction["consecutive_low_vol_days"] if vol_contraction else 0,
        "qualification_reasons":    reasons_json,
        "pattern_type":             pattern_type,
        "pattern_grade":            grade,
        # Extra for display (not in DB schema)
        "_stop_price":              stop_price,
        "_risk_per_share":          risk_per_share,
    }


# Number of parallel workers for criteria evaluation (CPU-light, pandas-heavy).
_EVAL_WORKERS = 16


def run_scan(tickers: list[str], dry_run: bool = False) -> tuple[list[dict], dict]:
    """Scan all tickers and return the watchlist."""
    total = len(tickers)

    print(f"\n{'='*65}")
    print(f"  DAILY WATCHLIST SCAN — {date.today()}")
    print(f"  Universe: {total} tickers | Dry run: {dry_run}")
    print(f"{'='*65}\n")

    # ── Step 1: Bulk-fetch all historical data ─────────────────────────────────────
    t0 = datetime.now()
    logger.info(f"Bulk-fetching historical data for {total} tickers…")
    histories = bulk_fetch_history(tickers, days=365)
    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(f"Data fetch done: {len(histories)}/{total} tickers in {elapsed:.1f}s")

    # ── Step 2: Parallel criteria evaluation ─────────────────────────────────────
    watchlist = []
    counters  = {"s1": 0, "s2": 0, "s2b": 0, "s3": 0, "s4": 0, "errors": 0}
    lock      = threading.Lock()

    def _eval(ticker: str) -> dict | None:
        """Evaluate one ticker against all stages. Returns entry dict or None."""
        df_raw = histories.get(ticker)
        if df_raw is None:
            return None
        try:
            df = compute_indicators(df_raw)

            # Stage 1
            universe = check_universe_filter(df, ticker)
            if universe is None:
                return None
            with lock: counters["s1"] += 1

            # Stage 2: Momentum trend
            momentum = check_momentum_trend(df)
            if momentum is None:
                return None
            with lock: counters["s2"] += 1

            # Stage 2b: Prior explosive move (bonus — not a gate)
            prior_move = find_prior_explosive_move(df)
            if prior_move:
                with lock: counters["s2b"] += 1
                base_anchor = prior_move["peak_date"]
            else:
                high_idx    = df["High"].tail(252).idxmax()
                base_anchor = high_idx.date()
                cap = date.today() - timedelta(days=cfg.MIN_BASE_DAYS + 2)
                if base_anchor > cap:
                    base_anchor = date.today() - timedelta(days=cfg.MAX_BASE_DAYS)

            # Stage 3
            base = find_consolidation_base(df, base_anchor)
            if base is None:
                return None
            with lock: counters["s3"] += 1

            # Stage 4: Volume contraction (bonus — not a gate)
            vol_contraction = check_volume_contraction(df, base["base_start_date"])
            if vol_contraction:
                with lock: counters["s4"] += 1

            # Proximity to pivot
            current_price  = universe["current_price"]
            pivot_price    = base["pivot_price"]
            if pivot_price <= 0:
                return None
            pct_from_pivot = ((pivot_price - current_price) / pivot_price) * 100
            if pct_from_pivot < 0 or pct_from_pivot > cfg.MAX_DIST_FROM_PIVOT_PCT:
                return None

            pattern_type = detect_pattern_type(df, base)
            grade        = grade_setup(prior_move, base, vol_contraction, pattern_type, momentum)
            reasons_json = build_qualification_reasons(
                prior_move, base, vol_contraction, pattern_type, grade, momentum
            )

            last        = df.iloc[-1]
            avg_vol_20d = float(last["avg_vol_20d"]) if last["avg_vol_20d"] > 0 else 0
            stop_price  = round(base["base_low"] * 0.995, 4)

            return {
                "scan_date":                date.today(),
                "ticker":                   ticker,
                "price_at_scan":            round(current_price, 4),
                "pivot_price":              pivot_price,
                "pct_from_pivot":           round(pct_from_pivot, 2),
                "prior_move_pct":           prior_move["move_pct"] if prior_move else 0,
                "prior_move_days":          prior_move["move_days"] if prior_move else 0,
                "base_depth_pct":           base["base_depth_pct"],
                "base_duration_days":       base["base_duration_days"],
                "volume_contraction_ratio": vol_contraction["contraction_ratio"] if vol_contraction else 0,
                "adr_pct":                  round(universe["adr_pct"], 2),
                "avg_daily_volume":         int(avg_vol_20d),
                "distance_to_pivot_pct":    round(pct_from_pivot, 2),
                "ma10_above_ma20":          base["ma10_above_ma20"],
                "above_50d_ma":             base["above_50d_ma"],
                "volume_contraction_days":  vol_contraction["consecutive_low_vol_days"] if vol_contraction else 0,
                "qualification_reasons":    reasons_json,
                "pattern_type":             pattern_type,
                "pattern_grade":            grade,
                "_stop_price":              stop_price,
            }
        except Exception as e:
            with lock: counters["errors"] += 1
            logger.debug(f"Error scanning {ticker}: {e}")
            return None

    done = 0
    with ThreadPoolExecutor(max_workers=_EVAL_WORKERS) as executor:
        futures = {executor.submit(_eval, t): t for t in histories}
        for future in as_completed(futures):
            done += 1
            if done % 200 == 0:
                logger.info(f"Criteria eval: {done}/{len(histories)} ({len(watchlist)} on watchlist)")
            result = future.result()
            if result:
                watchlist.append(result)

    return watchlist, {
        "total":      total,
        "fetched":    len(histories),
        "passed_s1":  counters["s1"],
        "passed_s2":  counters["s2"],
        "passed_s2b": counters["s2b"],
        "passed_s3":  counters["s3"],
        "passed_s4":  counters["s4"],
        "watchlist":  len(watchlist),
        "errors":     counters["errors"],
    }


def print_watchlist(watchlist: list[dict]) -> None:
    """Print a formatted watchlist summary table."""
    if not watchlist:
        print("  No stocks met watchlist criteria today.\n")
        return

    # Sort by grade then % from pivot
    grade_order = {"A+": 0, "A": 1, "B": 2, "C": 3}
    watchlist = sorted(
        watchlist,
        key=lambda x: (grade_order.get(x["pattern_grade"], 9), x["pct_from_pivot"])
    )

    print(f"\n{'─'*95}")
    print(f"  {'Ticker':<8} {'Grade':<6} {'Price':>8} {'Pivot':>8} {'%Away':>6}  {'Pattern':<12} {'Prior Move':<12} Top Reason")
    print(f"{'─'*95}")

    for e in watchlist:
        reasons = json.loads(e["qualification_reasons"]) if e["qualification_reasons"] else []
        top_reason = reasons[0] if reasons else ""
        print(
            f"  {e['ticker']:<8} {e['pattern_grade']:<6} "
            f"${e['price_at_scan']:>7.2f} ${e['pivot_price']:>7.2f} "
            f"{e['pct_from_pivot']:>5.1f}%  "
            f"{e['pattern_type']:<12} "
            f"+{e['prior_move_pct']:.0f}%/{e['prior_move_days']}d{'':<3} "
            f"{top_reason[:45]}"
        )

    print(f"{'─'*95}\n")


def main():
    parser = argparse.ArgumentParser(description="Daily Qullamaggie watchlist scanner")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to DB")
    parser.add_argument("--ticker",  type=str, default=None, help="Scan a single ticker only")
    args = parser.parse_args()

    # Verify DB connection unless dry-run
    if not args.dry_run:
        if not test_connection():
            logger.error("Cannot connect to SQL Server. Use --dry-run to test without DB.")
            sys.exit(1)

    # Build ticker list
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = get_ticker_universe()

    # Run scan
    watchlist, stats = run_scan(tickers, dry_run=args.dry_run)

    # Print summary
    print(f"\n  SCAN SUMMARY")
    print(f"  {'─'*40}")
    print(f"  Total tickers scanned : {stats['total']}")
    print(f"  Data fetched          : {stats.get('fetched', stats['total'])}")
    print(f"  Passed Stage 1 filter : {stats['passed_s1']}")
    print(f"  Passed Stage 2 (momentum) : {stats['passed_s2']}")
    print(f"  + also had prior move (2b): {stats['passed_s2b']}")
    print(f"  Passed Stage 3 (base)     : {stats['passed_s3']}")
    print(f"  Had vol contraction (4)   : {stats['passed_s4']} (bonus — not a gate)")
    print(f"  On watchlist today    : {stats['watchlist']}")
    print(f"  Errors (skipped)      : {stats['errors']}")

    print_watchlist(watchlist)

    # Write to DB
    if not args.dry_run and watchlist:
        written = 0
        for entry in watchlist:
            db_entry = {k: v for k, v in entry.items() if not k.startswith("_")}
            row_id = insert_watchlist_entry(db_entry)
            if row_id:
                written += 1
            else:
                logger.warning(f"Failed to write {entry['ticker']} to DB")
        print(f"  Written to DB: {written}/{len(watchlist)} entries\n")
    elif args.dry_run:
        print("  [DRY RUN] No data written to database.\n")

    # Send Telegram notification (always, even on dry-run)
    if not args.ticker:  # skip single-ticker test runs
        tg_stats = {
            "total":  stats["total"],
            "stage1": stats["passed_s1"],
            "stage2": stats["passed_s2"],
            "stage3": stats["passed_s3"],
            "stage4": stats["passed_s4"],
        }
        from datetime import date as _date
        sent = send_watchlist_summary(
            scan_date=str(_date.today()),
            results=watchlist,
            stats=tg_stats,
        )
        if sent:
            logger.info("Telegram notification sent")
        else:
            logger.warning("Telegram notification failed")


if __name__ == "__main__":
    main()
