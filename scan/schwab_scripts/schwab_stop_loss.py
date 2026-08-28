#!/usr/bin/env python3
"""
Schwab Stop-Loss Manager — Batch Computation + Exponential Backoff

Refactored (Option B) to separate data fetch and order submission phases:
  Phase 1 — Fetch token, account hash, positions, existing stops
  Phase 2 — Compute all stop prices upfront (yfinance SMA, no Schwab calls)
  Phase 3 — Submit all orders with exponential backoff retry on 429

Only RAISES stops, never lowers them.
Sends Telegram notifications for each action (created/raised/unchanged/retry/failed).

Key: GET requests use minimal headers (no Content-Type). Only POST/DELETE include
Content-Type: application/json to avoid 400 errors from Schwab API.
"""

import requests
import yfinance as yf
import time
import os
import sys

# cron runs this with no LANG/PYTHONIOENCODING set, so stdout defaults to the
# platform's ASCII/C locale — any print() with an emoji (see below) then raises
# UnicodeEncodeError, aborting the run before later stop-loss orders are submitted.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Configuration ──────────────────────────────────────────────────────────

SCHWAB_API_BASE = "https://api.schwabapi.com/trader/v1"
LAMBDA_TOKEN_ENDPOINT = os.getenv(
    "LAMBDA_TOKEN_ENDPOINT",
    "https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab"
)
LAMBDA_TOKEN_PASSWORD = os.getenv("LAMBDA_TOKEN_PASSWORD", "6#10oz")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

SMA_PERIOD  = 10
MAX_RETRIES = 3
# Backoff delays (seconds) for 429 responses. Schwab's undocumented limit is
# ~90–120s between order placements. Using 30/90/150 gives three meaningful
# attempts without exceeding a 15-minute cron window.
# To override: set SCHWAB_RETRY_DELAYS env var as comma-separated seconds, e.g. "60,120,180"
_default_delays = "30,90,150"
RETRY_DELAYS = [int(x) for x in os.getenv("SCHWAB_RETRY_DELAYS", _default_delays).split(",")]


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
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
        return r.status_code == 200
    except Exception:
        return False


def submit_order_with_backoff(
    ticker: str,
    spec: dict,
    h_post: dict,
    acct_hash: str,
    action_label: str,  # e.g. "create" or "raise"
    old_price: float | None = None,
) -> bool:
    """
    POST an order to Schwab with exponential backoff on 429.

    Retries up to MAX_RETRIES times using RETRY_DELAYS. On each 429:
      - Checks the Retry-After response header; if present, uses that value
      - Otherwise falls back to the configured RETRY_DELAYS sequence
    Returns True if the order was placed successfully, False after all retries fail.
    """
    url = f"{SCHWAB_API_BASE}/accounts/{acct_hash}/orders"

    for attempt in range(1, MAX_RETRIES + 1):
        r = requests.post(url, headers=h_post, json=spec, timeout=10)

        if r.status_code in (200, 201):
            return True

        if r.status_code == 429:
            if attempt == MAX_RETRIES:
                print(f"  ❌ {ticker}: 429 on attempt {attempt}/{MAX_RETRIES} — giving up")
                send_telegram(
                    f"❌ <b>{ticker}</b>: Failed to {action_label} stop after "
                    f"{MAX_RETRIES} attempts (rate limited)"
                )
                return False

            # Respect Retry-After header if Schwab provides one; otherwise use our table
            retry_after_hdr = r.headers.get("Retry-After")
            wait = int(retry_after_hdr) if retry_after_hdr else RETRY_DELAYS[attempt - 1]
            print(f"  ⏳ {ticker}: 429 on attempt {attempt}/{MAX_RETRIES} — "
                  f"waiting {wait}s (Retry-After={'header' if retry_after_hdr else 'default'})")
            send_telegram(
                f"⏳ <b>{ticker}</b>: Rate limited — retrying stop {action_label} "
                f"(attempt {attempt + 1}/{MAX_RETRIES}, waiting {wait}s)"
            )
            time.sleep(wait)
        else:
            print(f"  ❌ {ticker}: unexpected {r.status_code} — {r.text[:80]}")
            return False

    return False  # unreachable but satisfies type checker


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("  SCHWAB STOP-LOSS MANAGER — LIVE")
    print("=" * 70 + "\n")

    # ── Phase 1: Fetch token, account data, positions, existing stops ──────

    print("🔐 Fetching token...")
    token  = get_token()
    h_get  = {"Authorization": f"Bearer {token}"}
    h_post = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("✅ Token ready\n")

    print("📊 Fetching account hash...")
    r = requests.get(f"{SCHWAB_API_BASE}/accounts/accountNumbers", headers=h_get, timeout=10)
    if r.status_code != 200 or isinstance(r.json(), dict):
        print(f"❌ {r.status_code}: {r.text[:100]}")
        return 1
    acct_hash = r.json()[0]["hashValue"]
    print(f"✅ Hash: {acct_hash[:20]}...")

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
            "qty":    int(pos["longQuantity"]),
        })
    print(f"✅ {len(positions)} equity position(s)")

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
                sym  = legs[0].get("instrument", {}).get("symbol") if legs else None
                if sym:
                    existing_stops[sym] = o
    print(f"✅ {len(existing_stops)} existing stop(s): {list(existing_stops.keys())}")

    # ── Phase 2: Compute all stop prices (no order placement) ──────────────

    print("\n" + "=" * 70)
    print("  PHASE 2 — Computing stop prices")
    print("=" * 70 + "\n")

    pending = []   # items ready for order submission

    for pos in positions:
        ticker, qty = pos["ticker"], pos["qty"]

        try:
            df = yf.download(ticker, period="20d", auto_adjust=True, progress=False)
            if df is None or len(df) < SMA_PERIOD:
                print(f"{ticker:<8} ⚠️  Insufficient data for SMA — skipping")
                continue

            close = df["Close"].squeeze()
            sma   = round(float(close.tail(SMA_PERIOD).mean()), 2)
            curr  = round(float(close.iloc[-1]), 2)
            print(f"{ticker:<8}  qty={qty}  curr=${curr}  SMA10=${sma}")

            if sma >= curr:
                print(f"  ⚠️  SMA >= price — would trigger immediately, skipping")
                continue

            spec = {
                "orderType":          "STOP",
                "session":            "NORMAL",
                "duration":           "GOOD_TILL_CANCEL",
                "orderStrategyType":  "SINGLE",
                "stopPrice":          sma,
                "orderLegCollection": [{
                    "instruction": "SELL",
                    "quantity":    qty,
                    "instrument":  {"symbol": ticker, "assetType": "EQUITY"},
                }],
            }

            existing = existing_stops.get(ticker)
            if existing:
                old = existing.get("stopPrice")
                if sma > old:
                    pending.append({
                        "action":      "raise",
                        "ticker":      ticker,
                        "qty":         qty,
                        "sma":         sma,
                        "curr":        curr,
                        "spec":        spec,
                        "old_price":   old,
                        "order_id":    existing["orderId"],
                    })
                    print(f"  → will raise ${old} → ${sma}")
                else:
                    print(f"  ⏸ unchanged @ ${old}  (SMA ${sma} is lower — no action needed)")
                    send_telegram(f"⏸ <b>{ticker}</b>: Stop <b>unchanged</b> @ ${old} (SMA lower)")
            else:
                pending.append({
                    "action":    "create",
                    "ticker":    ticker,
                    "qty":       qty,
                    "sma":       sma,
                    "curr":      curr,
                    "spec":      spec,
                    "old_price": None,
                    "order_id":  None,
                })
                print(f"  → will create @ ${sma}")

        except Exception as e:
            print(f"{ticker:<8} ❌ compute error: {str(e)[:80]}")

    # ── Phase 3: Submit orders with backoff ────────────────────────────────

    print("\n" + "=" * 70)
    print(f"  PHASE 3 — Submitting {len(pending)} order(s)")
    print("=" * 70 + "\n")

    if not pending:
        print("  Nothing to submit.\n")
        print("=" * 70)
        print("  0 order(s) placed")
        print("=" * 70 + "\n")
        return 0

    # Phase 3a: Execute all DELETEs first (raises need to cancel the old stop)
    # Batching DELETEs before POSTs avoids sharing the rate-limit bucket
    # between a cancel and the immediately-following create.
    for item in pending:
        if item["action"] == "raise":
            print(f"{item['ticker']:<8} 🗑️  Cancelling old stop @ ${item['old_price']}...")
            requests.delete(
                f"{SCHWAB_API_BASE}/accounts/{acct_hash}/orders/{item['order_id']}",
                headers=h_get,
                timeout=10
            )

    # Brief pause after DELETEs before starting POSTs
    if any(i["action"] == "raise" for i in pending):
        print("\n  Pausing 5s after cancellations before placing new orders...\n")
        time.sleep(5)

    # Phase 3b: POST each order with exponential backoff on 429
    success = 0
    for item in pending:
        ticker = item["ticker"]
        sma    = item["sma"]
        action = item["action"]

        print(f"{ticker:<8} Attempting {action} @ ${sma}  (attempt 1/{MAX_RETRIES})...")
        ok = submit_order_with_backoff(
            ticker      = ticker,
            spec        = item["spec"],
            h_post      = h_post,
            acct_hash   = acct_hash,
            action_label= action,
            old_price   = item.get("old_price"),
        )

        if ok:
            if action == "raise":
                old = item["old_price"]
                print(f"  ✅ raised ${old} → ${sma}")
                send_telegram(f"✅ <b>{ticker}</b>: Stop <b>raised</b> to ${sma} (was ${old})")
            else:
                print(f"  ✅ created @ ${sma}")
                send_telegram(f"✅ <b>{ticker}</b>: Stop <b>created</b> @ ${sma}")
            success += 1
        # failure already logged inside submit_order_with_backoff

    print("\n" + "=" * 70)
    print(f"  {success}/{len(pending)} order(s) placed successfully")
    print("=" * 70 + "\n")

    return 0 if success == len(pending) else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Schwab Stop-Loss Manager")
    parser.add_argument("--token", type=str, default=None,
                        help="Pass a Schwab access token directly (skips Lambda fetch)")
    args = parser.parse_args()
    if args.token:
        get_token = lambda: args.token
    sys.exit(main())
