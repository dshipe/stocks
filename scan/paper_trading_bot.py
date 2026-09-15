#!/usr/bin/env python3
"""
paper_trading_bot.py — Fully automated PAPER trading. No real orders are ever
placed; this maintains a simulated portfolio in the paper_trades /
paper_trade_sales tables and records every decision with a reason, so the
whole history is auditable later.

Runs every 30 minutes during market hours, ~2 minutes after each
breakout_scanner run (see cron_setup.sh), in two passes:

  1. MANAGE existing open positions (checked first, before deploying new
     capital) — for every open paper_trades lot:
       a. R36/R37 — at 2R profit, sell 40% of the ORIGINAL shares, move the
          stop to breakeven (entry price). One-time, tracked via hit_2r.
       b. R38     — at 3R profit, sell another 25% of the ORIGINAL shares.
          One-time, tracked via hit_3r. (a) and (b) can both fire in the
          same run if price gaps straight past 3R.
       c. R39     — trail the stop toward the 10-day SMA of daily closes
          (the SMA itself is still a daily indicator -- only the check
          against it now happens intraday), same rule and same only-ever-
          raise behavior as schwab_stop_loss.py. Applies to every open
          position regardless of hit_2r, mirroring the real-money script.
       d. Stop check — if the current price is at/below the (possibly
          just-raised) stop, sell all remaining shares. Reason distinguishes
          the initial R29 stop from a raised R39 trailing stop.

  2. DEPLOY new capital — today's confirmed breakout_entries (Stage-5
     signals), ranked grade-then-R/R exactly like select_trades.py, sized by
     the same R33 (account %) / R34 (ADV %) caps, skipping any ticker already
     held open and stopping once MAX_CONCURRENT_POSITIONS or ACCOUNT_SIZE is
     exhausted -- accounting for capital already committed to step 1's
     survivors, not starting from a blank account each run.

**FIX (2026-09-15):** used to run once daily after close, so both buys and
stop-outs only happened once a day regardless of what the market did in
between -- a stock that spiked, alerted, and completely reversed intraday
(XHLD) got "bought" that evening at the stale alert-time price, hours after
it stopped being available, with its stop already blown through before the
paper position even opened. get_current_price() already used live intraday
prices when the market's open (fetch_intraday()) and this whole script is
idempotent per run -- the once-daily schedule was the actual bug. Now buys
happen within ~30 min of the alert and stops are checked at the same
cadence, both during 9:30 AM-4:00 PM ET. Prices are still not a perfect
intraday fill simulation (a stop "hit" means the price *at this 30-min
check* crossed the level, not that a real order would have filled at that
exact instant), but the gap is now minutes, not hours.

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
    _today_est,
)
from shared.cloudwatch_logging import enable_cloudwatch_logging

enable_cloudwatch_logging("paper_trading_bot")

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

        # Fill at the CURRENT price, not breakout_price (the price at the moment
        # breakout_scanner detected it, intraday). Buying only happens once a day
        # in this batch step, hours after detection -- for most stocks that gap is
        # negligible, but a volatile mover can completely reverse in the meantime.
        # Confirmed live: XHLD detected at $14.76, still "bought" at $14.76 by this
        # step even though it had already crashed to a $8.92 close by then -- a
        # fill no real order could ever have gotten, which made its stop-loss
        # meaningless (the "entry" was already far below the stop).
        current_price, _ = get_current_price(ticker)
        if current_price is None:
            print(f"    {ticker:<7} skipped — could not fetch current price")
            continue
        stop_price = float(c["stop_price"])
        if current_price <= stop_price:
            print(f"    {ticker:<7} skipped — current price ${current_price:.2f} already at/below "
                  f"stop ${stop_price:.2f} (moved too far since detection)")
            continue
        risk_per_share = round(current_price - stop_price, 4)

        sized = size_candidate({"breakout_price": current_price, "avg_daily_volume": c["avg_daily_volume"]}, account_size)
        shares = sized["shares"]
        position_size = sized["position_size"]
        if shares <= 0:
            print(f"    {ticker:<7} skipped — position size rounds to 0 shares")
            continue
        if capital_used + position_size > account_size:
            print(f"    {ticker:<7} skipped — would exceed remaining account capital")
            continue

        price_note = (
            f" (detected at ${c['breakout_price']:.2f})" if abs(current_price - c["breakout_price"]) > 0.01 else ""
        )
        reason = (
            f"{c['pattern_type']}/{c['pattern_grade']} breakout{price_note}, filled at ${current_price:.2f} "
            f"(pivot ${c['pivot_price']:.2f}), {c['volume_ratio']:.1f}x avg volume. "
            f"Target R:R {c['suggested_rr_ratio']}:1. {c.get('qualification_reasons') or ''}"
        ).strip()

        print(f"    {ticker:<7} BUY {shares} @ ${current_price:.2f}{price_note} (${position_size:,.0f}, "
              f"{sized['binding_rule']}){' [DRY RUN]' if dry_run else ''}")
        if not dry_run:
            insert_paper_trade({
                "ticker": ticker,
                "shares": shares,
                "entry_price": current_price,
                "entry_date": today,
                "entry_reason": reason,
                "pattern_type": c["pattern_type"],
                "pattern_grade": c["pattern_grade"],
                "stop_price": stop_price,
                "risk_per_share": risk_per_share,
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

    target_date = _today_est()
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
