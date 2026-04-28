"""
telegram_notify.py — Send scan results to Telegram.

Uses the OpenClaw bot token directly via the Telegram Bot API.
No external dependencies beyond `requests` (already required).
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8755401792:AAGdauh5m-BawSjNPkvFFalxfl1xdKQR8zY"
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8768764006")

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def _send(text: str) -> bool:
    """Send a plain message to the configured Telegram chat."""
    try:
        resp = requests.post(API_URL, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


# ─── Watchlist Summary ────────────────────────────────────────────────────────

def send_watchlist_summary(scan_date: str, results: list, stats: dict) -> bool:
    """
    Send the daily watchlist scan summary to Telegram.

    Args:
        scan_date: e.g. '2026-04-27'
        results: list of dicts with ticker, pattern_grade, price_at_scan,
                 pivot_price, distance_to_pivot_pct, pattern_type, prior_move_pct,
                 prior_move_days
        stats: dict with keys: total, stage1, stage2, stage3, stage4
    """
    if not results:
        msg = (
            f"📋 <b>Watchlist Scan — {scan_date}</b>\n\n"
            f"No stocks met all criteria today.\n\n"
            f"Scanned: {stats.get('total', 0)} | "
            f"Stage1: {stats.get('stage1', 0)} | "
            f"Stage2: {stats.get('stage2', 0)} | "
            f"Stage3: {stats.get('stage3', 0)} | "
            f"Stage4: {stats.get('stage4', 0)}"
        )
        return _send(msg)

    lines = [f"📋 <b>Watchlist — {scan_date}</b>  ({len(results)} setup{'s' if len(results) != 1 else ''})\n"]

    for r in results:
        grade     = r.get("pattern_grade", "?")
        ticker    = r.get("ticker", "?")
        price     = r.get("price_at_scan") or r.get("price", 0)
        pivot     = r.get("pivot_price", 0)
        away      = r.get("distance_to_pivot_pct") or r.get("pct_from_pivot", 0)
        pattern   = r.get("pattern_type", "")
        move_pct  = r.get("prior_move_pct", 0)
        move_days = r.get("prior_move_days", 0)

        grade_emoji = {"A+": "🔥", "A": "⭐", "B": "👍", "C": "👀"}.get(grade, "•")

        lines.append(
            f"{grade_emoji} <b>{ticker}</b>  [{grade}]  {pattern}\n"
            f"   Price ${price:.2f} → Pivot ${pivot:.2f}  ({away:.1f}% away)\n"
            f"   Prior move: +{move_pct:.0f}% in {move_days}d\n"
        )

    lines.append(
        f"\n<i>Scanned {stats.get('total', 0)} tickers — "
        f"S1:{stats.get('stage1',0)}  S2:{stats.get('stage2',0)}  "
        f"S3:{stats.get('stage3',0)}  S4:{stats.get('stage4',0)}</i>"
    )

    return _send("\n".join(lines))


# ─── Breakout Alert ───────────────────────────────────────────────────────────

def send_breakout_alert(breakout: dict) -> bool:
    """
    Send a single breakout alert to Telegram.

    Args:
        breakout: dict with ticker, breakout_price, pivot_price, volume_ratio,
                  pattern_type, pattern_grade, prior_move_pct, prior_move_days,
                  stop_price, suggested_rr_ratio
    """
    ticker    = breakout.get("ticker", "?")
    price     = breakout.get("breakout_price", 0)
    pivot     = breakout.get("pivot_price", 0)
    vol_ratio = breakout.get("volume_ratio", 0)
    pattern   = breakout.get("pattern_type", "")
    grade     = breakout.get("pattern_grade", "?")
    move_pct  = breakout.get("prior_move_pct", 0)
    move_days = breakout.get("prior_move_days", 0)
    stop      = breakout.get("stop_price")
    rr        = breakout.get("suggested_rr_ratio")

    grade_emoji = {"A+": "🔥", "A": "⭐", "B": "👍", "C": "👀"}.get(grade, "•")

    stop_line = f"   Stop: ${stop:.2f}" if stop else ""
    rr_line   = f"  |  R/R: {rr:.1f}:1" if rr else ""

    msg = (
        f"🚨 <b>BREAKOUT — {ticker}</b>  {grade_emoji} [{grade}]\n\n"
        f"   Price: <b>${price:.2f}</b>  (pivot ${pivot:.2f})\n"
        f"   Volume: {vol_ratio:.1f}× avg\n"
        f"   Pattern: {pattern}  |  Prior move: +{move_pct:.0f}% / {move_days}d\n"
        f"{stop_line}{rr_line}"
    )

    return _send(msg.strip())


# ─── Breakout Scan Summary (end of day / no breakouts) ───────────────────────

def send_breakout_scan_summary(scan_date: str, watchlist_count: int, breakout_count: int) -> bool:
    """Send a brief end-of-scan summary when the breakout scanner finishes with no new alerts."""
    if breakout_count > 0:
        return True  # individual alerts already sent
    msg = (
        f"🔍 <b>Breakout Scan — {scan_date}</b>\n"
        f"Monitored {watchlist_count} watchlist stock{'s' if watchlist_count != 1 else ''}. "
        f"No breakouts triggered this run."
    )
    return _send(msg)
