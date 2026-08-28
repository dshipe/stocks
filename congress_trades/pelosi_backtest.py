#!/usr/bin/env python3
"""
pelosi_backtest.py -- Backtest a "follow Nancy Pelosi's disclosed stock trades" strategy.

Data source: TattooedHead/house-stock-watcher-data (free, actively-scraped mirror of
official House Clerk Periodic Transaction Reports filed under the STOCK Act).
https://github.com/TattooedHead/house-stock-watcher-data
Only equity (stock) trades are in this feed -- options and other non-equity assets are
filtered out at the source.

Strategy:
  - Universe: every Nancy Pelosi "Purchase" disclosure in the trailing N years.
  - Entry: next available trading day's close on/after the *disclosure* date (not the
    transaction date -- a follower cannot act until the trade is public). This is the
    earliest realistic entry for a retail copier.
  - Size: the disclosed amount range's midpoint (amount_mid) used as notional dollars.
  - Exit: a later "Sale" disclosure for the same ticker/owner closes the position
    (FIFO), at the next trading day's close after that disclosure. Positions with no
    matching Sale by the run date are marked to the latest available close ("held").
  - A Sale for a ticker never bought inside the window (e.g. bought years earlier) has
    no open lot to close and is ignored -- this backtest only simulates positions a
    3-year-old copycat would actually be holding.
  - "Exchange" transactions (stock swaps, not buy/sell decisions) are excluded.

Benchmark: SPY, using the *same* cashflow schedule (same dates, same dollar amounts) --
this isolates whether Pelosi's stock picks beat just buying the index on her timing,
rather than comparing against an arbitrary lump-sum window.

Portfolio-level return is computed as an XIRR (money-weighted annualized return) over
the staggered entry dates, since trades don't all start on day one.

Usage:
    python pelosi_backtest.py [--years 3]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import requests
import yfinance as yf

DATA_URL = "https://raw.githubusercontent.com/TattooedHead/house-stock-watcher-data/main/data/all_transactions.json"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "all_transactions.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "pelosi_backtest_results.json")

REPRESENTATIVE = "Nancy Pelosi"
BENCHMARK_TICKER = "SPY"


# ─── Data loading ──────────────────────────────────────────────────────────────

def load_transactions(refresh: bool = True) -> list[dict]:
    """Fetch the full house-stock-watcher dataset, caching a local copy."""
    if refresh or not os.path.exists(CACHE_PATH):
        print(f"Fetching latest disclosures from {DATA_URL} ...")
        resp = requests.get(DATA_URL, timeout=60)
        resp.raise_for_status()
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(resp.text)
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def pelosi_trades(all_rows: list[dict]) -> list[dict]:
    rows = [r for r in all_rows if REPRESENTATIVE.lower() in r["representative"].lower()]
    for r in rows:
        r["_txn_date"] = datetime.strptime(r["transaction_date"], "%m/%d/%Y")
        r["_disc_date"] = datetime.strptime(r["disclosure_date"], "%m/%d/%Y")
    rows.sort(key=lambda r: (r["_disc_date"], r["_txn_date"]))
    return rows


# ─── Trade construction ────────────────────────────────────────────────────────

def build_lots(rows: list[dict], window_start: datetime) -> list[dict]:
    """
    Pair Purchase/Sale disclosures per (ticker, owner) FIFO. Only Purchases whose
    disclosure date falls inside the window open a tracked lot; a Sale can only
    close a lot that was itself opened inside the window.
    """
    open_lots: dict[tuple, list[dict]] = {}
    closed_lots = []

    for r in rows:
        if r["type"] not in ("Purchase", "Sale"):
            continue  # skip "Exchange" and anything else non-directional
        key = (r["ticker"], r["owner"])

        if r["type"] == "Purchase":
            if r["_disc_date"] < window_start:
                continue  # outside the backtest window -- not a trade we'd have made
            lot = {
                "ticker": r["ticker"],
                "owner": r["owner"],
                "entry_disclosure_date": r["_disc_date"],
                "entry_transaction_date": r["_txn_date"],
                "amount_mid": r["amount_mid"],
                "amount_range": r["amount"],
                "filing_id": r["filing_id"],
                "exit_disclosure_date": None,
                "exit_transaction_date": None,
            }
            open_lots.setdefault(key, []).append(lot)
        else:  # Sale
            lots = open_lots.get(key)
            if not lots:
                continue  # we never opened this position inside the window
            lot = lots.pop(0)
            lot["exit_disclosure_date"] = r["_disc_date"]
            lot["exit_transaction_date"] = r["_txn_date"]
            closed_lots.append(lot)

    still_open = [lot for lots in open_lots.values() for lot in lots]
    return closed_lots + still_open


# ─── Price data ─────────────────────────────────────────────────────────────────

def fetch_price_history(ticker: str, start: datetime, end: datetime):
    df = yf.Ticker(ticker).history(
        start=(start - timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(end + timedelta(days=5)).strftime("%Y-%m-%d"),
    )
    if df.empty:
        return None
    df.index = df.index.tz_localize(None)
    return df


def next_close_on_or_after(df, target_date: datetime):
    """First available closing price on/after target_date. None if data runs out."""
    after = df[df.index >= target_date]
    if after.empty:
        return None, None
    return after.index[0].to_pydatetime(), float(after["Close"].iloc[0])


def latest_close(df):
    return df.index[-1].to_pydatetime(), float(df["Close"].iloc[-1])


# ─── XIRR (money-weighted annualized return) ───────────────────────────────────

def xirr(cashflows: list[tuple]) -> float | None:
    """
    cashflows: list of (datetime, amount) -- negative = outflow, positive = inflow.
    Solves NPV(rate) = 0 via bisection. Returns annualized rate, or None if it
    doesn't converge (e.g. all cashflows same sign).
    """
    if not any(cf < 0 for _, cf in cashflows) or not any(cf > 0 for _, cf in cashflows):
        return None
    t0 = min(d for d, _ in cashflows)

    def npv(rate):
        return sum(cf / ((1 + rate) ** ((d - t0).days / 365.0)) for d, cf in cashflows)

    lo, hi = -0.9999, 10.0
    npv_lo, npv_hi = npv(lo), npv(hi)
    if npv_lo * npv_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        npv_mid = npv(mid)
        if abs(npv_mid) < 1e-6:
            return mid
        if npv_lo * npv_mid < 0:
            hi = mid
        else:
            lo, npv_lo = mid, npv_mid
    return (lo + hi) / 2


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backtest following Nancy Pelosi's disclosed trades")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument("--no-refresh", action="store_true", help="Use cached dataset instead of re-downloading")
    args = parser.parse_args()

    today = datetime.today()
    window_start = today - timedelta(days=args.years * 365.25)

    print(f"\n{'='*70}")
    print(f"  PELOSI FOLLOW-TRADE BACKTEST  --  {window_start.date()} -> {today.date()}")
    print(f"{'='*70}\n")

    all_rows = load_transactions(refresh=not args.no_refresh)
    rows = pelosi_trades(all_rows)
    print(f"Total disclosed Pelosi trades on file : {len(rows)}")

    lots = build_lots(rows, window_start)
    lots = [l for l in lots if l["entry_disclosure_date"] >= window_start]
    print(f"Trades opened inside the {args.years:.1f}-yr window : {len(lots)}\n")

    if not lots:
        print("No trades in this window. Nothing to backtest.")
        return

    tickers = sorted({l["ticker"] for l in lots})
    print(f"Tickers: {', '.join(tickers)}")

    price_cache = {}
    for t in tickers + [BENCHMARK_TICKER]:
        df = fetch_price_history(t, window_start, today)
        if df is None:
            print(f"  WARNING: no price data for {t} -- its trade(s) will be skipped")
        price_cache[t] = df

    trade_results = []
    pelosi_cashflows = []
    spy_cashflows = []
    skipped = []

    for lot in lots:
        df = price_cache.get(lot["ticker"])
        if df is None:
            skipped.append(lot["ticker"])
            continue

        entry_date, entry_price = next_close_on_or_after(df, lot["entry_disclosure_date"])
        if entry_price is None:
            skipped.append(lot["ticker"])
            continue

        if lot["exit_disclosure_date"] is not None:
            exit_date, exit_price = next_close_on_or_after(df, lot["exit_disclosure_date"])
            status = "closed"
            if exit_price is None:
                exit_date, exit_price = latest_close(df)
                status = "held (exit price data missing, marked to last close)"
        else:
            exit_date, exit_price = latest_close(df)
            status = "held (no sale disclosed yet)"

        shares = lot["amount_mid"] / entry_price
        exit_value = shares * exit_price
        return_pct = (exit_price / entry_price - 1) * 100
        holding_days = (exit_date - entry_date).days

        trade_results.append({
            "ticker": lot["ticker"],
            "owner": lot["owner"],
            "amount_range": lot["amount_range"],
            "amount_mid": lot["amount_mid"],
            "disclosure_date": lot["entry_disclosure_date"].strftime("%Y-%m-%d"),
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "entry_price": round(entry_price, 2),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "exit_price": round(exit_price, 2),
            "exit_value": round(exit_value, 2),
            "return_pct": round(return_pct, 2),
            "holding_days": holding_days,
            "status": status,
        })
        pelosi_cashflows.append((entry_date, -lot["amount_mid"]))
        pelosi_cashflows.append((exit_date, exit_value))

        # Same-schedule SPY benchmark: same dates, same dollar amount, SPY instead
        spy_df = price_cache.get(BENCHMARK_TICKER)
        if spy_df is not None:
            spy_entry_date, spy_entry_price = next_close_on_or_after(spy_df, lot["entry_disclosure_date"])
            spy_exit_date, spy_exit_price = (
                next_close_on_or_after(spy_df, lot["exit_disclosure_date"])
                if lot["exit_disclosure_date"] is not None else latest_close(spy_df)
            )
            if spy_entry_price and spy_exit_price:
                spy_shares = lot["amount_mid"] / spy_entry_price
                spy_cashflows.append((spy_entry_date, -lot["amount_mid"]))
                spy_cashflows.append((spy_exit_date, spy_shares * spy_exit_price))

    # ─── Aggregate ──────────────────────────────────────────────────────────────
    total_invested = sum(t["amount_mid"] for t in trade_results)
    total_exit_value = sum(t["exit_value"] for t in trade_results)
    total_pnl = total_exit_value - total_invested
    win_rate = 100 * sum(1 for t in trade_results if t["return_pct"] > 0) / len(trade_results) if trade_results else 0
    pelosi_xirr = xirr(pelosi_cashflows)
    spy_xirr = xirr(spy_cashflows)

    print(f"\n  {'-'*66}")
    print(f"  {'Ticker':<7} {'Disclosed':<11} {'Entry':<11} {'Entry$':>9} "
          f"{'Exit':<11} {'Exit$':>9} {'Ret%':>8}  Status")
    print(f"  {'-'*66}")
    for t in trade_results:
        print(
            f"  {t['ticker']:<7} {t['disclosure_date']:<11} {t['entry_date']:<11} "
            f"{t['entry_price']:>9.2f} {t['exit_date']:<11} {t['exit_price']:>9.2f} "
            f"{t['return_pct']:>+7.1f}%  {t['status']}"
        )
    if skipped:
        print(f"\n  Skipped (no price data): {', '.join(sorted(set(skipped)))}")

    print(f"\n  {'='*66}")
    print(f"  Trades simulated       : {len(trade_results)}")
    print(f"  Win rate               : {win_rate:.0f}%")
    print(f"  Total notional invested: ${total_invested:,.0f}")
    print(f"  Total ending value     : ${total_exit_value:,.0f}")
    print(f"  Total P&L              : ${total_pnl:,.0f}  ({100*total_pnl/total_invested:+.1f}%)")
    print(f"  Pelosi strategy XIRR   : {f'{pelosi_xirr*100:+.1f}%/yr' if pelosi_xirr is not None else 'n/a'}")
    print(f"  SPY same-schedule XIRR : {f'{spy_xirr*100:+.1f}%/yr' if spy_xirr is not None else 'n/a'}")
    if pelosi_xirr is not None and spy_xirr is not None:
        print(f"  Alpha vs SPY (annualized): {(pelosi_xirr-spy_xirr)*100:+.1f} pts/yr")
    print()

    results = {
        "run_date": today.strftime("%Y-%m-%d"),
        "window_start": window_start.strftime("%Y-%m-%d"),
        "window_years": args.years,
        "trades": trade_results,
        "skipped_tickers": sorted(set(skipped)),
        "summary": {
            "trades_simulated": len(trade_results),
            "win_rate_pct": round(win_rate, 1),
            "total_invested": round(total_invested, 2),
            "total_ending_value": round(total_exit_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(100 * total_pnl / total_invested, 2) if total_invested else None,
            "pelosi_xirr_pct": round(pelosi_xirr * 100, 2) if pelosi_xirr is not None else None,
            "spy_same_schedule_xirr_pct": round(spy_xirr * 100, 2) if spy_xirr is not None else None,
            "alpha_vs_spy_pct_per_yr": round((pelosi_xirr - spy_xirr) * 100, 2) if pelosi_xirr is not None and spy_xirr is not None else None,
        },
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Full results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
