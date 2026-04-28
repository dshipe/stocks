#!/usr/bin/env python3
"""
breakout_scanner.py — Intraday breakout detector.

Runs every 30 minutes during market hours (9:30 AM – 4:00 PM EST) via cron.
Reads today's watchlist from SQL Server and checks each stock for an active breakout.

Breakout = price above pivot + volume >= 150% of 20d avg + candle near its high.
Deduplicates: will not re-alert a stock that already broke out today.

Usage:
    python breakout_scanner.py
    python breakout_scanner.py --force      # run even if market is closed (testing)
    python breakout_scanner.py --dry-run    # print without writing to DB
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import json
import logging
from datetime import date, datetime

try:
    import pytz
    eastern = pytz.timezone("America/New_York")
    now_est = datetime.now(eastern)
except ImportError:
    from datetime import timezone, timedelta
    now_est = datetime.utcnow() - timedelta(hours=4)  # rough EDT offset

import config as cfg
from shared.data_fetcher import fetch_history, fetch_intraday, compute_indicators, is_market_open
from shared.criteria import (
    check_universe_filter,
    find_prior_explosive_move,
    find_consolidation_base,
    check_volume_contraction,
    check_breakout,
    build_qualification_reasons,
    detect_pattern_type,
    grade_setup,
)
from shared.telegram_notify import send_breakout_alert, send_breakout_scan_summary
from shared.db_writer import (
    get_todays_watchlist,
    breakout_already_logged_today,
    insert_breakout_entry,
    test_connection,
)

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Market Context ────────────────────────────────────────────────────────────

def get_sp500_context() -> dict:
    """
    Fetch current S&P 500 (SPY) trend for market condition context.
    Returns dict with above_50d_ma and above_200d_ma flags.
    """
    try:
        from shared.data_fetcher import fetch_history, compute_indicators
        df = fetch_history("SPY", days=250)
        if df is None:
            return {}
        df = compute_indicators(df)
        last = df.iloc[-1]
        close = float(last["Close"])
        return {
            "sp500_above_50d_ma":  close > float(last["ma50"])  if last["ma50"]  else None,
            "sp500_above_200d_ma": close > float(last["ma50"])  if last["ma50"]  else None,
        }
    except Exception:
        return {}


def send_notification(ticker: str, breakout: dict, entry: dict) -> None:
    """
    Send breakout alert via Telegram (and optionally Twilio SMS if configured).
    """
    # Telegram — always attempt
    send_breakout_alert({
        "ticker":             ticker,
        "breakout_price":     breakout.get("breakout_price"),
        "pivot_price":        breakout.get("pivot_price"),
        "volume_ratio":       breakout.get("volume_ratio"),
        "pattern_type":       entry.get("pattern_type", ""),
        "pattern_grade":      entry.get("pattern_grade", ""),
        "prior_move_pct":     entry.get("prior_move_pct", 0),
        "prior_move_days":    entry.get("prior_move_days", 0),
        "stop_price":         entry.get("stop_price"),
        "suggested_rr_ratio": entry.get("suggested_rr_ratio"),
    })

    # Twilio SMS — only if credentials are configured
    if not (cfg.TWILIO_SID and cfg.TWILIO_TOKEN and cfg.NOTIFY_PHONE):
        return
    try:
        from twilio.rest import Client
        client = Client(cfg.TWILIO_SID, cfg.TWILIO_TOKEN)
        msg = (
            f"BREAKOUT: {ticker} ({entry.get('pattern_type','')}/{entry.get('pattern_grade','')})
"
            f"Price: ${breakout['breakout_price']:.2f} | Pivot: ${breakout['pivot_price']:.2f}
"
            f"Vol: {breakout['volume_ratio']:.1f}x avg"
        )
        client.messages.create(body=msg, from_=cfg.TWILIO_FROM, to=cfg.NOTIFY_PHONE)
        logger.info(f"SMS sent for {ticker} breakout")
    except Exception as e:
        logger.warning(f"Twilio SMS failed for {ticker}: {e}")


# ─── Main Scanner ──────────────────────────────────────────────────────────────

def check_ticker_breakout(watchlist_entry: dict) -> dict | None:
    """
    Check a single watchlist ticker for an active intraday breakout.

    Returns a breakout result dict or None if no breakout.
    """
    ticker = watchlist_entry["ticker"]
    pivot_price = watchlist_entry.get("pivot_price")

    # Fetch intraday snapshot
    intraday = fetch_intraday(ticker)
    if intraday is None:
        return None

    # Fetch daily history for indicator context
    df = fetch_history(ticker, days=60)
    if df is None:
        return None
    df = compute_indicators(df)
    last = df.iloc[-1]

    avg_vol_20d = float(last["avg_vol_20d"]) if not hasattr(last["avg_vol_20d"], 'isna') or not last["avg_vol_20d"] != last["avg_vol_20d"] else 0

    # Reconstruct base from daily data for breakout check
    prior_move = find_prior_explosive_move(df)
    if prior_move is None:
        return None

    base = find_consolidation_base(df, prior_move["peak_date"])
    if base is None:
        # Fall back to watchlist pivot price if base detection fails
        if pivot_price:
            base = {"pivot_price": pivot_price, "base_low": pivot_price * 0.90,
                    "base_depth_pct": 8, "base_duration_days": 10,
                    "above_50d_ma": True, "ma10_above_ma20": True}
        else:
            return None

    # Override pivot with watchlist value if available (more accurate at 8 AM)
    if pivot_price:
        base["pivot_price"] = pivot_price

    # Stage 5: Breakout check
    breakout = check_breakout(intraday, base, avg_vol_20d)
    if breakout is None:
        return None

    # Build full entry for DB
    vol_contraction = check_volume_contraction(df, base.get("base_start_date", df.index[-20].date()))
    if vol_contraction is None:
        vol_contraction = {"contraction_ratio": 0.5, "consecutive_low_vol_days": 3, "avg_vol_50d": avg_vol_20d}

    pattern_type = watchlist_entry.get("pattern_type") or detect_pattern_type(df, base)
    grade        = watchlist_entry.get("pattern_grade") or grade_setup(prior_move, base, vol_contraction, pattern_type)

    reasons_json = build_qualification_reasons(
        prior_move, base, vol_contraction, pattern_type, grade
    )

    # Compute stop and R/R
    stop_price     = round(base.get("base_low", breakout["breakout_price"] * 0.95) * 0.995, 4)
    risk_per_share = round(breakout["breakout_price"] - stop_price, 4)
    rr_ratio       = round((breakout["breakout_price"] * 0.15) / risk_per_share, 2) if risk_per_share > 0 else 0

    # Get market context
    sp500_ctx = get_sp500_context()

    return {
        "scan_date":                date.today(),
        "ticker":                   ticker,
        "breakout_price":           breakout["breakout_price"],
        "pivot_price":              breakout["pivot_price"],
        "breakout_volume":          breakout["breakout_volume"],
        "avg_volume_20d":           int(avg_vol_20d),
        "volume_ratio":             breakout["volume_ratio"],
        "candle_close_pct":         breakout["candle_close_pct"],
        "prior_move_pct":           prior_move["move_pct"],
        "prior_move_days":          prior_move["move_days"],
        "base_depth_pct":           base.get("base_depth_pct"),
        "base_duration_days":       base.get("base_duration_days"),
        "volume_contraction_ratio": vol_contraction.get("contraction_ratio"),
        "adr_pct":                  float(last["adr_pct"]) if not last["adr_pct"] != last["adr_pct"] else None,
        "avg_daily_volume":         int(avg_vol_20d),
        "ma10_above_ma20":          base.get("ma10_above_ma20", True),
        "above_50d_ma":             base.get("above_50d_ma", True),
        "stop_price":               stop_price,
        "atr_14":                   float(last["atr_14"]) if not last["atr_14"] != last["atr_14"] else None,
        "risk_per_share":           risk_per_share,
        "suggested_rr_ratio":       rr_ratio,
        "pattern_type":             pattern_type,
        "pattern_grade":            grade,
        "is_episodic_pivot":        False,
        "catalyst_notes":           None,
        "sp500_above_50d_ma":       sp500_ctx.get("sp500_above_50d_ma"),
        "sp500_above_200d_ma":      sp500_ctx.get("sp500_above_200d_ma"),
        "vix_level":                None,
        "sector_trend":             None,
        "qualification_reasons":    reasons_json,
        "was_on_watchlist":         True,
        "watchlist_entry_id":       watchlist_entry["watchlist_entry_id"],
        # Display-only
        "_pct_above_pivot":         breakout["pct_above_pivot"],
    }


def main():
    parser = argparse.ArgumentParser(description="Intraday breakout scanner (watchlist-only)")
    parser.add_argument("--force",   action="store_true", help="Run even if market is closed")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing to DB")
    args = parser.parse_args()

    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    except Exception:
        now_str = str(date.today())

    print(f"\n{'='*65}")
    print(f"  BREAKOUT SCAN — {now_str} EST")
    print(f"{'='*65}")

    # Check market hours
    if not args.force and not is_market_open():
        print("  Market is closed. Exiting.\n")
        logger.info("Market closed — breakout scanner exiting.")
        sys.exit(0)

    # Verify DB connection
    if not args.dry_run:
        if not test_connection():
            logger.error("Cannot connect to SQL Server. Use --dry-run to test without DB.")
            sys.exit(1)

    # Load today's watchlist
    watchlist = get_todays_watchlist()
    if not watchlist:
        print("  No watchlist for today. Run watchlist_scanner.py first.\n")
        logger.info("No watchlist entries found for today — exiting.")
        sys.exit(0)

    print(f"  Watchlist stocks to check: {len(watchlist)}\n")

    # Track results
    new_breakouts = []
    already_alerted = []
    no_trigger = []

    for entry in watchlist:
        ticker = entry["ticker"]

        # Skip if already logged today
        if not args.dry_run and breakout_already_logged_today(ticker):
            already_alerted.append(ticker)
            continue

        try:
            result = check_ticker_breakout(entry)
            if result:
                new_breakouts.append(result)
                print(
                    f"  ✅ BREAKOUT: {ticker:<8} "
                    f"${result['breakout_price']:.2f} | "
                    f"Vol: {result['volume_ratio']:.1f}x | "
                    f"+{result['_pct_above_pivot']:.1f}% above pivot | "
                    f"{result['pattern_type']}/{result['pattern_grade']}"
                )

                if not args.dry_run:
                    row_id = insert_breakout_entry(
                        {k: v for k, v in result.items() if not k.startswith("_")}
                    )
                    if row_id:
                        logger.info(f"Wrote breakout for {ticker} (id={row_id})")
                        send_notification(ticker, {"breakout_price": result["breakout_price"],
                                                   "pivot_price": result["pivot_price"],
                                                   "volume_ratio": result["volume_ratio"],
                                                   "pct_above_pivot": result["_pct_above_pivot"]},
                                          result)
            else:
                no_trigger.append(ticker)

        except Exception as e:
            logger.warning(f"Error checking {ticker}: {e}")
            no_trigger.append(ticker)

    # Summary
    print(f"\n  {'─'*55}")
    print(f"  Stocks checked       : {len(watchlist)}")
    print(f"  New breakouts        : {len(new_breakouts)}")
    print(f"  Already alerted today: {len(already_alerted)}")
    print(f"  No trigger yet       : {len(no_trigger)}")
    if already_alerted:
        print(f"  Previously alerted   : {', '.join(already_alerted)}")
    if no_trigger:
        print(f"  Still watching       : {', '.join(no_trigger)}")
    print()

    if args.dry_run:
        print("  [DRY RUN] No data written to database.\n")


if __name__ == "__main__":
    main()
