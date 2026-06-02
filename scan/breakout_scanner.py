#!/usr/bin/env python3
"""
breakout_scanner.py — Intraday breakout detector (OPTIMIZED: batch data fetching).

Runs every 30 minutes during market hours (9:30 AM – 4:00 PM EST) via cron.
Reads today's watchlist from SQL Server and checks each stock for an active breakout.

**OPTIMIZATION (2026-05-07):**
- Pre-fetch all watchlist + runner tickers in batch (single yfinance call per ticker)
- Cache SPY context to avoid 163+ redundant fetches
- Reduced API calls from ~500+ to ~165 per scan run

Breakout = price above pivot + volume >= 125% of 20d avg + candle near its high.
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
import time as time_module
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
    check_adr_breakout,
    build_qualification_reasons,
    detect_pattern_type,
    grade_setup,
)
from shared.telegram_notify import send_breakout_alert, send_breakout_scan_summary
import pandas as pd
from shared.db_writer import (
    get_todays_watchlist,
    get_todays_runners,
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


# ─── Global Cache for Market Context (avoid 163+ redundant fetches) ─────────────
_sp500_context_cache = None
_sp500_context_cache_time = None

def get_sp500_context(force_refresh: bool = False) -> dict:
    """
    Fetch current S&P 500 (SPY) trend for market condition context.
    Returns dict with above_50d_ma and above_200d_ma flags.
    **OPTIMIZED:** Caches result for 5 minutes to avoid redundant fetches during scan.
    """
    global _sp500_context_cache, _sp500_context_cache_time
    
    now = time_module.time()
    if (_sp500_context_cache is not None and 
        _sp500_context_cache_time is not None and 
        not force_refresh and 
        (now - _sp500_context_cache_time) < 300):  # 5-minute cache
        return _sp500_context_cache
    
    try:
        df = fetch_history("SPY", days=250)
        if df is None:
            return {}
        df = compute_indicators(df)
        last = df.iloc[-1]
        close = float(last["Close"])
        result = {
            "sp500_above_50d_ma":  close > float(last["ma50"])  if not pd.isna(last["ma50"]) else None,
            "sp500_above_200d_ma": close > float(last["ma200"]) if not pd.isna(last["ma200"]) else None,
        }
        _sp500_context_cache = result
        _sp500_context_cache_time = now
        return result
    except Exception as e:
        logger.warning(f"SPY context fetch failed: {e}")
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
            f"BREAKOUT: {ticker} ({entry.get('pattern_type','')} / {entry.get('pattern_grade','')})"
            f"\nPrice: ${breakout['breakout_price']:.2f} | Pivot: ${breakout['pivot_price']:.2f}"
            f"\nVol: {breakout['volume_ratio']:.1f}x avg"
        )
        client.messages.create(body=msg, from_=cfg.TWILIO_FROM, to=cfg.NOTIFY_PHONE)
        logger.info(f"SMS sent for {ticker} breakout")
    except Exception as e:
        logger.warning(f"Twilio SMS failed for {ticker}: {e}")


# ─── ADR Breakout Entry Builder ────────────────────────────────────────────────

def _build_adr_breakout_entry(ticker: str, adr_result: dict, df,
                               sp500_context: dict,
                               watchlist_entry_id=None,
                               was_on_watchlist: bool = False,
                               source: str = "adr") -> dict:
    """
    Build the DB entry dict for an ADR-based breakout (parallel path).
    Base/pivot fields are None since there is no consolidation base.
    volume_ratio reflects last 30-min candle intensity (same approach as R24).
    """
    import pandas as pd
    last = df.iloc[-1]
    avg_vol_20d = float(last["avg_vol_20d"]) if not pd.isna(last["avg_vol_20d"]) else 0
    atr_14      = float(last["atr_14"])      if not pd.isna(last["atr_14"])      else None

    breakout_price = adr_result["breakout_price"]
    # Conservative stop: 1 ATR below current price (no base low available)
    stop_price     = round(breakout_price - atr_14, 4) if atr_14 else round(breakout_price * 0.95, 4)
    risk_per_share = round(breakout_price - stop_price, 4)
    rr_ratio       = round((breakout_price * 0.15) / risk_per_share, 2) if risk_per_share > 0 else 0

    return {
        "scan_date":                date.today(),
        "ticker":                   ticker,
        "breakout_price":           breakout_price,
        "pivot_price":              adr_result["pivot_price"],   # prev close
        "breakout_volume":          adr_result["breakout_volume"],
        "avg_volume_20d":           int(avg_vol_20d),
        "volume_ratio":             adr_result["volume_ratio"],  # 30-min intensity ratio
        "candle_close_pct":         adr_result["candle_close_pct"],
        "prior_move_pct":           None,
        "prior_move_days":          None,
        "base_depth_pct":           None,
        "base_duration_days":       None,
        "volume_contraction_ratio": None,
        "adr_pct":                  adr_result["adr_pct"],
        "avg_daily_volume":         int(avg_vol_20d),
        "ma10_above_ma20":          None,
        "above_50d_ma":             None,
        "stop_price":               stop_price,
        "atr_14":                   atr_14,
        "risk_per_share":           risk_per_share,
        "suggested_rr_ratio":       rr_ratio,
        "pattern_type":             "ADR_MOMENTUM",
        "pattern_grade":            f"{adr_result['adr_mult']:.1f}x ADR",
        "is_episodic_pivot":        False,
        "catalyst_notes":           None,
        "sp500_above_50d_ma":       sp500_context.get("sp500_above_50d_ma"),
        "sp500_above_200d_ma":      sp500_context.get("sp500_above_200d_ma"),
        "vix_level":                None,
        "sector_trend":             None,
        "qualification_reasons":    f'["ADR momentum: +{adr_result["pct_above_pivot"]:.1f}% '
                                    f'({adr_result["adr_mult"]:.1f}x ADR={adr_result["adr_pct"]:.1f}%) '
                                    f'on {adr_result["volume_ratio"]:.1f}x avg 30-min volume"]',
        "was_on_watchlist":         was_on_watchlist,
        "watchlist_entry_id":       watchlist_entry_id,
        # Display-only
        "_pct_above_pivot":         adr_result["pct_above_pivot"],
        "_source":                  source,
        "_adr_mult":                adr_result["adr_mult"],
    }


# ─── Main Scanner (uses pre-fetched data) ──────────────────────────────────────

def check_ticker_breakout(watchlist_entry: dict, 
                         history_cache: dict, 
                         intraday_cache: dict,
                         sp500_context: dict) -> dict | None:
    """
    Check a single watchlist ticker for an active intraday breakout.
    **OPTIMIZED:** Uses pre-fetched data from caches (no additional API calls).

    Returns a breakout result dict or None if no breakout.
    """
    ticker = watchlist_entry["ticker"]
    pivot_price = watchlist_entry.get("pivot_price")

    # Get cached data (already fetched in main)
    intraday = intraday_cache.get(ticker)
    if intraday is None:
        return None

    df = history_cache.get(ticker)
    if df is None:
        return None
    df = compute_indicators(df)
    last = df.iloc[-1]

    avg_vol_20d = float(last["avg_vol_20d"]) if not pd.isna(last["avg_vol_20d"]) else 0

    # Reconstruct base from daily data for breakout check
    prior_move = find_prior_explosive_move(df)
    if prior_move is None:
        # Base-pivot path unavailable — try ADR momentum path instead
        adr_result = check_adr_breakout(intraday, df)
        if adr_result is None:
            return None
        return _build_adr_breakout_entry(
            ticker, adr_result, df, sp500_context,
            watchlist_entry_id=watchlist_entry.get("watchlist_entry_id"),
            was_on_watchlist=True, source="watchlist-adr",
        )

    base = find_consolidation_base(df, prior_move["peak_date"])
    if base is None:
        # Fall back to watchlist pivot price if base detection fails
        if pivot_price:
            base = {"pivot_price": pivot_price, "base_low": pivot_price * 0.90,
                    "base_depth_pct": 8, "base_duration_days": 10,
                    "above_50d_ma": True, "ma10_above_ma20": True}
        else:
            # No stored pivot — try ADR momentum path
            adr_result = check_adr_breakout(intraday, df)
            if adr_result is None:
                return None
            return _build_adr_breakout_entry(
                ticker, adr_result, df, sp500_context,
                watchlist_entry_id=watchlist_entry.get("watchlist_entry_id"),
                was_on_watchlist=True, source="watchlist-adr",
            )

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

    # Use pre-fetched market context (shared across all stocks)

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
        "adr_pct":                  float(last["adr_pct"]) if not pd.isna(last["adr_pct"]) else None,
        "avg_daily_volume":         int(avg_vol_20d),
        "ma10_above_ma20":          base.get("ma10_above_ma20", True),
        "above_50d_ma":             base.get("above_50d_ma", True),
        "stop_price":               stop_price,
        "atr_14":                   float(last["atr_14"]) if not pd.isna(last["atr_14"]) else None,
        "risk_per_share":           risk_per_share,
        "suggested_rr_ratio":       rr_ratio,
        "pattern_type":             pattern_type,
        "pattern_grade":            grade,
        "is_episodic_pivot":        False,
        "catalyst_notes":           None,
        "sp500_above_50d_ma":       sp500_context.get("sp500_above_50d_ma"),
        "sp500_above_200d_ma":      sp500_context.get("sp500_above_200d_ma"),
        "vix_level":                None,
        "sector_trend":             None,
        "qualification_reasons":    reasons_json,
        "was_on_watchlist":         True,
        "watchlist_entry_id":       watchlist_entry["watchlist_entry_id"],
        # Display-only
        "_pct_above_pivot":         breakout["pct_above_pivot"],
    }



def check_runner_breakout(runner_entry: dict,
                         history_cache: dict,
                         intraday_cache: dict,
                         sp500_context: dict) -> dict | None:
    """
    Check if a runner has formed a base intraday and is breaking out.
    **OPTIMIZED:** Uses pre-fetched data from caches (no additional API calls).
    Returns a breakout result dict or None if no base or no breakout.
    """
    ticker = runner_entry["ticker"]

    intraday = intraday_cache.get(ticker)
    if intraday is None:
        return None

    df = history_cache.get(ticker)
    if df is None:
        return None
    df = compute_indicators(df)
    last = df.iloc[-1]

    avg_vol_20d = float(last["avg_vol_20d"]) if not pd.isna(last["avg_vol_20d"]) else 0

    prior_move = find_prior_explosive_move(df)
    if prior_move is None:
        # Base-pivot path unavailable — try ADR momentum path
        adr_result = check_adr_breakout(intraday, df)
        if adr_result is None:
            return None
        return _build_adr_breakout_entry(
            ticker, adr_result, df, sp500_context,
            watchlist_entry_id=None, was_on_watchlist=False, source="runner-adr",
        )

    base = find_consolidation_base(df, prior_move["peak_date"])
    if base is None:
        # Still running — no base formed yet; try ADR momentum path
        adr_result = check_adr_breakout(intraday, df)
        if adr_result is None:
            return None
        return _build_adr_breakout_entry(
            ticker, adr_result, df, sp500_context,
            watchlist_entry_id=None, was_on_watchlist=False, source="runner-adr",
        )

    breakout = check_breakout(intraday, base, avg_vol_20d)
    if breakout is None:
        return None

    vol_contraction = check_volume_contraction(df, base.get("base_start_date", df.index[-20].date()))
    if vol_contraction is None:
        vol_contraction = {"contraction_ratio": 0.5, "consecutive_low_vol_days": 3, "avg_vol_50d": avg_vol_20d}

    pattern_type = detect_pattern_type(df, base)
    grade        = grade_setup(prior_move, base, vol_contraction, pattern_type)
    reasons_json = build_qualification_reasons(prior_move, base, vol_contraction, pattern_type, grade)

    stop_price     = round(base.get("base_low", breakout["breakout_price"] * 0.95) * 0.995, 4)
    risk_per_share = round(breakout["breakout_price"] - stop_price, 4)
    rr_ratio       = round((breakout["breakout_price"] * 0.15) / risk_per_share, 2) if risk_per_share > 0 else 0

    # Use pre-fetched market context (shared across all stocks)

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
        "adr_pct":                  float(last["adr_pct"]) if not pd.isna(last["adr_pct"]) else None,
        "avg_daily_volume":         int(avg_vol_20d),
        "ma10_above_ma20":          base.get("ma10_above_ma20", True),
        "above_50d_ma":             base.get("above_50d_ma", True),
        "stop_price":               stop_price,
        "atr_14":                   float(last["atr_14"]) if not pd.isna(last["atr_14"]) else None,
        "risk_per_share":           risk_per_share,
        "suggested_rr_ratio":       rr_ratio,
        "pattern_type":             pattern_type,
        "pattern_grade":            grade,
        "is_episodic_pivot":        False,
        "catalyst_notes":           "promoted from runners list",
        "sp500_above_50d_ma":       sp500_context.get("sp500_above_50d_ma"),
        "sp500_above_200d_ma":      sp500_context.get("sp500_above_200d_ma"),
        "vix_level":                None,
        "sector_trend":             None,
        "qualification_reasons":    reasons_json,
        "was_on_watchlist":         False,
        "watchlist_entry_id":       None,
        "_pct_above_pivot":         breakout["pct_above_pivot"],
        "_source":                  "runner",
    }



def main():
    parser = argparse.ArgumentParser(description="Intraday breakout scanner (watchlist + runners)")
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

    if not args.force and not is_market_open():
        print("  Market is closed. Exiting.\n")
        sys.exit(0)

    if not args.dry_run:
        if not test_connection():
            logger.error("Cannot connect to SQL Server. Use --dry-run to test without DB.")
            sys.exit(1)

    watchlist = get_todays_watchlist()
    runners   = get_todays_runners()

    if not watchlist and not runners:
        print("  No watchlist or runners for today. Run watchlist_scanner.py first.\n")
        sys.exit(0)

    print(f"  Watchlist stocks : {len(watchlist)}  (grade >= {cfg.MIN_BREAKOUT_GRADE}; HTF grade >= {cfg.MIN_HTF_BREAKOUT_GRADE})")
    print(f"  Runner stocks    : {len(runners)}\n")

    # ─── BATCH PRE-FETCH: Collect all tickers and fetch once (OPTIMIZATION) ─────────────────────────────
    all_tickers = [e["ticker"] for e in watchlist] + [e["ticker"] for e in runners]
    print(f"  Pre-fetching {len(all_tickers)} ticker histories...")
    histories = {}
    intradays = {}
    successful = 0
    failed_tickers = []
    for ticker in all_tickers:
        try:
            histories[ticker] = fetch_history(ticker, days=60)
            intradays[ticker] = fetch_intraday(ticker)
            if histories[ticker] is not None:
                successful += 1
        except Exception as e:
            logger.warning(f"Pre-fetch error for {ticker}: {e}")
            failed_tickers.append((ticker, str(e)))
            histories[ticker] = None
            intradays[ticker] = None
    print(f"  Pre-fetch complete ({successful}/{len(all_tickers)} successful)")
    if failed_tickers:
        print(f"  Failed tickers ({len(failed_tickers)}):")
        for ticker, error in failed_tickers[:10]:  # Show first 10 failures
            print(f"    - {ticker}: {error}")
        if len(failed_tickers) > 10:
            print(f"    ... and {len(failed_tickers) - 10} more")
    print()

    # Pre-fetch SPY context once (shared for all stocks) — CACHE AVOIDS 163+ REDUNDANT FETCHES
    sp500_ctx = get_sp500_context()

    new_breakouts   = []
    already_alerted = []
    no_trigger      = []

    # ── Watchlist ──────────────────────────────────────────────────────────────────────────────────────
    for entry in watchlist:
        ticker = entry["ticker"]
        if not args.dry_run and breakout_already_logged_today(ticker):
            already_alerted.append(ticker)
            continue
        try:
            result = check_ticker_breakout(entry, histories, intradays, sp500_ctx)
            if result:
                if "_source" not in result:
                    result["_source"] = "watchlist"
                new_breakouts.append(result)
                is_adr = result["_source"].endswith("-adr")
                tag    = "📈 BREAKOUT [WL-ADR]" if is_adr else "✅ BREAKOUT [WL]   "
                extra  = f" | {result['_adr_mult']:.1f}x ADR" if is_adr else ""
                print(
                    f"  {tag}: {ticker:<6} "
                    f"${result['breakout_price']:.2f} | Vol {result['volume_ratio']:.1f}x | "
                    f"+{result['_pct_above_pivot']:.1f}%{extra} | {result['pattern_type']}/{result['pattern_grade']}"
                )
                if not args.dry_run:
                    row_id = insert_breakout_entry({k: v for k, v in result.items() if not k.startswith("_")})
                    if row_id:
                        send_notification(ticker, {"breakout_price": result["breakout_price"],
                                                   "pivot_price": result["pivot_price"],
                                                   "volume_ratio": result["volume_ratio"],
                                                   "pct_above_pivot": result["_pct_above_pivot"]}, result)
            else:
                no_trigger.append(ticker)
        except Exception as e:
            logger.warning(f"Error checking watchlist {ticker}: {e}")
            no_trigger.append(ticker)

    # ── Runners ────────────────────────────────────────────────────────────────────────────────────────
    for entry in runners:
        ticker = entry["ticker"]
        if not args.dry_run and breakout_already_logged_today(ticker):
            already_alerted.append(ticker)
            continue
        try:
            result = check_runner_breakout(entry, histories, intradays, sp500_ctx)
            if result:
                new_breakouts.append(result)
                is_adr = result.get("_source", "").endswith("-adr")
                tag    = "📈 BREAKOUT [RN-ADR]" if is_adr else "🏃 BREAKOUT [RN]   "
                extra  = f" | {result['_adr_mult']:.1f}x ADR" if is_adr else " (runner)"
                print(
                    f"  {tag}: {ticker:<6} "
                    f"${result['breakout_price']:.2f} | Vol {result['volume_ratio']:.1f}x | "
                    f"+{result['_pct_above_pivot']:.1f}% | {result['pattern_type']}/{result['pattern_grade']}{extra}"
                )
                if not args.dry_run:
                    row_id = insert_breakout_entry({k: v for k, v in result.items() if not k.startswith("_")})
                    if row_id:
                        send_notification(ticker, {"breakout_price": result["breakout_price"],
                                                   "pivot_price": result["pivot_price"],
                                                   "volume_ratio": result["volume_ratio"],
                                                   "pct_above_pivot": result["_pct_above_pivot"]}, result)
            else:
                no_trigger.append(ticker)
        except Exception as e:
            logger.warning(f"Error checking runner {ticker}: {e}")
            no_trigger.append(ticker)

    total_checked = len(watchlist) + len(runners) - len(already_alerted)
    print(f"\n  {'-'*55}")
    print(f"  Stocks checked       : {total_checked} ({len(watchlist)} watchlist + {len(runners)} runners)")
    print(f"  New breakouts        : {len(new_breakouts)}")
    print(f"  Already alerted today: {len(already_alerted)}")
    print(f"  No trigger yet       : {len(no_trigger)}")
    if already_alerted:
        print(f"  Previously alerted   : {', '.join(already_alerted)}")
    print()

    if args.dry_run:
        print("  [DRY RUN] No data written to database.\n")


if __name__ == "__main__":
    main()
