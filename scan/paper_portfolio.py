#!/usr/bin/env python3
"""
paper_portfolio.py — Read-only view into the paper trading bot's ledger
(paper_trades / paper_trade_sales). No orders, no writes.

Shows: currently open positions (with live unrealized P&L/R and the original
buy reason), full sale history (with the reason each sale was made), and an
account-level summary.

Usage:
    python paper_portfolio.py
    python paper_portfolio.py --history-only     # skip live price lookups
"""

import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
from shared.data_fetcher import fetch_history, fetch_intraday, is_market_open
from shared.db_writer import get_open_paper_trades, get_paper_trade_history, get_paper_trade_sales


def get_current_price(ticker: str) -> float | None:
    if is_market_open():
        intraday = fetch_intraday(ticker)
        if intraday and intraday.get("current_price"):
            return float(intraday["current_price"])
    df = fetch_history(ticker, days=10)
    if df is not None and not df.empty:
        return float(df["Close"].iloc[-1])
    return None


def main():
    parser = argparse.ArgumentParser(description="View the paper trading portfolio and trade history")
    parser.add_argument("--history-only", action="store_true", help="Skip live price lookups for open positions")
    args = parser.parse_args()

    print(f"\n{'='*78}")
    print(f"  PAPER TRADING PORTFOLIO  (simulated only — no real money)")
    print(f"{'='*78}\n")

    open_trades = get_open_paper_trades()
    all_sales = get_paper_trade_sales()
    closed_trades = get_paper_trade_history(status="closed")

    # ─── Open positions ─────────────────────────────────────────────────────────
    print(f"  OPEN POSITIONS ({len(open_trades)})")
    print(f"  {'-'*74}")
    committed = 0.0
    unrealized = 0.0
    if not open_trades:
        print("  (none)")
    for pos in open_trades:
        entry = float(pos["entry_price"])
        cost_basis = pos["remaining_shares"] * entry
        committed += cost_basis
        current_price = None if args.history_only else get_current_price(pos["ticker"])
        if current_price:
            pnl = pos["remaining_shares"] * (current_price - entry)
            unrealized += pnl
            r_mult = (current_price - entry) / float(pos["risk_per_share"]) if pos["risk_per_share"] else None
            r_str = f"  R={r_mult:+.2f}" if r_mult is not None else ""
            print(f"  {pos['ticker']:<7} {pos['remaining_shares']:>5} sh  entry ${entry:>8.2f} ({pos['entry_date']})  "
                  f"now ${current_price:>8.2f}  P&L ${pnl:>+10,.0f}{r_str}  stop ${float(pos['stop_price']):.2f}")
        else:
            print(f"  {pos['ticker']:<7} {pos['remaining_shares']:>5} sh  entry ${entry:>8.2f} ({pos['entry_date']})  "
                  f"stop ${float(pos['stop_price']):.2f}")
        reason = (pos.get("entry_reason") or "")[:100]
        print(f"           reason: {reason}")

    print(f"\n  Capital committed (cost basis): ${committed:,.0f}")
    if not args.history_only:
        print(f"  Unrealized P&L                : ${unrealized:+,.0f}")

    # ─── Sale history ───────────────────────────────────────────────────────────
    print(f"\n  SALE HISTORY ({len(all_sales)} sales across {len(closed_trades)} fully-closed lots)")
    print(f"  {'-'*74}")
    if not all_sales:
        print("  (none yet)")
    for s in all_sales[:30]:
        pnl = float(s["realized_pnl"]) if s["realized_pnl"] is not None else 0
        r_str = f"  R={float(s['r_multiple']):+.2f}" if s["r_multiple"] is not None else ""
        print(f"  {s['ticker']:<7} {s['shares_sold']:>5} sh @ ${float(s['sale_price']):>8.2f} ({s['sale_date']})  "
              f"P&L ${pnl:>+10,.0f}{r_str}")
        print(f"           reason: {s['sale_reason']}")
    if len(all_sales) > 30:
        print(f"  ... and {len(all_sales) - 30} more (see the DB for full history)")

    # ─── Account summary ────────────────────────────────────────────────────────
    total_realized = sum(float(s["realized_pnl"] or 0) for s in all_sales)
    wins = [s for s in all_sales if float(s["realized_pnl"] or 0) > 0]
    print(f"\n  {'='*74}")
    print(f"  Account size (config)      : ${cfg.ACCOUNT_SIZE:,.0f}")
    print(f"  Capital committed          : ${committed:,.0f}")
    print(f"  Available buying power     : ${cfg.ACCOUNT_SIZE - committed:,.0f}")
    print(f"  Total realized P&L to date : ${total_realized:+,.0f}")
    if all_sales:
        print(f"  Win rate on sales          : {len(wins)}/{len(all_sales)} = {100*len(wins)/len(all_sales):.0f}%")
    if not args.history_only:
        print(f"  Unrealized P&L (open)      : ${unrealized:+,.0f}")
        print(f"  Total P&L (realized+unrl.) : ${total_realized + unrealized:+,.0f}")
    print()


if __name__ == "__main__":
    main()
