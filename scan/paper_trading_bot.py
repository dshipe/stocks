#!/usr/bin/env python3
"""
paper_trading_bot.py — Fully automated PAPER trading. No real orders are ever
placed; this maintains a simulated portfolio in the paper_trades /
paper_trade_sales tables and records every decision with a reason, so the
whole history is auditable later.

Runs once daily, after market close (see cron_setup.sh), in two passes:

  1. MANAGE existing open positions (checked first, before deploying new
     capital) — for every open paper_trades lot:
       a. R36/R37 — at 2R profit, sell 40% of the ORIGINAL shares, move the
          stop to breakeven (entry price). One-time, tracked via hit_2r.
       b. R38     — at 3R profit, sell another 25% of the ORIGINAL shares.
          One-time, tracked via hit_3r. (a) and (b) can both fire the same
          day if price gaps straight past 3R.
       c. R39     — trail the stop toward the 10-day SMA of daily closes,
          same rule and same only-ever-raise behavior as schwab_stop_loss.py.
          Applies to every open position regardless of hit_2r, mirroring the
          real-money script exactly.
       d. Stop check — if today's close is at/below the (possibly just-
          raised) stop, sell all remaining shares. Reason distinguishes the
          initial R29 stop from a raised R39 trailing stop.

  2. DEPLOY new capital — today's confirmed breakout_entries (Stage-5
     signals), ranked grade-then-R/R exactly like select_trades.py, sized by
     the same R33 (account %) / R34 (ADV %) caps, skipping any ticker already
     held open and stopping once MAX_CONCURRENT_POSITIONS or ACCOUNT_SIZE is
     exhausted -- accounting for capital already committed to step 1's
     survivors, not starting from a blank account each day.

Caveat this does NOT fix: all prices are daily closes (no true intraday fill
simulation) -- a stop or profit-target "hit" here means today's close crossed
the level, not that a real order would have filled at that exact price. Same
approximation trade_simulator.py and check_profit_targets.py already use.

Usage:
    python paper_trading_bot.py
    python paper_trading_bot.py --dry-run              # print decisions, write nothing
    python paper_trading_bot.py --date 2026-07-08       # replay a specific date's signals
"""

import argparse
import os
import sys
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
from select_trades import size_candidate
from shared.data_fetcher import fetch_history, fetch_intraday, is_market_open
from shared.db_writer import (
    get_open_paper_trades,
    get_breakout_entries_full,
    insert_paper_trade,
    record_paper_sale,
    update_paper_trade_stop,
)

SMA_PERIOD = 10
PROFIT_TARGETS = [
    (2.0, 40, "hit_2r", "2R profit target — sold 40% of original position, stop moved to breakeven (R36/R37)"),
    (3.0, 25, "hit_3r", "3R profit target — sold another 25% of original position (R38)"),
]


def get_current_price(ticker: str) -> tuple[float, object] | tuple[None, None]:
    """(price, price_df) — live price if the market's open, else latest daily close."""
    df = fetch_history(ticker, days=SMA_PERIOD + 15)
    if df is None or df.empty:
        return None, None
    if is_market_open():
        intraday = fetch_intraday(ticker)
        if intraday and intraday.get("current_price"):
            return float(intraday["current_price"]), df
    return float(df["Close"].iloc[-1]), df


def manage_open_positions(today: date, dry_run: bool) -> dict:
    open_trades = get_open_paper_trades()
    print(f"  Open positions: {len(open_trades)}")

    closed_count = 0
    partial_count = 0
    committed_capital = 0.0

    for pos in open_trades:
        ticker = pos["ticker"]
        current_price, df = get_current_price(ticker)
        if current_price is None:
            print(f"    {ticker:<7} could not fetch price — skipping this run")
            committed_capital += pos["remaining_shares"] * float(pos["entry_price"])
            continue

        risk_per_share = float(pos["risk_per_share"])
        entry_price = float(pos["entry_price"])
        r_multiple = (current_price - entry_price) / risk_per_share if risk_per_share > 0 else 0
        remaining = pos["remaining_shares"]
        stop = float(pos["stop_price"])

        print(f"    {ticker:<7} entry=${entry_price:.2f} now=${current_price:.2f} "
              f"R={r_multiple:.2f} stop=${stop:.2f} remaining={remaining}")

        # ── (a)/(b) profit-target partials ──────────────────────────────────
        for r_level, pct, flag, reason in PROFIT_TARGETS:
            if pos[flag] or r_multiple < r_level or remaining <= 0:
                continue
            shares_to_sell = min(remaining, round(pos["shares"] * pct / 100))
            if shares_to_sell <= 0:
                continue
            realized_pnl = shares_to_sell * (current_price - entry_price)
            print(f"      -> {reason}: sell {shares_to_sell} @ ${current_price:.2f}"
                  f"{' [DRY RUN]' if dry_run else ''}")
            if not dry_run:
                record_paper_sale(
                    pos["id"], ticker, shares_to_sell, current_price, today, reason,
                    r_multiple, realized_pnl,
                    mark_2r=(flag == "hit_2r"), mark_3r=(flag == "hit_3r"),
                )
                if flag == "hit_2r":
                    stop = entry_price  # move to breakeven
                    update_paper_trade_stop(pos["id"], stop)
            remaining -= shares_to_sell
            partial_count += 1

        if remaining <= 0:
            closed_count += 1
            continue

        # ── (c) R39 trailing stop — 10-day SMA, only ever raised ────────────
        if df is not None and len(df) >= SMA_PERIOD:
            sma = round(float(df["Close"].tail(SMA_PERIOD).mean()), 4)
            if sma > stop:
                print(f"      -> R39 trailing stop raised ${stop:.2f} -> ${sma:.2f}{' [DRY RUN]' if dry_run else ''}")
                if not dry_run:
                    update_paper_trade_stop(pos["id"], sma)
                stop = sma

        # ── (d) stop check ──────────────────────────────────────────────────
        if current_price <= stop:
            was_raised = stop > float(pos["initial_stop_price"])
            reason = (
                f"stopped out — closed at ${current_price:.2f}, "
                f"at/below {'trailing (R39)' if was_raised else 'initial (R29)'} stop ${stop:.2f}"
            )
            realized_pnl = remaining * (current_price - entry_price)
            print(f"      -> {reason}: sell {remaining} @ ${current_price:.2f}{' [DRY RUN]' if dry_run else ''}")
            if not dry_run:
                record_paper_sale(pos["id"], ticker, remaining, current_price, today, reason, r_multiple, realized_pnl)
            closed_count += 1
        else:
            committed_capital += remaining * entry_price

    return {"closed": closed_count, "partial": partial_count, "committed_capital": committed_capital}


def deploy_new_capital(today: date, committed_capital: float, open_ticker_count: int, dry_run: bool) -> int:
    held_tickers = {p["ticker"] for p in get_open_paper_trades()}
    candidates = get_breakout_entries_full(today)
    print(f"\n  Confirmed breakout signals for {today}: {len(candidates)}")

    account_size = cfg.ACCOUNT_SIZE
    capital_used = committed_capital
    slots_used = open_ticker_count
    opened = 0

    for c in candidates:
        ticker = c["ticker"]
        if ticker in held_tickers:
            print(f"    {ticker:<7} skipped — already holding an open position")
            continue
        if slots_used >= cfg.MAX_CONCURRENT_POSITIONS:
            print(f"    {ticker:<7} skipped — MAX_CONCURRENT_POSITIONS ({cfg.MAX_CONCURRENT_POSITIONS}) reached")
            continue

        sized = size_candidate({"breakout_price": c["breakout_price"], "avg_daily_volume": c["avg_daily_volume"]}, account_size)
        shares = sized["shares"]
        position_size = sized["position_size"]
        if shares <= 0:
            print(f"    {ticker:<7} skipped — position size rounds to 0 shares")
            continue
        if capital_used + position_size > account_size:
            print(f"    {ticker:<7} skipped — would exceed remaining account capital")
            continue

        reason = (
            f"{c['pattern_type']}/{c['pattern_grade']} breakout at ${c['breakout_price']:.2f} "
            f"(pivot ${c['pivot_price']:.2f}), {c['volume_ratio']:.1f}x avg volume. "
            f"Target R:R {c['suggested_rr_ratio']}:1. {c.get('qualification_reasons') or ''}"
        ).strip()

        print(f"    {ticker:<7} BUY {shares} @ ${c['breakout_price']:.2f} (${position_size:,.0f}, "
              f"{sized['binding_rule']}){' [DRY RUN]' if dry_run else ''}")
        if not dry_run:
            insert_paper_trade({
                "ticker": ticker,
                "shares": shares,
                "entry_price": c["breakout_price"],
                "entry_date": today,
                "entry_reason": reason,
                "pattern_type": c["pattern_type"],
                "pattern_grade": c["pattern_grade"],
                "stop_price": c["stop_price"],
                "risk_per_share": c["risk_per_share"],
                "breakout_entry_id": c["id"],
            })

        capital_used += position_size
        slots_used += 1
        opened += 1

    return opened


def main():
    parser = argparse.ArgumentParser(description="Automated paper trading bot (no real orders)")
    parser.add_argument("--dry-run", action="store_true", help="Print decisions, write nothing to the DB")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None, help="Replay a specific date's breakout signals (default: today)")
    args = parser.parse_args()

    target_date = date.today()
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid --date '{args.date}' — expected YYYY-MM-DD")
            sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  PAPER TRADING BOT — {target_date}  (simulated only — no real orders)")
    print(f"{'='*70}\n")

    print("Step 1: managing open positions...")
    mgmt = manage_open_positions(target_date, args.dry_run)

    open_count_after = len(get_open_paper_trades()) if not args.dry_run else None
    # In --dry-run, nothing was actually closed in the DB, so approximate the
    # count for sizing purposes using what this run *would* have closed.
    still_open_count = (
        open_count_after if open_count_after is not None
        else len(get_open_paper_trades()) - mgmt["closed"]
    )

    print(f"\nStep 2: deploying new capital...")
    opened = deploy_new_capital(target_date, mgmt["committed_capital"], still_open_count, args.dry_run)

    print(f"\n  {'-'*55}")
    print(f"  Positions closed this run  : {mgmt['closed']}")
    print(f"  Partial exits this run     : {mgmt['partial']}")
    print(f"  New positions opened       : {opened}")
    print(f"  {'[DRY RUN] nothing written to the DB' if args.dry_run else 'All changes committed.'}")
    print(f"  {'-'*55}\n")


if __name__ == "__main__":
    main()
