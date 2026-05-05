#!/usr/bin/env python3
"""
Schwab Stop-Loss Manager — Lambda Token + Telegram + Only-Raise Logic

Fetches Schwab token from Lambda endpoint, gets all positions, computes 10-day SMAs,
and creates/updates GTC stop-loss orders. Only RAISES stops, never lowers them.
Sends Telegram notifications for each action (created/raised/unchanged).

Key: GET requests use minimal headers (no Content-Type). Only POST/DELETE include
Content-Type: application/json to avoid 400 errors from Schwab API.
"""

import requests
import yfinance as yf
import time
import os
import sys

# ── Configuration ──────────────────────────────────────────────────────────

SCHWAB_API_BASE = "https://api.schwabapi.com/trader/v1"
LAMBDA_TOKEN_ENDPOINT = os.getenv(
    "LAMBDA_TOKEN_ENDPOINT",
    "https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab"
)
LAMBDA_TOKEN_PASSWORD = os.getenv("LAMBDA_TOKEN_PASSWORD", "6#10oz")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SMA_PERIOD = 10


# ── Utilities ──────────────────────────────────────────────────────────────

def get_token() -> str:
    """Fetch fresh Schwab token from Lambda endpoint."""
    r = requests.get(
        LAMBDA_TOKEN_ENDPOINT,
        params={"pw": LAMBDA_TOKEN_PASSWORD},
        timeout=10
    )
    if r.status_code != 200:
        raise Exception(f"Token fetch failed: {r.status_code}")
    return r.json()["access_token"]


def send_telegram(message: str) -> bool:
    """Send Telegram message."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except:
        return False


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("  SCHWAB STOP-LOSS MANAGER — LIVE")
    print("=" * 70 + "\n")

    # Get token
    print("🔐 Fetching token...")
    token = get_token()
    h_get = {"Authorization": f"Bearer {token}"}
    h_post = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("✅ Token ready\n")

    # Get account hash
    print("📊 Fetching account hash...")
    r = requests.get(
        f"{SCHWAB_API_BASE}/accounts/accountNumbers",
        headers=h_get,
        timeout=10
    )
    if r.status_code != 200 or isinstance(r.json(), dict):
        print(f"❌ {r.status_code}: {r.text[:100]}")
        return 1
    acct_hash = r.json()[0]["hashValue"]
    print(f"✅ Hash: {acct_hash[:20]}...")

    # Get positions
    print("📈 Fetching positions...")
    r = requests.get(
        f"{SCHWAB_API_BASE}/accounts",
        headers=h_get,
        params={"fields": "positions"},
        timeout=10
    )
    if r.status_code != 200 or isinstance(r.json(), dict):
        print(f"❌ {r.status_code}: {r.text[:100]}")
        return 1

    positions = []
    for pos in r.json()[0].get("securitiesAccount", {}).get("positions", []):
        if pos.get("instrument", {}).get("assetType") != "EQUITY":
            continue
        if pos.get("longQuantity", 0) <= 0:
            continue
        positions.append({
            "ticker": pos["instrument"]["symbol"],
            "qty": int(pos["longQuantity"]),
        })

    print(f"✅ {len(positions)} equity positions")

    # Get existing stops
    print("📋 Fetching existing stops...")
    r = requests.get(
        f"{SCHWAB_API_BASE}/accounts/{acct_hash}/orders",
        headers=h_get,
        params={"status": "WORKING"},
        timeout=10
    )
    existing_stops = {}
    if r.status_code == 200:
        for o in r.json():
            if o.get("orderType") == "STOP" and o.get("duration") == "GOOD_TILL_CANCEL":
                legs = o.get("orderLegCollection", [{}])
                sym = legs[0].get("instrument", {}).get("symbol") if legs else None
                if sym:
                    existing_stops[sym] = o

    print(f"✅ {len(existing_stops)} existing stop(s): {list(existing_stops.keys())}")

    print("\n" + "=" * 70)

    # Process each position
    success = 0
    for pos in positions:
        ticker, qty = pos["ticker"], pos["qty"]

        try:
            # Get 10-day SMA
            df = yf.download(ticker, period="20d", auto_adjust=True, progress=False)
            if df is None or len(df) < SMA_PERIOD:
                print(f"\n{ticker:<8} ⚠️  No SMA data")
                continue

            close = df["Close"].squeeze()
            sma = round(float(close.tail(SMA_PERIOD).mean()), 2)
            curr = round(float(close.iloc[-1]), 2)

            print(f"\n{ticker:<8}  qty={qty}  curr=${curr}  SMA=${sma}")

            # Skip if SMA >= current price (would trigger immediately)
            if sma >= curr:
                print(f"{'':8} ⚠️  SMA >= price — skipping")
                continue

            # Build stop order spec
            spec = {
                "orderType": "STOP",
                "session": "NORMAL",
                "duration": "GOOD_TILL_CANCEL",
                "orderStrategyType": "SINGLE",
                "stopPrice": sma,
                "orderLegCollection": [{
                    "instruction": "SELL",
                    "quantity": qty,
                    "instrument": {"symbol": ticker, "assetType": "EQUITY"}
                }]
            }

            existing = existing_stops.get(ticker)

            if existing:
                old = existing.get("stopPrice")
                if sma > old:
                    # Raise: cancel old, place new
                    requests.delete(
                        f"{SCHWAB_API_BASE}/accounts/{acct_hash}/orders/{existing['orderId']}",
                        headers=h_get,
                        timeout=10
                    )
                    r = requests.post(
                        f"{SCHWAB_API_BASE}/accounts/{acct_hash}/orders",
                        headers=h_post,
                        json=spec,
                        timeout=10
                    )
                    if r.status_code in (200, 201):
                        print(f"{'':8} ✅ raised ${old} → ${sma}")
                        send_telegram(f"✅ <b>{ticker}</b>: Stop <b>raised</b> to ${sma} (was ${old})")
                        success += 1
                    else:
                        print(f"{'':8} ❌ ({r.status_code}): {r.text[:80]}")
                else:
                    # Leave unchanged
                    print(f"{'':8} ⏸ unchanged @ ${old}  (SMA ${sma} is lower)")
                    send_telegram(f"⏸ <b>{ticker}</b>: Stop <b>unchanged</b> @ ${old} (SMA lower)")
                    success += 1
            else:
                # Create new stop
                r = requests.post(
                    f"{SCHWAB_API_BASE}/accounts/{acct_hash}/orders",
                    headers=h_post,
                    json=spec,
                    timeout=10
                )
                if r.status_code in (200, 201):
                    print(f"{'':8} ✅ created @ ${sma}")
                    send_telegram(f"✅ <b>{ticker}</b>: Stop <b>created</b> @ ${sma}")
                    success += 1
                else:
                    print(f"{'':8} ❌ ({r.status_code}): {r.text[:80]}")

            # Schwab dev API rate limit: ~60s between orders
            time.sleep(65)

        except Exception as e:
            print(f"\n{ticker:<8} ❌ {str(e)[:60]}")

    print("\n" + "=" * 70)
    print(f"  {success}/{len(positions)} stops managed")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
