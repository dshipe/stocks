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
import time
import json
from datetime import datetime, timedelta
import requests

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
APP_KEY               = os.getenv("SCHWAB_APP_KEY")
APP_SECRET            = os.getenv("SCHWAB_SECRET")
CALLBACK_URL          = "https://127.0.0.1"
TOKEN_FILE            = os.path.join(os.path.dirname(__file__), "schwab_token.json")
LAMBDA_TOKEN_ENDPOINT = os.getenv("LAMBDA_TOKEN_ENDPOINT", "https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab")
LAMBDA_TOKEN_PASSWORD = os.getenv("LAMBDA_TOKEN_PASSWORD", "6#10oz")
TELEGRAM_BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID")

SMA_PERIOD   = 10   # 10-day SMA


def get_or_refresh_token() -> str:
    """Fetch token from Lambda API, or use cached token if still valid."""
    # Check if cached token exists and is fresh (< 5 min old)
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                cached = json.load(f)
            if 'fetched_at' in cached:
                fetched_time = datetime.fromisoformat(cached['fetched_at'])
                if datetime.now() - fetched_time < timedelta(minutes=5):
                    print("🔑 Using cached token")
                    return cached['token']
        except Exception as e:
            print(f"⚠️  Could not read cached token: {e}")
    
    # Fetch new token from Lambda
    print("🔐 Fetching token from Lambda API...")
    params = {'pw': LAMBDA_TOKEN_PASSWORD}
    try:
        resp = requests.get(LAMBDA_TOKEN_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        sys.exit(f"❌  Lambda token fetch failed: {e}")
    
    # Cache token with timestamp
    token_data = {
        'token': data['access_token'],
        'fetched_at': datetime.now().isoformat()
    }
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f)
    
    print("✅ Token cached")
    return data['access_token']


def get_client(force_auth: bool = False):
    """Return an authenticated Schwab client using Lambda token."""
    access_token = get_or_refresh_token()
    client = schwab.auth.client_from_token_dict(
        token_dict={'access_token': access_token, 'token_type': 'Bearer'},
    )
    return client


def get_account_hash_map(client) -> dict:
    """Return {accountNumber: hashValue} from the account numbers endpoint."""
    resp = client.get_account_numbers()
    resp.raise_for_status()
    return {a["accountNumber"]: a["hashValue"] for a in resp.json()}


def get_positions(client) -> list[dict]:
    """Return all open long equity positions across all accounts."""
    hash_map = get_account_hash_map(client)
    resp = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
    resp.raise_for_status()
    positions = []
    for account in resp.json():
        acct     = account.get("securitiesAccount", {})
        acct_num = acct.get("accountNumber", "")
        acct_hash = hash_map.get(acct_num, acct_num)
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


def send_telegram(message: str):
    """Send a Telegram message."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return  # Silently skip if not configured
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"  ⚠️  Telegram error: {resp.status_code}")
    except Exception as e:
        print(f"  ⚠️  Telegram failed: {e}")


def process_position(client, pos: dict, dry_run: bool):
    """Manage GTC stop at 10-day SMA — only raise, never lower."""
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
            print(f"           [DRY RUN] would manage existing stop @ ${old_stop} vs SMA ${sma}")
        else:
            print(f"           [DRY RUN] would place new GTC stop @ ${sma}")
        return

    if existing:
        current_stop_price = existing[0].get("stopPrice")
        if sma > current_stop_price:
            # SMA is higher: raise the stop
            resp = client.cancel_order(acct_hash, existing[0]["orderId"])
            if resp.status_code in (200, 204):
                print(f"           ✅ cancelled existing stop @ ${current_stop_price}")
            else:
                print(f"           ⚠️  cancel failed ({resp.status_code}) — proceeding anyway")

            # Place new stop (retry once on 429)
            order_spec = build_stop_order(ticker, qty, sma)
            for attempt in range(2):
                resp = client.place_order(acct_hash, order_spec)
                if resp.status_code in (200, 201):
                    print(f"           ✅ stop raised @ ${sma:.2f} (was ${current_stop_price:.2f})")
                    send_telegram(f"✅ <b>{ticker}</b>: Stop <b>raised</b> to ${sma:.2f} (was ${current_stop_price:.2f})")
                    break
                elif resp.status_code == 429 and attempt == 0:
                    print(f"           ⏳ rate limited, waiting 10s...")
                    time.sleep(10)
                else:
                    print(f"           ❌ place order failed ({resp.status_code}): {resp.text}")
                    break
        else:
            # SMA is lower or equal: leave stop unchanged
            print(f"           ⏸  stop unchanged @ ${current_stop_price:.2f} (SMA ${sma:.2f} is lower)")
            send_telegram(f"⏸ <b>{ticker}</b>: Stop <b>unchanged</b> @ ${current_stop_price:.2f} (SMA ${sma:.2f} is lower)")
    else:
        # No existing stop: create one at SMA
        order_spec = build_stop_order(ticker, qty, sma)
        for attempt in range(2):
            resp = client.place_order(acct_hash, order_spec)
            if resp.status_code in (200, 201):
                print(f"           ✅ stop created @ ${sma:.2f} GTC")
                send_telegram(f"✅ <b>{ticker}</b>: Stop <b>created</b> @ ${sma:.2f}")
                break
            elif resp.status_code == 429 and attempt == 0:
                print(f"           ⏳ rate limited, waiting 10s...")
                time.sleep(10)
            else:
                print(f"           ❌ place order failed ({resp.status_code}): {resp.text}")
                break
    
    time.sleep(65)  # Schwab dev API enforces ~60s between order placements


def main():
    parser = argparse.ArgumentParser(description="Set GTC stop-loss orders at 10-day SMA")
    parser.add_argument("--get-auth-url",  action="store_true", help="Print the Schwab OAuth2 login URL")
    parser.add_argument("--complete-auth", metavar="REDIRECT_URL", help="Complete auth by passing the redirect URL from the browser")
    parser.add_argument("--dry-run",       action="store_true", help="Show what would happen — no orders placed")
    args = parser.parse_args()

    # ── Legacy OAuth2 args (deprecated, will be removed) ──────────────────────
    if args.get_auth_url or args.complete_auth:
        print("\n⚠️  OAuth2 args deprecated. Using Lambda token endpoint now.\n")
        print("   Run: python3 schwab_stop_loss.py --dry-run\n")
        return

    if args.dry_run:
        print("\n⚠️   DRY RUN — no orders will be placed or cancelled\n")

    client    = get_client(force_auth=False)
    positions = get_positions(client)

    if not positions:
        print("No open equity long positions found.")
        return

    print(f"\n{'='*65}")
    print(f"  SCHWAB STOP-LOSS MANAGER")
    print(f"  Positions: {len(positions)} | Dry run: {args.dry_run}")
    print(f"  (Only raises stops, never lowers them)")
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
