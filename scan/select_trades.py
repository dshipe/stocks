#!/usr/bin/env python3
"""
select_trades.py — Rank a day's alerts and pick which to act on within a
capital budget. Read-only report — no orders placed, nothing written to the DB.

Implements Rules.MD Stage 6 position sizing (R33/R34), which previously existed
only on paper: the system fired every qualifying alert with no concept of
account size, so a trader had no way to know which of a day's ~10-50 alerts
were actually affordable, or how large a position each one could support.

For each candidate:
    R33 — position size <= MAX_POSITION_PCT of ACCOUNT_SIZE (concentration cap)
    R34 — position size <= MAX_PCT_OF_ADV of the stock's avg daily $ volume
          (don't buy more than you can exit without moving the market)
Position size = the LARGER-constraint-respecting max allowed under both, i.e.
min(R33 cap, R34 cap) — not a fixed size. Candidates are taken in rank order
(grade first, then R/R) until ACCOUNT_SIZE or MAX_CONCURRENT_POSITIONS runs out.
A candidate that doesn't fit is skipped (not a hard stop) — a cheaper one further
down the list may still fit the remaining budget.

Data source: breakout_entries for the target date (the actual Stage-5-confirmed
signals) if any exist; falls back to watchlist_entries (candidates only, not a
confirmed trigger) with a clear label when breakout_entries is empty for that
date — e.g. before the R24/ADR2 volume-baseline fix, or on a day nothing broke out.

Usage:
    python select_trades.py
    python select_trades.py --date 2026-07-08
    python select_trades.py --account-size 250000
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from datetime import date, datetime

import config as cfg
from shared.db_writer import get_breakout_candidates_for_date, get_watchlist_candidates_for_date


def size_candidate(candidate: dict, account_size: float) -> dict:
    """Compute the max position size allowed under R33 (account %) and R34 (ADV %)."""
    price = float(candidate.get("breakout_price") or 0)
    adv   = candidate.get("avg_daily_volume")

    max_by_account = account_size * cfg.MAX_POSITION_PCT / 100.0
    max_by_adv = None
    if adv and price > 0:
        max_by_adv = cfg.MAX_PCT_OF_ADV / 100.0 * float(adv) * price

    caps = {"R33 (account %)": max_by_account}
    if max_by_adv is not None:
        caps["R34 (ADV %)"] = max_by_adv

    binding_rule, position_size = min(caps.items(), key=lambda kv: kv[1])
    shares = int(position_size // price) if price > 0 else 0
    actual_size = shares * price

    return {
        **candidate,
        "binding_rule": binding_rule,
        "shares": shares,
        "position_size": actual_size,
    }


def select_trades(target_date: date, account_size: float) -> dict:
    candidates = get_breakout_candidates_for_date(target_date)
    source = "breakout_entries (confirmed)"
    if not candidates:
        candidates = get_watchlist_candidates_for_date(target_date)
        source = "watchlist_entries (candidates only — no confirmed breakout for this date)"

    sized = [size_candidate(c, account_size) for c in candidates if c.get("breakout_price")]

    selected, skipped_budget = [], []
    capital_used = 0.0
    for c in sized:
        if len(selected) >= cfg.MAX_CONCURRENT_POSITIONS:
            skipped_budget.append({**c, "reason": f"MAX_CONCURRENT_POSITIONS ({cfg.MAX_CONCURRENT_POSITIONS}) reached"})
            continue
        if c["shares"] <= 0:
            skipped_budget.append({**c, "reason": "position size rounds to 0 shares"})
            continue
        if capital_used + c["position_size"] > account_size:
            skipped_budget.append({**c, "reason": "would exceed remaining account capital"})
            continue
        capital_used += c["position_size"]
        selected.append(c)

    return {
        "source": source,
        "selected": selected,
        "skipped": skipped_budget,
        "capital_used": capital_used,
        "account_size": account_size,
    }


def main():
    parser = argparse.ArgumentParser(description="Rank today's alerts and pick trades within a capital budget")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                         help="Target date (default: today)")
    parser.add_argument("--account-size", type=float, default=None,
                         help=f"Override ACCOUNT_SIZE (default: ${cfg.ACCOUNT_SIZE:,.0f} from config)")
    args = parser.parse_args()

    target_date = date.today()
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid --date '{args.date}' — expected YYYY-MM-DD")
            sys.exit(1)

    account_size = args.account_size or cfg.ACCOUNT_SIZE

    result = select_trades(target_date, account_size)

    print(f"\n{'='*70}")
    print(f"  TRADE SELECTION — {target_date}")
    print(f"{'='*70}\n")
    print(f"  Source           : {result['source']}")
    print(f"  Account size     : ${account_size:,.0f}")
    print(f"  R33 cap/position : {cfg.MAX_POSITION_PCT:.0f}% = ${account_size * cfg.MAX_POSITION_PCT/100:,.0f}")
    print(f"  R34 cap          : {cfg.MAX_PCT_OF_ADV:.1f}% of avg daily $ volume")
    print(f"  Max concurrent   : {cfg.MAX_CONCURRENT_POSITIONS}\n")

    if not result["selected"] and not result["skipped"]:
        print("  No candidates found for this date.\n")
        return

    print(f"  {'Ticker':<8} {'Gr':<3} {'Pattern':<10} {'Price':>9} {'Shares':>8} {'Size $':>12}  Binding cap")
    print("  " + "-" * 78)
    for c in result["selected"]:
        print(
            f"  {c['ticker']:<8} {c.get('pattern_grade') or '-':<3} {c.get('pattern_type') or '-':<10} "
            f"${c['breakout_price']:>8.2f} {c['shares']:>8} ${c['position_size']:>10,.0f}  {c['binding_rule']}"
        )

    print(f"\n  Selected    : {len(result['selected'])} position(s)")
    print(f"  Capital used: ${result['capital_used']:,.0f} / ${account_size:,.0f} "
          f"({100*result['capital_used']/account_size:.0f}%)")

    if result["skipped"]:
        print(f"\n  Skipped ({len(result['skipped'])}) — not silently dropped:")
        for c in result["skipped"]:
            print(f"    {c['ticker']:<8} {c.get('pattern_grade') or '-':<3} — {c['reason']}")
    print()


if __name__ == "__main__":
    main()
