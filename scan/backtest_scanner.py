#!/usr/bin/env python3
"""
backtest_scanner.py -- Historical backtest of the Qullamaggie watchlist criteria.

For each trading day in the backtest window, re-evaluates Stage 1-4 criteria
against ONLY data available up to that date (point-in-time simulation).
Measures 1d/5d/10d/20d forward returns for every qualifying entry.

Survivorship bias caveat: uses the CURRENT ticker universe -- stocks that
delisted during the backtest period are absent, which slightly flatters results.

Usage:
    python backtest_scanner.py                          # 1 year, S&P 500
    python backtest_scanner.py --years 2               # 2 years
    python backtest_scanner.py --universe full         # full Nasdaq (~3,500 tickers, slow)
    python backtest_scanner.py --output bt_results.csv # custom output file
    python backtest_scanner.py --years 1 --workers 32  # more parallelism
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import csv
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import config as cfg
from shared.data_fetcher import (
    get_ticker_universe,
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
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_trading_days(start: date, end: date) -> list[date]:
    return [d.date() for d in pd.bdate_range(start=start, end=end)]


def pct_change(entry_price: float, current) -> float | None:
    if current is not None and entry_price > 0:
        return round((current - entry_price) / entry_price * 100, 2)
    return None


def fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "    --  "
    return f"{v:>+.1f}%"


# ── Per-ticker backtest ───────────────────────────────────────────────────────

def backtest_ticker(
    ticker: str,
    df_raw: pd.DataFrame,
    trading_days: list[date],
    stage_counters: dict,
    lock: threading.Lock,
) -> list[dict]:
    """
    Run Stage 1-4 criteria for one ticker across all backtest dates.
    Computes indicators once on full history, then slices for each date.
    Returns a list of virtual watchlist entries that qualified.
    """
    try:
        df_full = compute_indicators(df_raw)
    except Exception as e:
        logger.debug(f"compute_indicators({ticker}): {e}")
        return []

    results = []

    for d in trading_days:
        # Point-in-time slice: only bars on or before date d
        df = df_full[df_full.index.date <= d]

        # Need at least 130 bars for Stage 2 (120 for 6M momentum + warmup)
        if len(df) < 130:
            continue

        # Stage 1: Universe filter
        universe = check_universe_filter(df, ticker)
        if universe is None:
            continue
        with lock:
            stage_counters["s1"] += 1

        # Stage 2: Momentum trend
        momentum = check_momentum_trend(df)
        if momentum is None:
            continue
        with lock:
            stage_counters["s2"] += 1

        # Stage 2b: Prior explosive move (bonus grading only)
        prior_move = find_prior_explosive_move(df)
        if prior_move:
            with lock:
                stage_counters["s2b"] += 1

        # Stage 3: Consolidation base
        if prior_move:
            anchor = prior_move["peak_date"]
        else:
            high_idx = df["High"].tail(252).idxmax()
            anchor   = high_idx.date()
            cap      = d - timedelta(days=cfg.MIN_BASE_DAYS + 2)
            if anchor > cap:
                anchor = d - timedelta(days=cfg.MAX_BASE_DAYS)

        base = find_consolidation_base(df, anchor)
        if base is None:
            continue
        with lock:
            stage_counters["s3"] += 1

        # Stage 4: Volume contraction (bonus grading only)
        vol_contraction = check_volume_contraction(df, base["base_start_date"])
        if vol_contraction:
            with lock:
                stage_counters["s4"] += 1

        # Watchlist trigger: within MAX_DIST_FROM_PIVOT_PCT of pivot
        current_price = universe["current_price"]
        pivot         = base["pivot_price"]
        if pivot <= 0:
            continue

        pct_from_pivot = ((pivot - current_price) / pivot) * 100
        if pct_from_pivot < 0 or pct_from_pivot > cfg.MAX_DIST_FROM_PIVOT_PCT:
            continue

        with lock:
            stage_counters["trigger"] += 1

        pattern = detect_pattern_type(df, base)
        grade   = grade_setup(prior_move, base, vol_contraction, pattern, momentum)

        results.append({
            "scan_date":             d,
            "ticker":                ticker,
            "grade":                 grade,
            "pattern":               pattern,
            "price_at_scan":         round(current_price, 4),
            "pivot_price":           round(pivot, 4),
            "pct_from_pivot":        round(pct_from_pivot, 2),
            "base_depth_pct":        base["base_depth_pct"],
            "base_duration_days":    base["base_duration_days"],
            "vol_contraction_ratio": vol_contraction["contraction_ratio"] if vol_contraction else None,
            "prior_move_pct":        prior_move["move_pct"] if prior_move else None,
            "prior_move_days":       prior_move["move_days"] if prior_move else None,
            "pct_1m":                momentum["pct_1m"],
            "pct_3m":                momentum["pct_3m"],
            "pct_6m":                momentum["pct_6m"],
            "pct_from_52w_high":     momentum["pct_from_52w_high"],
        })

    return results


# ── Forward return measurement ────────────────────────────────────────────────

def add_forward_returns(entry: dict, df_ind: pd.DataFrame) -> dict:
    """Attach 1d/5d/10d/20d forward returns. Uses only data after scan_date."""
    d     = entry["scan_date"]
    price = entry["price_at_scan"]
    pivot = entry["pivot_price"]

    df_fwd = df_ind[df_ind.index.date > d]

    def close_at(n: int):
        return float(df_fwd["Close"].iloc[n - 1]) if len(df_fwd) >= n else None

    p1, p5, p10, p20 = close_at(1), close_at(5), close_at(10), close_at(20)

    did_break_out = (
        bool(df_fwd.head(5)["Close"].max() > pivot)
        if len(df_fwd) >= 1 else False
    )

    max_gain_pct = None
    if len(df_fwd) >= 1:
        best         = float(df_fwd.head(20)["Close"].max())
        max_gain_pct = pct_change(price, best)

    return {
        **entry,
        "pct_1d":        pct_change(price, p1),
        "pct_5d":        pct_change(price, p5),
        "pct_10d":       pct_change(price, p10),
        "pct_20d":       pct_change(price, p20),
        "max_gain_pct":  max_gain_pct,
        "did_break_out": did_break_out,
    }


# ── Summary printing ──────────────────────────────────────────────────────────

def print_summary(results: list[dict], start: date, end: date, years: float) -> None:
    if not results:
        print("\n  No entries qualified during the backtest window.")
        return

    df      = pd.DataFrame(results)
    has_10d = df["pct_10d"].notna().any()
    has_20d = df["pct_20d"].notna().any()

    print(f"\n{'='*65}")
    print(f"  BACKTEST RESULTS  {start} to {end}  ({years:.1f} yr)")
    print(f"  Unique tickers : {df['ticker'].nunique()}")
    print(f"  Total entries  : {len(df)}")
    print(f"{'='*65}")

    # By grade
    print(f"\n  {'Grade':<5} {'N':>5}  {'Avg5d':>7}  {'Avg10d':>8}  {'Avg20d':>8}  {'MaxGain':>8}  {'BO%':>5}")
    print("  " + "-" * 58)
    for grade in ["A+", "A", "B", "C"]:
        sub = df[df["grade"] == grade]
        if sub.empty:
            continue
        n   = len(sub)
        a5  = sub["pct_5d"].mean()
        a10 = sub["pct_10d"].mean() if has_10d else None
        a20 = sub["pct_20d"].mean() if has_20d else None
        amg = sub["max_gain_pct"].mean()
        bo  = sub["did_break_out"].mean() * 100
        print(f"  {grade:<5} {n:>5}  {fmt(a5):>8}  {fmt(a10):>9}  {fmt(a20):>9}  {fmt(amg):>9}  {bo:>4.0f}%")

    # By pattern
    print(f"\n  {'Pattern':<12} {'N':>5}  {'Avg5d':>7}  {'Avg10d':>8}  {'Avg20d':>8}  {'BO%':>5}")
    print("  " + "-" * 52)
    for pt in sorted(df["pattern"].unique()):
        sub = df[df["pattern"] == pt]
        if len(sub) < 3:
            continue
        n   = len(sub)
        a5  = sub["pct_5d"].mean()
        a10 = sub["pct_10d"].mean() if has_10d else None
        a20 = sub["pct_20d"].mean() if has_20d else None
        bo  = sub["did_break_out"].mean() * 100
        print(f"  {pt:<12} {n:>5}  {fmt(a5):>8}  {fmt(a10):>9}  {fmt(a20):>9}  {bo:>4.0f}%")

    # By quarter
    df["quarter"] = df["scan_date"].apply(
        lambda d: f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    )
    quarters = sorted(df["quarter"].unique())
    if len(quarters) > 1:
        print(f"\n  {'Quarter':<10} {'N':>5}  {'Avg5d':>7}  {'Avg10d':>8}  {'BO%':>5}")
        print("  " + "-" * 40)
        for q in quarters:
            sub = df[df["quarter"] == q]
            n   = len(sub)
            a5  = sub["pct_5d"].mean()
            a10 = sub["pct_10d"].mean() if has_10d else None
            bo  = sub["did_break_out"].mean() * 100
            print(f"  {q:<10} {n:>5}  {fmt(a5):>8}  {fmt(a10):>9}  {bo:>4.0f}%")

    # Overall
    print(f"\n  Overall avg 5d   : {fmt(df['pct_5d'].mean())}")
    if has_10d:
        print(f"  Overall avg 10d  : {fmt(df['pct_10d'].mean())}")
    if has_20d:
        print(f"  Overall avg 20d  : {fmt(df['pct_20d'].mean())}")
    print(f"  Overall BO rate  : {df['did_break_out'].mean()*100:.0f}%")
    print(f"  Overall max gain : {fmt(df['max_gain_pct'].mean())}")
    print()


# ── CSV save ──────────────────────────────────────────────────────────────────

def save_csv(results: list[dict], path: str) -> None:
    if not results:
        logger.warning("save_csv: no results to write")
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fieldnames = list(results[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"  Saved {len(results)} rows to: {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backtest the Qullamaggie watchlist scanner")
    parser.add_argument("--years",    type=float, default=1.0,
                        help="Years to backtest (default: 1.0)")
    parser.add_argument("--universe", choices=["sp500", "full"], default="sp500",
                        help="sp500 (~500 tickers, fast) or full Nasdaq (~3500, slow). Default: sp500")
    parser.add_argument("--output",   type=str,   default=None,
                        help="CSV output path (default: backtest_YYYYMMDD.csv in workspace)")
    parser.add_argument("--workers",  type=int,   default=16,
                        help="Parallel workers (default: 16)")
    parser.add_argument("--min-grade", choices=["A+", "A", "B", "C"], default=None,
                        help="Only include this grade or better in the CSV output")
    args = parser.parse_args()

    # ── Date range ────────────────────────────────────────────────────────────
    end_date   = date.today() - timedelta(days=28)   # leave room for 20d forward data
    start_date = date.today() - timedelta(days=int(args.years * 365))
    fetch_days = int(args.years * 365) + 400          # extra for indicator warmup

    print(f"\n{'='*65}")
    print(f"  BACKTEST SCANNER")
    print(f"  Window   : {start_date} to {end_date}  ({args.years:.1f} yr)")
    print(f"  Universe : {args.universe}")
    print(f"  Workers  : {args.workers}")
    print(f"{'='*65}\n")

    trading_days = get_trading_days(start_date, end_date)
    logger.info(f"Trading days in window: {len(trading_days)}  ({trading_days[0]} to {trading_days[-1]})")

    # ── Ticker universe ───────────────────────────────────────────────────────
    logger.info("Fetching ticker universe...")
    all_tickers = get_ticker_universe()
    logger.info(f"Raw universe: {len(all_tickers)} tickers")

    if args.universe == "sp500":
        logger.info("Filtering to S&P 500...")
        try:
            from yahoo_fin import stock_info as si
            sp500_set = set(t.replace(".", "-") for t in si.tickers_sp500())
        except Exception as e:
            logger.warning(f"yahoo_fin S&P 500 failed ({e}), trying GitHub CSV...")
            try:
                import requests
                from io import StringIO
                resp = requests.get(
                    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
                    timeout=15,
                )
                sp500_df  = pd.read_csv(StringIO(resp.text))
                sp500_set = set(t.replace(".", "-") for t in sp500_df["Symbol"].tolist())
            except Exception as e2:
                logger.error(f"S&P 500 fallback also failed: {e2}. Using full universe.")
                sp500_set = set(all_tickers)

        tickers = [t for t in all_tickers if t in sp500_set]
        logger.info(f"S&P 500 overlap with universe: {len(tickers)} tickers")
        if len(tickers) < 10:
            logger.warning("Very few S&P 500 tickers matched -- falling back to full universe")
            tickers = all_tickers
    else:
        tickers = all_tickers
        logger.info(f"Full universe: {len(tickers)} tickers")

    # ── Bulk data fetch ───────────────────────────────────────────────────────
    t0 = datetime.now()
    logger.info(f"Fetching {fetch_days} days of history for {len(tickers)} tickers...")
    histories = bulk_fetch_history(tickers, days=fetch_days)
    elapsed   = (datetime.now() - t0).total_seconds()
    logger.info(f"Data fetch complete: {len(histories)}/{len(tickers)} tickers with data in {elapsed:.0f}s")

    if not histories:
        logger.error("No historical data returned. Check internet connection or yfinance.")
        return

    # ── Parallel criteria evaluation ──────────────────────────────────────────
    all_entries    = []
    stage_counters = {"s1": 0, "s2": 0, "s2b": 0, "s3": 0, "s4": 0, "trigger": 0}
    errors         = 0
    done           = 0
    lock           = threading.Lock()
    total          = len(histories)
    report_every   = max(1, total // 20)   # log at every 5% of tickers

    logger.info(f"Evaluating criteria: {total} tickers x {len(trading_days)} days...")
    t1 = datetime.now()

    def _eval(ticker: str) -> list[dict]:
        df_raw = histories.get(ticker)
        if df_raw is None:
            return []
        return backtest_ticker(ticker, df_raw, trading_days, stage_counters, lock)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_eval, t): t for t in histories}
        for future in as_completed(futures):
            done += 1
            try:
                entries = future.result()
                if entries:
                    with lock:
                        all_entries.extend(entries)
            except Exception as e:
                with lock:
                    errors += 1
                logger.debug(f"Error on {futures[future]}: {e}")

            if done % report_every == 0 or done == total:
                pct  = done / total * 100
                rate = done / max((datetime.now() - t1).total_seconds(), 1)
                with lock:
                    n_entries = len(all_entries)
                    s1 = stage_counters["s1"]
                    s2 = stage_counters["s2"]
                    s3 = stage_counters["s3"]
                    trig = stage_counters["trigger"]
                logger.info(
                    f"  {done:>4}/{total} tickers ({pct:.0f}%) | "
                    f"S1:{s1}  S2:{s2}  S3:{s3}  Trigger:{trig} | "
                    f"Entries:{n_entries} | {rate:.1f} tickers/s"
                )

    elapsed2 = (datetime.now() - t1).total_seconds()
    logger.info(
        f"Criteria eval done in {elapsed2:.0f}s. "
        f"Stage funnel: S1={stage_counters['s1']} S2={stage_counters['s2']} "
        f"S2b={stage_counters['s2b']} S3={stage_counters['s3']} "
        f"S4={stage_counters['s4']} Trigger={stage_counters['trigger']} "
        f"Errors={errors}"
    )
    logger.info(f"Total qualifying entries: {len(all_entries)}")

    if not all_entries:
        logger.error(
            "No entries qualified. Possible causes:\n"
            "  - Date range too narrow (start/end dates)\n"
            "  - All tickers failed Stage 1 (price/volume/ADR)\n"
            "  - No tickers had sufficient history for the warmup period\n"
            "  - Stage 2 momentum thresholds too tight for the period\n"
            "Try: python backtest_scanner.py --years 0.5 to test a shorter window first."
        )
        return

    # ── Forward return measurement ─────────────────────────────────────────────
    logger.info(f"Measuring forward returns for {len(all_entries)} entries...")
    t2 = datetime.now()

    # Pre-compute indicator DataFrames once per ticker (reuse across entries)
    indicator_cache = {}
    for ticker in set(e["ticker"] for e in all_entries):
        df_raw = histories.get(ticker)
        if df_raw is not None:
            try:
                indicator_cache[ticker] = compute_indicators(df_raw)
            except Exception:
                pass

    logger.info(f"Indicator cache built for {len(indicator_cache)} tickers")

    enriched = []
    skipped  = 0
    for entry in all_entries:
        df_ind = indicator_cache.get(entry["ticker"])
        if df_ind is None:
            skipped += 1
            continue
        try:
            enriched.append(add_forward_returns(entry, df_ind))
        except Exception as e:
            logger.debug(f"forward_returns({entry['ticker']} {entry['scan_date']}): {e}")
            enriched.append({
                **entry,
                "pct_1d": None, "pct_5d": None,
                "pct_10d": None, "pct_20d": None,
                "max_gain_pct": None, "did_break_out": False,
            })

    elapsed3 = (datetime.now() - t2).total_seconds()
    logger.info(f"Forward returns done in {elapsed3:.1f}s. Enriched: {len(enriched)}  Skipped: {skipped}")

    enriched.sort(key=lambda x: (x["scan_date"], x["ticker"]))

    # ── Summary ────────────────────────────────────────────────────────────────
    print_summary(enriched, start_date, end_date, args.years)

    # ── Grade filter for CSV ───────────────────────────────────────────────────
    grade_order  = {"A+": 0, "A": 1, "B": 2, "C": 3}
    output_data  = enriched
    if args.min_grade:
        cutoff      = grade_order[args.min_grade]
        output_data = [e for e in enriched if grade_order.get(e["grade"], 9) <= cutoff]
        logger.info(f"Grade filter >= {args.min_grade}: {len(output_data)}/{len(enriched)} entries")

    # ── CSV ────────────────────────────────────────────────────────────────────
    if args.output:
        out_path = args.output
    else:
        workspace = os.path.join(os.path.dirname(__file__), "..", "backtest_results")
        os.makedirs(workspace, exist_ok=True)
        out_path  = os.path.join(workspace, f"backtest_{date.today().strftime('%Y%m%d')}_{args.universe}_{args.years}yr.csv")
        out_path  = os.path.abspath(out_path)

    logger.info(f"Saving CSV to: {out_path}")
    save_csv(output_data, out_path)

    total_elapsed = (datetime.now() - t0).total_seconds()
    logger.info(f"Done. Total runtime: {total_elapsed/60:.1f} min")


if __name__ == "__main__":
    main()
