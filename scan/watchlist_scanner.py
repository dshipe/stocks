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
import importlib.util
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
    check_runner_state,
    find_prior_explosive_move,
    find_consolidation_base,
    check_volume_contraction,
    detect_pattern_type,
    grade_setup,
    build_qualification_reasons,
)
from shared.db_writer import insert_watchlist_entry, insert_runner_entry, test_connection
from shared.telegram_notify import send_watchlist_summary, send_runners_summary

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
        """Evaluate one ticker against all stages. Returns entry dict or None.
        
        Returns a dict with key '_type' = 'watchlist' or 'runner'.
        """
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
                # Not consolidating yet — check if it's a runner
                runner = check_runner_state(df, universe, momentum, prior_move)
                if runner is None:
                    return None
                last        = df.iloc[-1]
                avg_vol_20d = float(last["avg_vol_20d"]) if last["avg_vol_20d"] > 0 else 0
                return {
                    "_type":            "runner",
                    "scan_date":        date.today(),
                    "ticker":           ticker,
                    "price_at_scan":    round(universe["current_price"], 4),
                    "pct_1m":           runner["pct_1m"],
                    "pct_3m":           runner["pct_3m"],
                    "pct_6m":           runner["pct_6m"],
                    "pct_from_52w_high":runner["pct_from_52w_high"],
                    "pct_from_20d_high":runner["pct_from_20d_high"],
                    "prior_move_pct":   prior_move["move_pct"] if prior_move else 0,
                    "prior_move_days":  prior_move["move_days"] if prior_move else 0,
                    "adr_pct":          round(universe["adr_pct"], 2),
                    "avg_daily_volume": int(avg_vol_20d),
                }
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
                "_type":                    "watchlist",
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

    runners = []
    done    = 0
    with ThreadPoolExecutor(max_workers=_EVAL_WORKERS) as executor:
        futures = {executor.submit(_eval, t): t for t in histories}
        for future in as_completed(futures):
            done += 1
            if done % 200 == 0:
                logger.info(
                    f"Criteria eval: {done}/{len(histories)} "
                    f"({len(watchlist)} on watchlist, {len(runners)} runners)"
                )
            result = future.result()
            if result:
                if result.get("_type") == "runner":
                    runners.append(result)
                else:
                    watchlist.append(result)

    return watchlist, runners, {
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
    parser.add_argument("--dry-run",     action="store_true", help="Print results without writing to DB")
    parser.add_argument("--ticker",      type=str, default=None, help="Scan a single ticker only")
    parser.add_argument("--schwab-only", action="store_true",
                        help=(
                            "Skip the yfinance fetch and scan entirely. "
                            "Reads existing records from the DB and pushes them to Schwab watchlists. "
                            "Useful for re-syncing after the scan has already run."
                        ))
    args = parser.parse_args()

    # ── --schwab-only: skip scan, go straight to Schwab sync ──────────────────
    if args.schwab_only:
        if not test_connection():
            logger.error("Cannot connect to SQL Server.")
            sys.exit(1)
        try:
            # Import directly from schwab_scripts/ to avoid conflicts with installed schwab package
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "schwab_watchlist_sync",
                os.path.join(os.path.dirname(__file__), "schwab_scripts", "schwab_watchlist_sync.py")
            )
            sync_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sync_mod)
            result = sync_mod.sync_watchlists()
            if result["scan_date"]:
                print(f"\n  Schwab sync complete — {result['scan_date']}")
                print(f"  {result['watch_name']}: {result['watch_count']} tickers")
                print(f"  {result['runners_name']}: {result['runners_count']} tickers\n")
            else:
                logger.warning("No scan records found in DB — nothing synced.")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Schwab sync failed: {e}")
            sys.exit(1)
        return

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
    watchlist, runners, stats = run_scan(tickers, dry_run=args.dry_run)

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

    # Print runners
    if runners:
        runners_sorted = sorted(runners, key=lambda x: -x.get("pct_3m", 0))
        print(f"\n  RUNNERS (Stage 1+2 \u2705 — no base yet, still marking up)")
        print(f"  {'\u2500'*87}")
        print(f"  {'Ticker':<8} {'Price':>9} {'1M':>7} {'3M':>7} {'6M':>7} {'52wH%':>6}  Prior Move")
        print(f"  {'\u2500'*87}")
        for r in runners_sorted:
            mv = f"+{r['prior_move_pct']:.0f}%/{r['prior_move_days']}d" if r.get('prior_move_pct') else "—"
            print(
                f"  {r['ticker']:<8} ${r['price_at_scan']:>8.2f} "
                f"{r['pct_1m']:>+6.1f}% {r['pct_3m']:>+6.1f}% {r['pct_6m']:>+6.1f}%  "
                f"-{r['pct_from_52w_high']:>4.1f}%  {mv}"
            )
        print(f"  {'\u2500'*87}")
        print(f"  {len(runners)} runners identified \u2014 monitor for base formation\n")
    else:
        print("  No runners today.\n")

    # Write to DB
    if not args.dry_run:
        if watchlist:
            written = 0
            for entry in watchlist:
                db_entry = {k: v for k, v in entry.items() if not k.startswith("_")}
                row_id = insert_watchlist_entry(db_entry)
                if row_id:
                    written += 1
                else:
                    logger.warning(f"Failed to write {entry['ticker']} to DB")
            print(f"  Written to DB: {written}/{len(watchlist)} watchlist entries")
        if runners:
            written_r = 0
            for r in runners:
                db_entry = {k: v for k, v in r.items() if not k.startswith("_")}
                row_id = insert_runner_entry(db_entry)
                if row_id:
                    written_r += 1
            print(f"  Written to DB: {written_r}/{len(runners)} runner entries\n")
    else:
        print("  [DRY RUN] No data written to database.\n")

    # ── Schwab watchlist sync ──────────────────────────────────────────────────
    if not args.dry_run and not args.ticker:
        try:
            # Import directly from schwab_scripts/ to avoid conflicts with installed schwab package
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "schwab_watchlist_sync",
                os.path.join(os.path.dirname(__file__), "schwab_scripts", "schwab_watchlist_sync.py")
            )
            sync_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sync_mod)
            wl_result = sync_mod.sync_watchlists()
            logger.info(
                f"Schwab watchlists created: "
                f"{wl_result['watch_name']} ({wl_result['watch_count']} tickers), "
                f"{wl_result['runners_name']} ({wl_result['runners_count']} tickers)"
            )
        except Exception as e:
            logger.warning(f"Schwab watchlist sync failed (non-fatal): {e}")

    # Send Telegram notifications (always, even on dry-run)
    if not args.ticker:  # skip single-ticker test runs
        tg_stats = {
            "total":  stats["total"],
            "stage1": stats["passed_s1"],
            "stage2": stats["passed_s2"],
            "stage3": stats["passed_s3"],
            "stage4": stats["passed_s4"],
        }
        from datetime import date as _date
        scan_date_str = str(_date.today())

        # Only notify A and A+ grade setups via Telegram
        tg_watchlist = [e for e in watchlist if e.get("pattern_grade") in ("A+", "A")]

        sent = send_watchlist_summary(
            scan_date=scan_date_str,
            results=tg_watchlist,
            stats=tg_stats,
        )
        if sent:
            logger.info("Telegram watchlist notification sent")
        else:
            logger.warning("Telegram watchlist notification failed")
        if runners:
            sent_r = send_runners_summary(scan_date=scan_date_str, runners=runners)
            if sent_r:
                logger.info("Telegram runners notification sent")
            else:
                logger.warning("Telegram runners notification failed")


if __name__ == "__main__":
    main()
