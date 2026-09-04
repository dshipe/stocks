#!/usr/bin/env python3
"""
check_profit_targets.py — Alert (not execute) when an open Schwab position
crosses a Rules.MD profit-taking R-level.

Implements, as alerts only:
    R36/R37 — at 2R profit: sell 1/3-1/2, move stop to breakeven
    R38     — at 3R profit: sell another 1/4 of the original position

This does NOT place any Schwab orders. It reads live equity positions, looks
up each ticker's tracked entry/stop/risk from breakout_entries (the row this
system's own breakout scanner wrote when it detected the setup), computes the
current R-multiple, and sends a Telegram alert the first time a position
crosses 2R or 3R. You place the actual sell order yourself.

R29 (initial stop) and the live 10-day-MA trailing stop (R39) are handled
separately by schwab_stop_loss.py — this script only covers the profit-taking
side (R36-R38), and only as a notification.

A position with no matching breakout_entries row (predates this system, or
wasn't sourced from an alert) is skipped with a note — there's no reliable
way to know its original risk, so no R-multiple can be computed for it.

Usage:
    python check_profit_targets.py
    python check_profit_targets.py --dry-run   # print without sending Telegram / marking DB
"""

import argparse
import logging
import os
import sys

import requests

# ── Path setup so shared/ and config are importable ───────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.db_writer import (
    get_latest_breakout_entry,
    profit_target_already_alerted,
    mark_profit_target_alerted,
)
from shared.data_fetcher import fetch_history, fetch_intraday, is_market_open
from shared.telegram_notify import send_profit_target_alert
from shared.cloudwatch_logging import enable_cloudwatch_logging

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
enable_cloudwatch_logging("check_profit_targets")

# ── Schwab API config (mirrors schwab_stop_loss.py / schwab_watchlist_sync.py) ─
SCHWAB_API_BASE       = "https://api.schwabapi.com/trader/v1"
LAMBDA_TOKEN_ENDPOINT = os.getenv(
    "LAMBDA_TOKEN_ENDPOINT",
    "https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab"
)
LAMBDA_TOKEN_PASSWORD = os.getenv("LAMBDA_TOKEN_PASSWORD", "6#10oz")

# R36/R38: (r_level, % of ORIGINAL position to sell, action text for the alert)
PROFIT_TARGETS = [
    (2.0, 40, "Sell ~40% of position, move stop to breakeven (R36/R37)"),
    (3.0, 25, "Sell another ~25% of ORIGINAL position, trail the rest (R38)"),
]


# ── Schwab auth + positions ────────────────────────────────────────────────────

def get_token() -> str:
    """Fetch a fresh Schwab access token from the Lambda endpoint."""
    r = requests.get(LAMBDA_TOKEN_ENDPOINT, params={"pw": LAMBDA_TOKEN_PASSWORD}, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"Token fetch failed: {r.status_code} — {r.text[:80]}")
    return r.json()["access_token"]


def get_account_hash(h_get: dict) -> str:
    """Return the primary account hash from Schwab."""
    r = requests.get(f"{SCHWAB_API_BASE}/accounts/accountNumbers", headers=h_get, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"accountNumbers failed: {r.status_code} — {r.text[:80]}")
    data = r.json()
    if isinstance(data, dict) or not data:
        raise RuntimeError(f"Unexpected accountNumbers response: {data}")
    return data[0]["hashValue"]


def get_equity_positions(acct_hash: str, h_get: dict) -> list[dict]:
    """Return [{ticker, qty}] for all long equity positions."""
    r = requests.get(
        f"{SCHWAB_API_BASE}/accounts",
        headers=h_get,
        params={"fields": "positions"},
        timeout=10,
    )
    if r.status_code != 200 or isinstance(r.json(), dict):
        raise RuntimeError(f"positions fetch failed: {r.status_code} — {r.text[:80]}")

    positions = []
    for pos in r.json()[0].get("securitiesAccount", {}).get("positions", []):
        if pos.get("instrument", {}).get("assetType") != "EQUITY":
            continue
        if pos.get("longQuantity", 0) <= 0:
            continue
        positions.append({
            "ticker": pos["instrument"]["symbol"],
            "qty":    int(pos["longQuantity"]),
        })
    return positions


def get_current_price(ticker: str) -> float | None:
    """Live price if the market is open, else the latest daily close."""
    if is_market_open():
        intraday = fetch_intraday(ticker)
        if intraday and intraday.get("current_price"):
            return float(intraday["current_price"])
    df = fetch_history(ticker, days=10)
    if df is not None and not df.empty:
        return float(df["Close"].iloc[-1])
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Alert on 2R/3R profit targets for open Schwab positions")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print what would be alerted without sending Telegram or marking the DB")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  PROFIT TARGET CHECK (alert-only — no orders placed)")
    print("=" * 70 + "\n")

    print("Fetching Schwab token + positions...")
    token     = get_token()
    h_get     = {"Authorization": f"Bearer {token}"}
    acct_hash = get_account_hash(h_get)
    positions = get_equity_positions(acct_hash, h_get)
    print(f"{len(positions)} open equity position(s)\n")

    alerts_sent = 0
    for pos in positions:
        ticker, qty = pos["ticker"], pos["qty"]

        entry = get_latest_breakout_entry(ticker)
        if entry is None:
            print(f"{ticker:<8} no tracked breakout entry (stop/risk unknown) — skipping")
            continue

        risk_per_share = entry["risk_per_share"]
        if not risk_per_share or risk_per_share <= 0:
            print(f"{ticker:<8} invalid risk_per_share — skipping")
            continue

        current_price = get_current_price(ticker)
        if current_price is None:
            print(f"{ticker:<8} could not fetch current price — skipping")
            continue

        r_multiple = (current_price - entry["breakout_price"]) / risk_per_share
        print(f"{ticker:<8} entry=${entry['breakout_price']:.2f}  stop=${entry['stop_price']:.2f}  "
              f"now=${current_price:.2f}  R={r_multiple:.2f}")

        for r_level, sell_pct, action in PROFIT_TARGETS:
            if r_multiple < r_level:
                continue
            if profit_target_already_alerted(entry["id"], r_level):
                print(f"         {r_level:.0f}R already alerted — skipping")
                continue

            print(f"         >= {r_level:.0f}R — {'[DRY RUN] would alert' if args.dry_run else 'alerting'}: {action}")
            if not args.dry_run:
                send_profit_target_alert(
                    ticker=ticker, r_level=r_level, r_multiple=r_multiple,
                    current_price=current_price, entry_price=entry["breakout_price"],
                    qty=qty, sell_pct=sell_pct, action=action,
                )
                mark_profit_target_alerted(entry["id"], ticker, r_level, r_multiple)
            alerts_sent += 1

    print(f"\n{'-'*55}")
    print(f"{'[DRY RUN] ' if args.dry_run else ''}{alerts_sent} profit-target alert(s) {'would be ' if args.dry_run else ''}sent")
    print(f"{'-'*55}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
