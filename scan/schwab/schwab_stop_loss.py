#!/usr/bin/env python3
"""
schwab_stop_loss.py — Set / update GTC stop-loss orders at the 10-day SMA.

For every open equity long position in the Schwab account:
  1. Calculate the 10-day Simple Moving Average (SMA) via yfinance
  2. Cancel any existing STOP / STOP_LIMIT GTC order for that ticker
  3. Place a new GTC STOP sell order at the 10-day SMA price

Usage:
    # First run (browser OAuth2 flow):
    python3 schwab_stop_loss.py --auth

    # Normal run:
    python3 schwab_stop_loss.py

    # Preview — no orders placed or cancelled:
    python3 schwab_stop_loss.py --dry-run
"""

import argparse
import os
import sys

# ── Ensure scan/ is on path for config + .env ──────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import schwab
import schwab.auth
import yfinance as yf
from schwab.orders.common import (
    Duration, OrderType, Session, OrderStrategyType, EquityInstruction,
)
from schwab.orders.generic import OrderBuilder

# ── Config ─────────────────────────────────────────────────────────────────
APP_KEY      = os.getenv("SCHWAB_APP_KEY")
APP_SECRET   = os.getenv("SCHWAB_SECRET")
CALLBACK_URL = "https://localhost"
TOKEN_FILE   = os.path.join(os.path.dirname(__file__), "schwab_token.json")

SMA_PERIOD   = 10   # 10-day SMA


def get_client(force_auth: bool = False):
    """Return an authenticated Schwab client.

    If TOKEN_FILE exists (and --auth not forced), load from file.
    Otherwise run the interactive browser OAuth2 flow.
    """
    if not APP_KEY or not APP_SECRET:
        sys.exit("❌  SCHWAB_APP_KEY / SCHWAB_SECRET not set in scan/.env")

    if force_auth or not os.path.exists(TOKEN_FILE):
        print("🔐  Starting OAuth2 login flow — a browser window will open.")
        print("    Log in to Schwab, then paste the redirect URL back here.\n")
        client = schwab.auth.client_from_login_flow(
            api_key=APP_KEY,
            app_secret=APP_SECRET,
            callback_url=CALLBACK_URL,
            token_path=TOKEN_FILE,
        )
    else:
        client = schwab.auth.client_from_token_file(
            token_path=TOKEN_FILE,
            api_key=APP_KEY,
            app_secret=APP_SECRET,
        )
    return client


def get_positions(client) -> list[dict]:
    """Return all open long equity positions across all accounts."""
    resp = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
    resp.raise_for_status()
    positions = []
    for account in resp.json():
        acct = account.get("securitiesAccount", {})
        acct_hash = account.get("hashValue", acct.get("accountNumber", ""))
        for pos in acct.get("positions", []):
            instr = pos.get("instrument", {})
            if instr.get("assetType") != "EQUITY":
                continue
            qty = float(pos.get("longQuantity", 0))
            if qty <= 0:
                continue
            positions.append({
                "account_hash": acct_hash,
                "ticker":       instr["symbol"],
                "qty":          qty,
                "avg_price":    pos.get("averagePrice", 0),
                "market_value": pos.get("marketValue", 0),
                "current_price": pos.get("marketValue", 0) / qty if qty else 0,
            })
    return positions


def get_sma(ticker: str, period: int = SMA_PERIOD) -> float | None:
    """Fetch daily closes via yfinance and return the N-day SMA."""
    df = yf.download(ticker, period=f"{period * 2}d", interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or len(df) < period:
        return None
    closes = df["Close"]
    if hasattr(closes, "iloc"):
        closes = closes.squeeze()
    return round(float(closes.tail(period).mean()), 2)


def get_existing_stops(client, account_hash: str, ticker: str) -> list[dict]:
    """Return all WORKING STOP / STOP_LIMIT GTC orders for this ticker."""
    resp = client.get_orders_for_account(
        account_hash=account_hash,
        status=client.Order.Status.WORKING,
    )
    resp.raise_for_status()
    stops = []
    for order in resp.json():
        if order.get("orderType") not in ("STOP", "STOP_LIMIT"):
            continue
        if order.get("duration") not in ("GOOD_TILL_CANCEL",):
            continue
        legs = order.get("orderLegCollection", [])
        if not legs:
            continue
        if legs[0].get("instrument", {}).get("symbol") != ticker:
            continue
        if legs[0].get("instruction") not in ("SELL", "SELL_SHORT"):
            continue
        stops.append(order)
    return stops


def build_stop_order(ticker: str, qty: int, stop_price: float):
    """Build a GTC STOP sell order."""
    return (
        OrderBuilder()
        .set_order_type(OrderType.STOP)
        .set_session(Session.NORMAL)
        .set_duration(Duration.GOOD_TILL_CANCEL)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .set_stop_price(stop_price)
        .add_equity_leg(EquityInstruction.SELL, ticker, qty)
        .build()
    )


def process_position(client, pos: dict, dry_run: bool):
    """Cancel existing stops and place a new GTC stop at the 10-day SMA."""
    ticker    = pos["ticker"]
    acct_hash = pos["account_hash"]
    qty       = int(pos["qty"])

    sma = get_sma(ticker)
    if sma is None:
        print(f"  {ticker:<8} ⚠️  Could not compute 10d SMA — skipping")
        return

    current = round(pos["current_price"], 2)
    print(f"\n  {ticker:<8}  qty={qty}  current=${current:.2f}  10d SMA=${sma:.2f}")

    # Check SMA is below current price — stop above current price would trigger immediately
    if sma >= current:
        print(f"           ⚠️  SMA (${sma}) >= current price (${current}) — skipping to avoid immediate fill")
        return

    existing = get_existing_stops(client, acct_hash, ticker)

    if dry_run:
        if existing:
            old_stop = existing[0].get("stopPrice", "?")
            print(f"           [DRY RUN] would cancel existing stop @ ${old_stop} → place new @ ${sma}")
        else:
            print(f"           [DRY RUN] would place new GTC stop @ ${sma}")
        return

    # Cancel existing stops
    for order in existing:
        old_stop = order.get("stopPrice", "?")
        resp = client.cancel_order(acct_hash, order["orderId"])
        if resp.status_code in (200, 204):
            print(f"           ✅ cancelled existing stop @ ${old_stop}")
        else:
            print(f"           ⚠️  cancel failed ({resp.status_code}) — proceeding anyway")

    # Place new stop
    order_spec = build_stop_order(ticker, qty, sma)
    resp = client.place_order(acct_hash, order_spec)
    if resp.status_code in (200, 201):
        action = "updated" if existing else "placed"
        print(f"           ✅ stop {action} @ ${sma:.2f} GTC")
    else:
        print(f"           ❌ place order failed ({resp.status_code}): {resp.text}")


def main():
    parser = argparse.ArgumentParser(description="Set GTC stop-loss orders at 10-day SMA")
    parser.add_argument("--auth",    action="store_true", help="Force re-authentication (browser flow)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen — no orders placed")
    args = parser.parse_args()

    if args.dry_run:
        print("\n⚠️   DRY RUN — no orders will be placed or cancelled\n")

    client    = get_client(force_auth=args.auth)
    positions = get_positions(client)

    if not positions:
        print("No open equity long positions found.")
        return

    print(f"\n{'='*65}")
    print(f"  SCHWAB STOP-LOSS MANAGER")
    print(f"  Positions: {len(positions)} | Dry run: {args.dry_run}")
    print(f"{'='*65}")

    ok = 0
    for pos in positions:
        try:
            process_position(client, pos, dry_run=args.dry_run)
            ok += 1
        except Exception as e:
            print(f"  {pos['ticker']:<8} ❌ error: {e}")

    print(f"\n  {'─'*40}")
    print(f"  Processed: {ok}/{len(positions)} positions\n")


if __name__ == "__main__":
    main()
