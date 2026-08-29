#!/usr/bin/env python3
"""
congress_backtest.py -- Performance of every disclosed congressional stock trade
in the trailing N months (default 12), across all members on file.

Data source: TattooedHead/house-stock-watcher-data -- House of Representatives
only (this feed does not cover the Senate). Equity trades only; options and
other non-equity assets are filtered out at the source.

Methodology (same as pelosi_backtest.py):
  - Universe: every Purchase disclosure in the trailing window.
  - Entry: next trading day's close on/after the disclosure date.
  - Size: the disclosed amount range's midpoint (amount_mid), as notional dollars.
  - Exit: a later Sale disclosure for the same (representative, ticker, owner),
    FIFO, at the next trading day's close. No matching Sale -> marked to the
    latest available close ("held").
  - "Exchange" transactions are excluded (non-directional corporate actions).

Prices are fetched in bulk via yfinance (chunked, multi-threaded) rather than
one call per trade -- with ~700 distinct tickers, per-ticker calls would be
too slow and risk Yahoo rate-limiting.

Usage:
    python congress_backtest.py [--months 12]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_URL = "https://raw.githubusercontent.com/TattooedHead/house-stock-watcher-data/main/data/all_transactions.json"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "all_transactions.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "congress_backtest_results.json")
CHUNK_SIZE = 100


def load_transactions(refresh: bool = True) -> list[dict]:
    if refresh or not os.path.exists(CACHE_PATH):
        print(f"Fetching latest disclosures from {DATA_URL} ...")
        resp = requests.get(DATA_URL, timeout=60)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(resp.text)
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def parse_date(s: str):
    try:
        return datetime.strptime(s, "%m/%d/%Y")
    except Exception:
        return None


def build_lots(rows: list[dict], window_start: datetime) -> list[dict]:
    """FIFO-pair Purchase/Sale per (representative, ticker, owner)."""
    for r in rows:
        r["_disc"] = parse_date(r["disclosure_date"])
        r["_txn"] = parse_date(r["transaction_date"])
    rows = [r for r in rows if r["_disc"] is not None and r["type"] in ("Purchase", "Sale")]
    rows.sort(key=lambda r: (r["_disc"], r["_txn"] or r["_disc"]))

    open_lots: dict[tuple, list[dict]] = defaultdict(list)
    closed_lots = []

    for r in rows:
        key = (r["representative"], r["ticker"], r["owner"])
        if r["type"] == "Purchase":
            if r["_disc"] < window_start:
                continue
            open_lots[key].append({
                "representative": r["representative"],
                "district": r.get("district"),
                "ticker": r["ticker"],
                "owner": r["owner"],
                "entry_disclosure_date": r["_disc"],
                "amount_mid": r["amount_mid"],
                "amount_range": r["amount"],
                "filing_id": r["filing_id"],
                "exit_disclosure_date": None,
            })
        else:  # Sale
            lots = open_lots.get(key)
            if not lots:
                continue
            lot = lots.pop(0)
            lot["exit_disclosure_date"] = r["_disc"]
            closed_lots.append(lot)

    still_open = [lot for lots in open_lots.values() for lot in lots]
    return closed_lots + still_open


def fetch_prices_bulk(tickers: list[str], start: datetime, end: datetime) -> dict:
    """Bulk-fetch daily history for many tickers, chunked. Returns {ticker: DataFrame}."""
    price_data = {}
    failed = []
    start_str = (start - timedelta(days=10)).strftime("%Y-%m-%d")
    end_str = (end + timedelta(days=5)).strftime("%Y-%m-%d")

    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i:i + CHUNK_SIZE]
        print(f"  Fetching prices {i+1}-{min(i+CHUNK_SIZE, len(tickers))} of {len(tickers)} ...")
        try:
            df = yf.download(
                chunk, start=start_str, end=end_str, group_by="ticker",
                threads=True, auto_adjust=True, progress=False,
            )
        except Exception as e:
            print(f"    chunk failed entirely: {e}")
            failed.extend(chunk)
            continue

        for t in chunk:
            try:
                sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                sub = sub.dropna(subset=["Close"])
                if sub.empty:
                    failed.append(t)
                    continue
                sub.index = pd.to_datetime(sub.index).tz_localize(None)
                price_data[t] = sub
            except Exception:
                failed.append(t)

    return price_data, failed


def next_close_on_or_after(df, target_date: datetime):
    after = df[df.index >= target_date]
    if after.empty:
        return None, None
    return after.index[0].to_pydatetime(), float(after["Close"].iloc[0])


def latest_close(df):
    return df.index[-1].to_pydatetime(), float(df["Close"].iloc[-1])


def xirr(cashflows: list[tuple]) -> float | None:
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


def main():
    parser = argparse.ArgumentParser(description="Performance of all congressional stock trades in a trailing window")
    parser.add_argument("--months", type=float, default=12.0)
    parser.add_argument("--no-refresh", action="store_true")
    args = parser.parse_args()

    today = datetime.today()
    window_start = today - timedelta(days=args.months * 30.44)

    print(f"\n{'='*70}")
    print(f"  CONGRESSIONAL TRADE PERFORMANCE -- {window_start.date()} -> {today.date()}")
    print(f"  (House of Representatives only -- Senate not covered by this feed)")
    print(f"{'='*70}\n")

    all_rows = load_transactions(refresh=not args.no_refresh)
    lots = build_lots(all_rows, window_start)
    lots = [l for l in lots if l["entry_disclosure_date"] >= window_start]
    print(f"Trades opened in window: {len(lots)} across {len({l['representative'] for l in lots})} members, "
          f"{len({l['ticker'] for l in lots})} tickers\n")

    tickers = sorted({l["ticker"] for l in lots})
    price_data, failed_tickers = fetch_prices_bulk(tickers, window_start, today)
    print(f"\nPrice data OK for {len(price_data)}/{len(tickers)} tickers "
          f"({len(failed_tickers)} failed: {', '.join(failed_tickers[:20])}{'...' if len(failed_tickers) > 20 else ''})\n")

    trade_results = []
    skipped = 0

    for lot in lots:
        df = price_data.get(lot["ticker"])
        if df is None:
            skipped += 1
            continue
        entry_date, entry_price = next_close_on_or_after(df, lot["entry_disclosure_date"])
        if entry_price is None:
            skipped += 1
            continue
        if lot["exit_disclosure_date"] is not None:
            exit_date, exit_price = next_close_on_or_after(df, lot["exit_disclosure_date"])
            status = "closed"
            if exit_price is None:
                exit_date, exit_price = latest_close(df)
                status = "held (exit price missing)"
        else:
            exit_date, exit_price = latest_close(df)
            status = "held"

        return_pct = (exit_price / entry_price - 1) * 100
        exit_value = lot["amount_mid"] / entry_price * exit_price

        trade_results.append({
            "representative": lot["representative"],
            "district": lot["district"],
            "ticker": lot["ticker"],
            "owner": lot["owner"],
            "amount_mid": lot["amount_mid"],
            "disclosure_date": lot["entry_disclosure_date"].strftime("%Y-%m-%d"),
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "entry_price": round(entry_price, 2),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "exit_price": round(exit_price, 2),
            "exit_value": round(exit_value, 2),
            "return_pct": round(return_pct, 2),
            "status": status,
        })

    if skipped:
        print(f"Skipped {skipped} trades with no usable price data.\n")

    # ─── Aggregate ──────────────────────────────────────────────────────────────
    total_invested = sum(t["amount_mid"] for t in trade_results)
    total_exit_value = sum(t["exit_value"] for t in trade_results)
    total_pnl = total_exit_value - total_invested
    win_rate = 100 * sum(1 for t in trade_results if t["return_pct"] > 0) / len(trade_results) if trade_results else 0

    all_cashflows = []
    for t in trade_results:
        all_cashflows.append((datetime.strptime(t["entry_date"], "%Y-%m-%d"), -t["amount_mid"]))
        all_cashflows.append((datetime.strptime(t["exit_date"], "%Y-%m-%d"), t["exit_value"]))
    portfolio_xirr = xirr(all_cashflows)

    # SPY same-schedule benchmark
    spy_df = fetch_prices_bulk(["SPY"], window_start, today)[0].get("SPY")
    spy_cashflows = []
    if spy_df is not None:
        for t in trade_results:
            e_date, e_price = next_close_on_or_after(spy_df, datetime.strptime(t["disclosure_date"], "%Y-%m-%d"))
            x_date, x_price = next_close_on_or_after(spy_df, datetime.strptime(t["exit_date"], "%Y-%m-%d")) \
                if t["status"] == "closed" else latest_close(spy_df)
            if e_price and x_price:
                shares = t["amount_mid"] / e_price
                spy_cashflows.append((e_date, -t["amount_mid"]))
                spy_cashflows.append((x_date, shares * x_price))
    spy_xirr = xirr(spy_cashflows) if spy_cashflows else None

    # ─── Per-member leaderboard (dollar-weighted return %) ─────────────────────
    by_member = defaultdict(list)
    for t in trade_results:
        by_member[t["representative"]].append(t)

    leaderboard = []
    for rep, trades in by_member.items():
        inv = sum(x["amount_mid"] for x in trades)
        val = sum(x["exit_value"] for x in trades)
        leaderboard.append({
            "representative": rep,
            "trades": len(trades),
            "total_invested": round(inv, 2),
            "total_pnl": round(val - inv, 2),
            "weighted_return_pct": round(100 * (val - inv) / inv, 2) if inv else None,
        })
    leaderboard.sort(key=lambda x: x["weighted_return_pct"] or -999, reverse=True)

    trades_sorted = sorted(trade_results, key=lambda t: t["return_pct"], reverse=True)

    print(f"  {'='*66}")
    print(f"  Trades analyzed        : {len(trade_results)}")
    print(f"  Win rate               : {win_rate:.0f}%")
    print(f"  Total notional invested: ${total_invested:,.0f}")
    print(f"  Total ending value     : ${total_exit_value:,.0f}")
    print(f"  Total P&L              : ${total_pnl:,.0f}  ({100*total_pnl/total_invested:+.1f}%)")
    print(f"  Portfolio XIRR         : {f'{portfolio_xirr*100:+.1f}%/yr' if portfolio_xirr is not None else 'n/a'}")
    print(f"  SPY same-schedule XIRR : {f'{spy_xirr*100:+.1f}%/yr' if spy_xirr is not None else 'n/a'}")
    if portfolio_xirr is not None and spy_xirr is not None:
        print(f"  Alpha vs SPY           : {(portfolio_xirr-spy_xirr)*100:+.1f} pts/yr")

    print(f"\n  Top 15 trades by return:")
    print(f"  {'Rep':<24} {'Ticker':<7} {'Disclosed':<11} {'Ret%':>8}  Status")
    for t in trades_sorted[:15]:
        print(f"  {t['representative'][:24]:<24} {t['ticker']:<7} {t['disclosure_date']:<11} {t['return_pct']:>+7.1f}%  {t['status']}")

    print(f"\n  Bottom 15 trades by return:")
    for t in trades_sorted[-15:]:
        print(f"  {t['representative'][:24]:<24} {t['ticker']:<7} {t['disclosure_date']:<11} {t['return_pct']:>+7.1f}%  {t['status']}")

    print(f"\n  Member leaderboard (dollar-weighted return, min 2 trades):")
    print(f"  {'Representative':<28} {'Trades':>6} {'Invested':>14} {'Ret%':>8}")
    shown = [m for m in leaderboard if m["trades"] >= 2][:15]
    for m in shown:
        print(f"  {m['representative'][:28]:<28} {m['trades']:>6} ${m['total_invested']:>12,.0f} {m['weighted_return_pct']:>+7.1f}%")
    print()

    results = {
        "run_date": today.strftime("%Y-%m-%d"),
        "window_start": window_start.strftime("%Y-%m-%d"),
        "window_months": args.months,
        "trades": trade_results,
        "failed_tickers": failed_tickers,
        "summary": {
            "trades_analyzed": len(trade_results),
            "win_rate_pct": round(win_rate, 1),
            "total_invested": round(total_invested, 2),
            "total_ending_value": round(total_exit_value, 2),
            "total_pnl": round(total_pnl, 2),
            "portfolio_xirr_pct": round(portfolio_xirr * 100, 2) if portfolio_xirr is not None else None,
            "spy_same_schedule_xirr_pct": round(spy_xirr * 100, 2) if spy_xirr is not None else None,
        },
        "member_leaderboard": leaderboard,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Full results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
