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
from shared.cloudwatch_logging import enable_cloudwatch_logging

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
enable_cloudwatch_logging("performance_tracker")


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


def get_close_on_date(df: pd.DataFrame, target_date: date) -> float | None:
    """Exact-date close if present, else the next available trading day's close."""
    exact = df[df.index.date == target_date]
    if not exact.empty:
        return float(exact["Close"].iloc[0])
    return get_close_on_or_after(df, target_date)


def rebase_for_splits(df: pd.DataFrame, entry_date: date, stored_entry_price: float | None,
                       *other_prices: float | None) -> tuple[float | None, float, list]:
    """
    Re-derive the entry price from `df` itself instead of trusting a value stored
    at scan time, and rescale any other stored price levels (stop, pivot, ...) by
    the same ratio.

    Why: yfinance retroactively adjusts an entire history for splits every time
    it's fetched. entry_price gets written to the DB once, at scan time — before
    a future split exists to adjust for. When performance_tracker later re-fetches
    history (now split-adjusted), comparing that OLD raw entry_price against NEW
    adjusted closes produces a fake cliff. Example: KLAC did a 10-for-1 split on
    2026-06-12; entries stored ~$1800-2000 pre-split were compared against
    post-split closes ~$180-200, showing a fabricated ~-90% "loss".

    Deriving entry_price from the same `df` call as the exit prices guarantees
    both sides are on the same adjustment basis, regardless of any split that
    happens between entry_date and whenever this runs. The implied split_ratio
    (stored / adjusted) is then applied to `other_prices` (e.g. stop_price,
    pivot_price) so everything stays internally consistent.

    Returns (adjusted_entry_price, split_ratio, [rescaled other_prices]).
    Falls back to the stored values unchanged if entry_date isn't in `df` at all.
    """
    adjusted_entry = get_close_on_date(df, entry_date)
    if not adjusted_entry or not stored_entry_price or stored_entry_price <= 0:
        return stored_entry_price, 1.0, list(other_prices)

    split_ratio = stored_entry_price / adjusted_entry
    rescaled = [p / split_ratio if p else p for p in other_prices]
    return adjusted_entry, split_ratio, rescaled


def pct_change(entry_price: float, current_price: float) -> float | None:
    if entry_price and entry_price > 0 and current_price:
        return round(((current_price - entry_price) / entry_price) * 100, 2)
    return None


def max_gain_and_drawdown(window_df: pd.DataFrame, entry_price: float) -> tuple:
    """
    Best-case and worst-case outcome within a window, both measured on CLOSE
    (not intraday High/Low) for consistency with each other — this is still
    not true intraday drawdown, just the worst daily close.

    Returns (max_gain_pct, max_gain_date, max_drawdown_pct, max_drawdown_date).
    """
    if window_df.empty:
        return None, None, None, None

    gain_idx  = window_df["Close"].idxmax()
    gain_pct  = pct_change(entry_price, float(window_df["Close"].max()))
    dd_idx    = window_df["Close"].idxmin()
    dd_pct    = pct_change(entry_price, float(window_df["Close"].min()))

    return gain_pct, gain_idx.date(), dd_pct, dd_idx.date()


# ─── Watchlist Performance ────────────────────────────────────────────────────

def update_watchlist_entries(dry_run: bool = False, force_ticker: str | None = None) -> int:
    """
    Fill in performance data for all pending watchlist entries. Returns count updated.
    force_ticker reprocesses every entry for that ticker regardless of whether
    performance data already looks complete — use to repair rows computed
    before a bug fix (e.g. the 2026-07-08 split-rebase fix).
    """
    pending = get_pending_watchlist_performance(force_ticker=force_ticker)
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

        # Re-derive entry_price (and rescale pivot_price) from this same fetch so
        # a split between scan_date and now can't produce a fake cliff — see
        # rebase_for_splits() docstring.
        entry_price, _split_ratio, (pivot_price,) = rebase_for_splits(
            df, scan_date, entry_price, pivot_price
        )

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

        # max_gain / max_drawdown: best/worst close within 20 trading days
        window_20_end = trading_day_offset(scan_date, 20)
        window_20_df  = df[
            (df.index.date >= scan_date) &
            (df.index.date <= window_20_end)
        ]
        max_gain_pct, max_gain_date, max_drawdown_pct, max_drawdown_date = \
            max_gain_and_drawdown(window_20_df, entry_price)

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
            "max_drawdown_pct":  max_drawdown_pct,
            "max_drawdown_date": max_drawdown_date,
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

def update_runner_entries(dry_run: bool = False, force_ticker: str | None = None) -> int:
    """Fill in performance data for all pending runner entries. Returns count updated."""
    import pyodbc
    import config as cfg

    pending = get_pending_runner_performance(force_ticker=force_ticker)
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

        # Re-derive entry_price from this same fetch — see rebase_for_splits() docstring.
        entry_price, _split_ratio, _ = rebase_for_splits(df, scan_date, entry_price)

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

        # max_gain / max_drawdown within 20 trading days
        w20_end = trading_day_offset(scan_date, 20)
        w20_df  = df[(df.index.date >= scan_date) & (df.index.date <= w20_end)]
        max_gain_pct, max_gain_date, max_drawdown_pct, max_drawdown_date = \
            max_gain_and_drawdown(w20_df, entry_price)

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
            "max_drawdown_pct":  max_drawdown_pct,
            "max_drawdown_date": max_drawdown_date,
        }

        if not dry_run:
            if upsert_runner_performance(row["runner_id"], perf):
                updated += 1
        else:
            logger.info(f"[DRY RUN] Would update runner perf for {ticker}: 5d={perf['pct_change_5d']}%")
            updated += 1

    return updated

# ─── Breakout Performance ─────────────────────────────────────────────────────

def update_breakout_entries(dry_run: bool = False, force_ticker: str | None = None) -> int:
    """Fill in performance data for all pending breakout entries. Returns count updated."""
    pending = get_pending_breakout_performance(force_ticker=force_ticker)
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

        # Re-derive entry_price (and rescale stop_price/pivot_price) from this same
        # fetch — see rebase_for_splits() docstring. Critical here: hit_stop and
        # max_r_multiple below compare stop_price directly against df's High/Low,
        # so a stale pre-split stop_price would corrupt both.
        entry_price, _split_ratio, (stop_price, pivot_price) = rebase_for_splits(
            df, breakout_date, entry_price, stop_price, pivot_price
        )

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

        # max_gain / max_drawdown within 20 trading days
        window_20_end = trading_day_offset(breakout_date, 20)
        window_20_df  = df[
            (df.index.date >= breakout_date) &
            (df.index.date <= window_20_end)
        ]
        max_gain_pct, max_gain_date, max_drawdown_pct, max_drawdown_date = \
            max_gain_and_drawdown(window_20_df, entry_price)

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
            "max_drawdown_pct":     max_drawdown_pct,
            "max_drawdown_date":    max_drawdown_date,
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
    parser.add_argument("--ticker", type=str, default=None,
                         help="Force-reprocess ALL entries for this ticker, even if performance "
                              "data already looks complete (e.g. to repair rows affected by a "
                              "since-fixed bug like the split-rebase fix)")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  PERFORMANCE TRACKER — {date.today()}")
    if args.ticker:
        print(f"  [FORCE REPROCESS] {args.ticker}")
    print(f"{'='*55}\n")

    if not args.dry_run:
        if not test_connection():
            logger.error("Cannot connect to SQL Server.")
            sys.exit(1)

    w_updated = update_watchlist_entries(dry_run=args.dry_run, force_ticker=args.ticker)
    b_updated = update_breakout_entries(dry_run=args.dry_run, force_ticker=args.ticker)
    r_updated = update_runner_entries(dry_run=args.dry_run, force_ticker=args.ticker)

    print(f"\n  Watchlist entries updated : {w_updated}")
    print(f"  Breakout entries updated  : {b_updated}")
    print(f"  Runner entries updated    : {r_updated}")
    if args.dry_run:
        print("  [DRY RUN] No data written to database.\n")
    else:
        print(f"  Done.\n")


if __name__ == "__main__":
    main()
