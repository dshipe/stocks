#!/usr/bin/env python3
"""
trade_simulator.py — Rules.MD-based $ P&L backtest over tracked watchlist
breakouts. Read-only report — no orders placed, nothing written to the DB.

First-class version of the ad hoc simulation methodology: what would trading
every Stage-5-confirmed setup (did_break_out=1 in watchlist_performance) have
returned, with fixed position sizing and Rules.MD Stage 6/7 risk management?

Entry     — pivot_price (R23: buy at the breakout trigger), falls back to
            price_at_scan when pivot_price is missing.
Stop      — base_low - 0.5% (R29), derived from the entry's base_depth_pct.
Stop-out  — uses max_drawdown_pct (the worst CLOSE within the 20-day tracking
            window — see performance_tracker.py's max_gain_and_drawdown, added
            2026-07-08) rather than only checking the four discrete 1d/5d/10d/
            20d checkpoints. This catches a stop breach on ANY trading day in
            the window, not just the four sampled ones — meaningfully more
            accurate than checkpoint-only detection, though still limited to
            daily closes (no true intraday low).
Profit    — approximates R36/R37 (sell 40% at 2R, breakeven stop) and R38
            (sell another 25% at 3R) using max_gain_pct to detect whether those
            thresholds were reached within the window; the remainder exits at
            the last available checkpoint close.

Caveat this does NOT fix: exact intraday timing of stops/scale-outs still
can't be reconstructed from daily-close data alone — this is the best
available approximation given what's tracked, not an audited backtest.

Usage:
    python trade_simulator.py
    python trade_simulator.py --position-size 25000
    python trade_simulator.py --grades A+,A,B          # exclude C
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from collections import defaultdict

import config as cfg
from shared.db_writer import get_connection

STOP_BUFFER = 0.995  # R29: base_low - 0.5%


def fetch_trades(grades: set | None):
    sql = """
        SELECT e.scan_date, e.ticker, e.pattern_type, e.pattern_grade,
               e.pivot_price, e.price_at_scan, e.base_depth_pct,
               p.price_1d, p.price_5d, p.price_10d, p.price_20d,
               p.max_gain_pct, p.max_drawdown_pct
        FROM watchlist_entries e
        JOIN watchlist_performance p ON p.watchlist_id = e.id
        WHERE p.did_break_out = 1
    """
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    if grades:
        rows = [r for r in rows if (r["pattern_grade"] or "") in grades]
    return rows


def simulate_trade(row: dict, position_size: float) -> dict | None:
    entry = float(row["pivot_price"] or row["price_at_scan"] or 0)
    if entry <= 0:
        return None
    depth = float(row["base_depth_pct"]) if row["base_depth_pct"] is not None else 10.0

    base_low = entry * (1 - depth / 100.0)
    stop = base_low * STOP_BUFFER
    risk_per_share = max(entry - stop, entry * 0.01)
    risk_pct = (risk_per_share / entry) * 100.0

    checkpoints = [
        (label, float(row[col])) for label, col in
        [("1d", "price_1d"), ("5d", "price_5d"), ("10d", "price_10d"), ("20d", "price_20d")]
        if row[col] is not None
    ]
    if not checkpoints:
        return None

    max_gain_pct = float(row["max_gain_pct"]) if row["max_gain_pct"] is not None else None
    max_drawdown_pct = float(row["max_drawdown_pct"]) if row["max_drawdown_pct"] is not None else None

    stopped = max_drawdown_pct is not None and max_drawdown_pct <= -risk_pct
    note = ""

    if stopped:
        realized_pct = -risk_pct
        note = "stopped (max_drawdown_pct)"
    else:
        two_r, three_r = 2 * risk_pct, 3 * risk_pct
        terminal_label, terminal_price = checkpoints[-1]
        terminal_pct = ((terminal_price - entry) / entry) * 100.0

        if max_gain_pct is not None and max_gain_pct >= two_r:
            reached_3r = max_gain_pct >= three_r
            runner_pct = max(terminal_pct, 0.0)
            if reached_3r:
                realized_pct = (0.40 * two_r) + (0.25 * three_r) + (0.35 * runner_pct)
                note = "2R+3R scale-out"
            else:
                realized_pct = (0.40 * two_r) + (0.60 * runner_pct)
                note = "2R scale-out"
        else:
            realized_pct = terminal_pct
            note = f"held to {terminal_label}"

    return {
        "ticker": row["ticker"], "scan_date": str(row["scan_date"]),
        "pattern": row["pattern_type"], "grade": row["pattern_grade"],
        "entry": entry, "risk_pct": risk_pct, "stopped": stopped,
        "realized_pct": realized_pct,
        "pnl": position_size * (realized_pct / 100.0),
        "note": note,
    }


def report(trades: list, position_size: float):
    if not trades:
        print("  No qualifying trades found.\n")
        return

    total_pnl = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] > 0]
    stopped = [t for t in trades if t["stopped"]]

    print(f"  Trades taken            : {len(trades)}")
    print(f"  Capital deployed (sum)  : ${position_size * len(trades):,.0f}  "
          f"(${position_size:,.0f} x {len(trades)} sequential positions)")
    print(f"  Total P&L               : ${total_pnl:,.0f}")
    print(f"  Avg P&L / trade         : ${total_pnl/len(trades):,.0f}")
    print(f"  Avg return / trade      : {sum(t['realized_pct'] for t in trades)/len(trades):.2f}%")
    print(f"  Win rate                : {len(wins)}/{len(trades)} = {100*len(wins)/len(trades):.1f}%")
    print(f"  Stopped out             : {len(stopped)} ({100*len(stopped)/len(trades):.1f}%)")

    biggest_win  = max(trades, key=lambda t: t["pnl"])
    biggest_loss = min(trades, key=lambda t: t["pnl"])
    print(f"  Biggest win             : {biggest_win['ticker']} {biggest_win['scan_date']} "
          f"${biggest_win['pnl']:,.0f} ({biggest_win['realized_pct']:.1f}%) [{biggest_win['note']}]")
    print(f"  Biggest loss            : {biggest_loss['ticker']} {biggest_loss['scan_date']} "
          f"${biggest_loss['pnl']:,.0f} ({biggest_loss['realized_pct']:.1f}%) [{biggest_loss['note']}]")

    print("\n  By grade:")
    by_grade = defaultdict(list)
    for t in trades:
        by_grade[t["grade"] or "?"].append(t)
    for g in sorted(by_grade):
        gt = by_grade[g]
        pnl = sum(t["pnl"] for t in gt)
        wr = 100 * len([t for t in gt if t["pnl"] > 0]) / len(gt)
        print(f"    {g:<3} n={len(gt):>4}  total_pnl=${pnl:>12,.0f}  avg_pnl=${pnl/len(gt):>8,.0f}  win_rate={wr:5.1f}%")

    print("\n  By pattern:")
    by_pat = defaultdict(list)
    for t in trades:
        by_pat[t["pattern"] or "?"].append(t)
    for p in sorted(by_pat):
        pt = by_pat[p]
        pnl = sum(t["pnl"] for t in pt)
        wr = 100 * len([t for t in pt if t["pnl"] > 0]) / len(pt)
        print(f"    {p:<10} n={len(pt):>4}  total_pnl=${pnl:>12,.0f}  avg_pnl=${pnl/len(pt):>8,.0f}  win_rate={wr:5.1f}%")
    print()


def main():
    parser = argparse.ArgumentParser(description="Rules.MD-based $ P&L backtest over tracked breakouts")
    parser.add_argument("--position-size", type=float, default=50000.0,
                         help="Fixed $ position size per trade (default: 50000)")
    parser.add_argument("--grades", type=str, default=None,
                         help="Comma-separated grades to include, e.g. 'A+,A,B' (default: all)")
    args = parser.parse_args()

    grades = set(g.strip().upper() for g in args.grades.split(",")) if args.grades else None

    rows = fetch_trades(grades)
    trades = [t for t in (simulate_trade(r, args.position_size) for r in rows) if t]

    print(f"\n{'='*70}")
    print(f"  TRADE SIMULATOR — position size ${args.position_size:,.0f}"
          f"{'  grades=' + args.grades if args.grades else ''}")
    print(f"{'='*70}\n")
    report(trades, args.position_size)


if __name__ == "__main__":
    main()
