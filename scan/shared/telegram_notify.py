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

API_URL   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
MAX_CHARS = 4000   # Telegram hard limit is 4096 — leave headroom


def _send(text: str) -> bool:
    """Send a single message (must be ≤ MAX_CHARS) to the configured Telegram chat."""
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


def _send_chunked(text: str) -> bool:
    """
    Send text to Telegram, splitting into multiple messages if needed.

    Splits on blank lines (natural stock-entry boundaries) so entries
    are never cut mid-block.  Continues sending remaining chunks even
    if one fails, and returns False if any chunk failed.
    """
    if len(text) <= MAX_CHARS:
        return _send(text)

    # Split on double-newlines (blank lines between stock entries)
    paragraphs = text.split("\n\n")
    chunks  = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para).lstrip("\n") if current else para
        if len(candidate) > MAX_CHARS:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    success = True
    for i, chunk in enumerate(chunks, 1):
        label = f"\n<i>(part {i}/{len(chunks)})</i>" if len(chunks) > 1 else ""
        if not _send(chunk + label):
            success = False
    return success


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

    return _send_chunked("\n".join(lines))




# ─── Runners Summary ──────────────────────────────────────────────────────────────────────────────

def send_runners_summary(scan_date: str, runners: list) -> bool:
    """
    Send a compact runners section to Telegram.

    Called after send_watchlist_summary() on the same scan day.
    Runners are stocks that passed Stage 1+2 but have not yet formed a base.
    """
    if not runners:
        return True

    lines = [f"\U0001f3c3 <b>Runners</b> \u2014 {scan_date}  "
             f"(S1+S2 \u2705, no base yet \u2014 {len(runners)} stocks)\n"]

    for r in sorted(runners, key=lambda x: -x.get("pct_3m", 0)):
        ticker  = r.get("ticker", "?")
        price   = r.get("price_at_scan", 0)
        pct_1m  = r.get("pct_1m", 0)
        pct_3m  = r.get("pct_3m", 0)
        pct_6m  = r.get("pct_6m", 0)
        h52w    = r.get("pct_from_52w_high", 0)
        mv_pct  = r.get("prior_move_pct", 0)
        mv_days = r.get("prior_move_days", 0)

        move_str = f" | prior +{mv_pct:.0f}%/{mv_days}d" if mv_pct else ""
        lines.append(
            f"  <b>{ticker}</b> ${price:.2f}  "
            f"1M:{pct_1m:+.0f}% 3M:{pct_3m:+.0f}% 6M:{pct_6m:+.0f}%  "
            f"-{h52w:.1f}% from 52wH{move_str}\n"
        )

    lines.append("\n<i>These will appear on the watchlist once a base forms.</i>")
    return _send_chunked("".join(lines))

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


# ─── Profit Target Alerts (Rules.MD R36/R38 — alert-only) ────────────────────

def send_profit_target_alert(ticker: str, r_level: float, r_multiple: float,
                              current_price: float, entry_price: float,
                              qty: int, sell_pct: int, action: str) -> bool:
    """
    Alert that an open position has crossed a profit-taking R-level.

    This is alert-only — no order is placed. `action` describes what Rules.MD
    recommends (e.g. "Sell 40%, move stop to breakeven (R36/R37)").
    """
    shares_to_sell = round(qty * sell_pct / 100)
    msg = (
        f"🎯 <b>PROFIT TARGET — {ticker}</b>  {r_level:.0f}R hit ({r_multiple:.1f}R actual)\n\n"
        f"   Entry: ${entry_price:.2f}  →  Now: ${current_price:.2f}\n"
        f"   Position: {qty} shares\n\n"
        f"   <b>{action}</b>\n"
        f"   ≈ {shares_to_sell} of {qty} shares — you place the order manually."
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
