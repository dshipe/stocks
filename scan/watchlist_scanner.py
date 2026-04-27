#!/usr/bin/env python3
"""
watchlist_scanner.py — Daily watchlist generator.

Run every weekday at 8:00 AM EST via cron.
Scans the full market universe for stocks meeting Qullamaggie setup criteria
(Stages 1–4) that are within 5% of their pivot (breakout level).

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
from datetime import date, datetime

import config as cfg
from shared.data_fetcher import (
    get_ticker_universe,
    fetch_history,
    compute_indicators,
)
from shared.criteria import (
    check_universe_filter,
    find_prior_explosive_move,
    find_consolidation_base,
    check_volume_contraction,
    detect_pattern_type,
    grade_setup,
    build_qualification_reasons,
)
from shared.db_writer import insert_watchlist_entry, test_connection

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

    # Stage 2: Prior explosive move
    prior_move = find_prior_explosive_move(df)
    if prior_move is None:
        return None

    # Stage 3: Consolidation base
    base = find_consolidation_base(df, prior_move["peak_date"])
    if base is None:
        return None

    # Stage 4: Volume contraction
    vol_contraction = check_volume_contraction(df, base["base_start_date"])
    if vol_contraction is None:
        return None

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
    grade        = grade_setup(prior_move, base, vol_contraction, pattern_type)

    # Build human-readable qualification reasons for the database
    reasons_json = build_qualification_reasons(
        prior_move, base, vol_contraction, pattern_type, grade
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
        "prior_move_pct":           prior_move["move_pct"],
        "prior_move_days":          prior_move["move_days"],
        "base_depth_pct":           base["base_depth_pct"],
        "base_duration_days":       base["base_duration_days"],
        "volume_contraction_ratio": vol_contraction["contraction_ratio"],
        "adr_pct":                  round(universe["adr_pct"], 2),
        "avg_daily_volume":         int(avg_vol_20d),
        "distance_to_pivot_pct":    round(pct_from_pivot, 2),
        "ma10_above_ma20":          base["ma10_above_ma20"],
        "above_50d_ma":             base["above_50d_ma"],
        "volume_contraction_days":  vol_contraction["consecutive_low_vol_days"],
        "qualification_reasons":    reasons_json,
        "pattern_type":             pattern_type,
        "pattern_grade":            grade,
        # Extra for display (not in DB schema)
        "_stop_price":              stop_price,
        "_risk_per_share":          risk_per_share,
    }


def run_scan(tickers: list[str], dry_run: bool = False) -> list[dict]:
    """Scan all tickers and return the watchlist."""
    watchlist  = []
    total      = len(tickers)
    passed_s1  = passed_s2 = passed_s3 = passed_s4 = 0
    errors     = 0

    print(f"\n{'='*65}")
    print(f"  DAILY WATCHLIST SCAN — {date.today()}")
    print(f"  Universe: {total} tickers | Dry run: {dry_run}")
    print(f"{'='*65}\n")

    for i, ticker in enumerate(tickers, 1):
        if i % 50 == 0 or i == 1:
            logger.info(f"Progress: {i}/{total} ({watchlist.__len__()} on watchlist so far)")

        try:
            df = fetch_history(ticker, days=365)
            if df is None:
                continue
            df = compute_indicators(df)

            # Stage 1
            universe = check_universe_filter(df, ticker)
            if universe is None:
                continue
            passed_s1 += 1

            # Stage 2
            prior_move = find_prior_explosive_move(df)
            if prior_move is None:
                continue
            passed_s2 += 1

            # Stage 3
            base = find_consolidation_base(df, prior_move["peak_date"])
            if base is None:
                continue
            passed_s3 += 1

            # Stage 4
            vol_contraction = check_volume_contraction(df, base["base_start_date"])
            if vol_contraction is None:
                continue
            passed_s4 += 1

            # Proximity to pivot
            current_price  = universe["current_price"]
            pivot_price    = base["pivot_price"]
            if pivot_price <= 0:
                continue
            pct_from_pivot = ((pivot_price - current_price) / pivot_price) * 100
            if pct_from_pivot < 0 or pct_from_pivot > cfg.MAX_DIST_FROM_PIVOT_PCT:
                continue

            pattern_type = detect_pattern_type(df, base)
            grade        = grade_setup(prior_move, base, vol_contraction, pattern_type)
            reasons_json = build_qualification_reasons(
                prior_move, base, vol_contraction, pattern_type, grade
            )

            last        = df.iloc[-1]
            avg_vol_20d = float(last["avg_vol_20d"]) if last["avg_vol_20d"] > 0 else 0
            stop_price  = round(base["base_low"] * 0.995, 4)

            entry = {
                "scan_date":                date.today(),
                "ticker":                   ticker,
                "price_at_scan":            round(current_price, 4),
                "pivot_price":              pivot_price,
                "pct_from_pivot":           round(pct_from_pivot, 2),
                "prior_move_pct":           prior_move["move_pct"],
                "prior_move_days":          prior_move["move_days"],
                "base_depth_pct":           base["base_depth_pct"],
                "base_duration_days":       base["base_duration_days"],
                "volume_contraction_ratio": vol_contraction["contraction_ratio"],
                "adr_pct":                  round(universe["adr_pct"], 2),
                "avg_daily_volume":         int(avg_vol_20d),
                "distance_to_pivot_pct":    round(pct_from_pivot, 2),
                "ma10_above_ma20":          base["ma10_above_ma20"],
                "above_50d_ma":             base["above_50d_ma"],
                "volume_contraction_days":  vol_contraction["consecutive_low_vol_days"],
                "qualification_reasons":    reasons_json,
                "pattern_type":             pattern_type,
                "pattern_grade":            grade,
                "_stop_price":              stop_price,
            }
            watchlist.append(entry)

        except Exception as e:
            errors += 1
            logger.debug(f"Error scanning {ticker}: {e}")

    return watchlist, {
        "total": total, "passed_s1": passed_s1, "passed_s2": passed_s2,
        "passed_s3": passed_s3, "passed_s4": passed_s4,
        "watchlist": len(watchlist), "errors": errors,
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
    print(f"  Passed Stage 1 filter : {stats['passed_s1']}")
    print(f"  Passed Stage 2 (move) : {stats['passed_s2']}")
    print(f"  Passed Stage 3 (base) : {stats['passed_s3']}")
    print(f"  Passed Stage 4 (vol)  : {stats['passed_s4']}")
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


if __name__ == "__main__":
    main()
