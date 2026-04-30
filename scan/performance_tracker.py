#!/usr/bin/env python3
"""
performance_tracker.py — Post-entry performance updater.

Runs at 4:30 PM EST daily after market close.
Fills in price_1d, price_5d, price_10d, price_20d, price_60d for all
watchlist and breakout entries that are missing performance data.

Also computes:
    - pct_change for each interval
    - did_break_out (watchlist: did price exceed pivot within 5 days?)
    - hit_stop (breakout: did price fall to stop within 10 days?)
    - max_gain_pct / max_gain_date (within 20 days)
    - max_r_multiple (breakout: best (price - entry) / risk achieved)
    - was_failed_breakout (closed back below pivot within 3 days)

Usage:
    python performance_tracker.py
    python performance_tracker.py --dry-run
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import logging
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from shared.db_writer import (
    get_pending_watchlist_performance,
    get_pending_breakout_performance,
    get_pending_runner_performance,
    upsert_watchlist_performance,
    upsert_breakout_performance,
    upsert_runner_performance,
    test_connection,
)
from shared.data_fetcher import fetch_history

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def trading_day_offset(start_date: date, n_days: int) -> date:
    """Return the date that is approximately n trading days after start_date."""
    bdays = pd.bdate_range(start=start_date, periods=n_days + 1)
    return bdays[-1].date() if len(bdays) > n_days else start_date + timedelta(days=n_days + 3)


def get_close_on_or_after(df: pd.DataFrame, target_date: date) -> float | None:
    """Return the closing price on or just after target_date from a OHLCV DataFrame."""
    target_ts = pd.Timestamp(target_date)
    subset = df[df.index >= target_ts]
    if subset.empty:
        return None
    return float(subset["Close"].iloc[0])


def pct_change(entry_price: float, current_price: float) -> float | None:
    if entry_price and entry_price > 0 and current_price:
        return round(((current_price - entry_price) / entry_price) * 100, 2)
    return None


# ─── Watchlist Performance ────────────────────────────────────────────────────

def update_watchlist_entries(dry_run: bool = False) -> int:
    """Fill in performance data for all pending watchlist entries. Returns count updated."""
    pending = get_pending_watchlist_performance()
    logger.info(f"Found {len(pending)} watchlist entries needing performance data")
    updated = 0

    for row in pending:
        ticker      = row["ticker"]
        scan_date   = row["scan_date"]
        entry_price = row["entry_price"]
        pivot_price = row["pivot_price"]

        if not entry_price:
            continue

        # Fetch enough history to cover all intervals (up to 90 trading days)
        df = fetch_history(ticker, days=100)
        if df is None:
            logger.warning(f"Could not fetch history for {ticker}")
            continue

        # Price at each interval
        def get_price(n: int) -> float | None:
            target = trading_day_offset(scan_date, n)
            if target > date.today():
                return None  # Not yet reached
            return get_close_on_or_after(df, target)

        p1  = get_price(1)
        p3  = get_price(3)
        p5  = get_price(5)
        p10 = get_price(10)
        p20 = get_price(20)
        p60 = get_price(60)

        # did_break_out: price exceeded pivot within 5 trading days
        did_break_out = False
        if pivot_price:
            window_end = trading_day_offset(scan_date, 5)
            window_df  = df[
                (df.index.date >= scan_date) &
                (df.index.date <= window_end)
            ]
            if not window_df.empty and window_df["High"].max() > pivot_price:
                did_break_out = True

        # max_gain: highest close within 20 trading days
        max_gain_pct  = None
        max_gain_date = None
        window_20_end = trading_day_offset(scan_date, 20)
        window_20_df  = df[
            (df.index.date >= scan_date) &
            (df.index.date <= window_20_end)
        ]
        if not window_20_df.empty:
            best_idx   = window_20_df["Close"].idxmax()
            best_price = float(window_20_df["Close"].max())
            max_gain_pct  = pct_change(entry_price, best_price)
            max_gain_date = best_idx.date()

        perf = {
            "ticker":          ticker,
            "scan_date":       scan_date,
            "price_1d":        p1,  "price_3d": p3,   "price_5d": p5,
            "price_10d":       p10, "price_20d": p20,  "price_60d": p60,
            "pct_change_1d":   pct_change(entry_price, p1),
            "pct_change_5d":   pct_change(entry_price, p5),
            "pct_change_10d":  pct_change(entry_price, p10),
            "pct_change_20d":  pct_change(entry_price, p20),
            "pct_change_60d":  pct_change(entry_price, p60),
            "did_break_out":   did_break_out,
            "max_gain_pct":    max_gain_pct,
            "max_gain_date":   max_gain_date,
        }

        if not dry_run:
            if upsert_watchlist_performance(row["watchlist_id"], perf):
                updated += 1
                logger.debug(f"Updated watchlist perf for {ticker} (id={row['watchlist_id']})")
        else:
            logger.info(f"[DRY RUN] Would update watchlist perf for {ticker}: 5d={perf['pct_change_5d']}%")
            updated += 1

    return updated




# ─── Runner Performance ─────────────────────────────────────────────────────────────────────────

def update_runner_entries(dry_run: bool = False) -> int:
    """Fill in performance data for all pending runner entries. Returns count updated."""
    import pyodbc
    import config as cfg

    pending = get_pending_runner_performance()
    logger.info(f"Found {len(pending)} runner entries needing performance data")
    updated = 0

    for row in pending:
        ticker      = row["ticker"]
        scan_date   = row["scan_date"]
        entry_price = row["entry_price"]
        if not entry_price:
            continue

        df = fetch_history(ticker, days=100)
        if df is None:
            logger.warning(f"Could not fetch history for runner {ticker}")
            continue

        def get_price(n: int) -> float | None:
            target = trading_day_offset(scan_date, n)
            if target > date.today():
                return None
            return get_close_on_or_after(df, target)

        p1  = get_price(1);  p5  = get_price(5)
        p10 = get_price(10); p20 = get_price(20); p60 = get_price(60)

        # did_break_out: price made new 20d high within 20 trading days
        did_break_out = False
        pre_df = df[df.index.date <= scan_date]
        high_at_scan = float(pre_df["High"].tail(20).max()) if not pre_df.empty else 0
        if high_at_scan > 0:
            w_end = trading_day_offset(scan_date, 20)
            w_df  = df[(df.index.date > scan_date) & (df.index.date <= w_end)]
            if not w_df.empty and w_df["High"].max() > high_at_scan:
                did_break_out = True

        # did_set_up: appeared in watchlist_entries after scan_date
        did_set_up = False; days_to_setup = None
        try:
            conn2   = pyodbc.connect(cfg.DB_CONNECTION_STRING, timeout=10)
            cursor2 = conn2.cursor()
            cursor2.execute(
                "SELECT MIN(scan_date) FROM watchlist_entries WHERE ticker = ? AND scan_date > ?",
                (ticker, scan_date)
            )
            result = cursor2.fetchone()
            conn2.close()
            if result and result[0]:
                did_set_up    = True
                days_to_setup = (result[0] - scan_date).days
        except Exception:
            pass

        # max_gain within 20 trading days
        max_gain_pct = None; max_gain_date = None
        w20_end = trading_day_offset(scan_date, 20)
        w20_df  = df[(df.index.date >= scan_date) & (df.index.date <= w20_end)]
        if not w20_df.empty:
            best_idx      = w20_df["Close"].idxmax()
            max_gain_pct  = pct_change(entry_price, float(w20_df["Close"].max()))
            max_gain_date = best_idx.date()

        perf = {
            "ticker": ticker, "scan_date": scan_date,
            "price_1d": p1,   "price_5d":  p5,
            "price_10d": p10, "price_20d": p20, "price_60d": p60,
            "pct_change_1d":  pct_change(entry_price, p1),
            "pct_change_5d":  pct_change(entry_price, p5),
            "pct_change_10d": pct_change(entry_price, p10),
            "pct_change_20d": pct_change(entry_price, p20),
            "pct_change_60d": pct_change(entry_price, p60),
            "did_set_up":     did_set_up,
            "days_to_setup":  days_to_setup,
            "did_break_out":  did_break_out,
            "max_gain_pct":   max_gain_pct,
            "max_gain_date":  max_gain_date,
        }

        if not dry_run:
            if upsert_runner_performance(row["runner_id"], perf):
                updated += 1
        else:
            logger.info(f"[DRY RUN] Would update runner perf for {ticker}: 5d={perf['pct_change_5d']}%")
            updated += 1

    return updated

# ─── Breakout Performance ─────────────────────────────────────────────────────

def update_breakout_entries(dry_run: bool = False) -> int:
    """Fill in performance data for all pending breakout entries. Returns count updated."""
    pending = get_pending_breakout_performance()
    logger.info(f"Found {len(pending)} breakout entries needing performance data")
    updated = 0

    for row in pending:
        ticker       = row["ticker"]
        breakout_date = row["scan_date"]
        entry_price  = row["entry_price"]
        stop_price   = row["stop_price"]
        pivot_price  = row["pivot_price"]

        if not entry_price:
            continue

        df = fetch_history(ticker, days=100)
        if df is None:
            logger.warning(f"Could not fetch history for {ticker}")
            continue

        def get_price(n: int) -> float | None:
            target = trading_day_offset(breakout_date, n)
            if target > date.today():
                return None
            return get_close_on_or_after(df, target)

        p1  = get_price(1)
        p3  = get_price(3)
        p5  = get_price(5)
        p10 = get_price(10)
        p20 = get_price(20)
        p60 = get_price(60)

        # hit_stop: did price ever close at or below stop_price within 10 days?
        hit_stop      = False
        hit_stop_date = None
        if stop_price:
            window_10_end = trading_day_offset(breakout_date, 10)
            window_df = df[
                (df.index.date >= breakout_date) &
                (df.index.date <= window_10_end)
            ]
            for idx, bar in window_df.iterrows():
                if float(bar["Low"]) <= stop_price:
                    hit_stop      = True
                    hit_stop_date = idx.date()
                    break

        # max_r_multiple: best (high - entry) / (entry - stop) within 20 days
        max_r_multiple = None
        risk = (entry_price - stop_price) if stop_price else None
        if risk and risk > 0:
            window_20_end = trading_day_offset(breakout_date, 20)
            window_20_df  = df[
                (df.index.date >= breakout_date) &
                (df.index.date <= window_20_end)
            ]
            if not window_20_df.empty:
                best_high = float(window_20_df["High"].max())
                max_r_multiple = round((best_high - entry_price) / risk, 2)

        # max_gain_pct
        max_gain_pct  = None
        max_gain_date = None
        window_20_end = trading_day_offset(breakout_date, 20)
        window_20_df  = df[
            (df.index.date >= breakout_date) &
            (df.index.date <= window_20_end)
        ]
        if not window_20_df.empty:
            best_idx   = window_20_df["Close"].idxmax()
            best_price = float(window_20_df["Close"].max())
            max_gain_pct  = pct_change(entry_price, best_price)
            max_gain_date = best_idx.date()

        # was_failed_breakout: price closed back below pivot within 3 days
        was_failed_breakout = False
        if pivot_price:
            window_3_end = trading_day_offset(breakout_date, 3)
            window_3_df  = df[
                (df.index.date >= breakout_date) &
                (df.index.date <= window_3_end)
            ]
            if not window_3_df.empty and window_3_df["Close"].min() < pivot_price:
                was_failed_breakout = True

        perf = {
            "ticker":               ticker,
            "breakout_date":        breakout_date,
            "entry_price":          entry_price,
            "stop_price":           stop_price,
            "price_1d":             p1,   "price_3d": p3,  "price_5d": p5,
            "price_10d":            p10,  "price_20d": p20, "price_60d": p60,
            "pct_change_1d":        pct_change(entry_price, p1),
            "pct_change_5d":        pct_change(entry_price, p5),
            "pct_change_10d":       pct_change(entry_price, p10),
            "pct_change_20d":       pct_change(entry_price, p20),
            "pct_change_60d":       pct_change(entry_price, p60),
            "hit_stop":             hit_stop,
            "hit_stop_date":        hit_stop_date,
            "max_r_multiple":       max_r_multiple,
            "max_gain_pct":         max_gain_pct,
            "max_gain_date":        max_gain_date,
            "was_failed_breakout":  was_failed_breakout,
        }

        if not dry_run:
            if upsert_breakout_performance(row["breakout_id"], perf):
                updated += 1
                logger.debug(f"Updated breakout perf for {ticker} (id={row['breakout_id']})")
        else:
            logger.info(f"[DRY RUN] Would update breakout perf for {ticker}: 5d={perf['pct_change_5d']}%")
            updated += 1

    return updated


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Performance tracker for watchlist and breakout entries")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing to DB")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  PERFORMANCE TRACKER — {date.today()}")
    print(f"{'='*55}\n")

    if not args.dry_run:
        if not test_connection():
            logger.error("Cannot connect to SQL Server.")
            sys.exit(1)

    w_updated = update_watchlist_entries(dry_run=args.dry_run)
    b_updated = update_breakout_entries(dry_run=args.dry_run)
    r_updated = update_runner_entries(dry_run=args.dry_run)

    print(f"\n  Watchlist entries updated : {w_updated}")
    print(f"  Breakout entries updated  : {b_updated}")
    print(f"  Runner entries updated    : {r_updated}")
    if args.dry_run:
        print("  [DRY RUN] No data written to database.\n")
    else:
        print(f"  Done.\n")


if __name__ == "__main__":
    main()
