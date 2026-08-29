#!/usr/bin/env python3
"""
pelosi_alert.py -- Daily check for new Nancy Pelosi stock trade disclosures.

Downloads the latest house-stock-watcher-data dataset (same free source used by
pelosi_backtest.py -- see https://github.com/TattooedHead/house-stock-watcher-data),
diffs it against the previously-seen trades, and sends a Telegram alert for any
that are new. Meant to run once a day via cron.

First run establishes a baseline (every trade currently on file is marked "seen"
without alerting) so you don't get flooded with years of historical trades the
first time this runs -- only trades that appear *after* that get alerted.

Dedup key is (filing_id, ticker, transaction_date, type, amount, owner) per the
source project's own guidance: one filing can contain several trades, and the
same rep can make the same trade the same day in two accounts (e.g. Self +
Spouse), which are real, distinct disclosures.

Reuses scan/shared/telegram_notify.py's bot credentials rather than duplicating
them here -- same bot/chat as your breakout alerts.

Usage:
    python pelosi_alert.py                  # normal run: alert + update state
    python pelosi_alert.py --dry-run         # show what would alert, no state write, no Telegram
    python pelosi_alert.py --representative "Dan Crenshaw"   # track someone else
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scan"))
from shared.telegram_notify import _send as send_telegram  # noqa: E402  (reuses existing bot config)

DATA_URL = "https://raw.githubusercontent.com/TattooedHead/house-stock-watcher-data/main/data/all_transactions.json"
STATE_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_PATH = os.path.join(STATE_DIR, "all_transactions.json")


def load_transactions() -> list[dict]:
    resp = requests.get(DATA_URL, timeout=60)
    resp.raise_for_status()
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(resp.text)
    return json.loads(resp.text)


def trade_key(r: dict) -> str:
    return "|".join([
        str(r.get("filing_id")), r.get("ticker", ""), r.get("transaction_date", ""),
        r.get("type", ""), r.get("amount", ""), r.get("owner", ""),
    ])


def state_path(representative: str) -> str:
    slug = representative.lower().replace(" ", "_")
    return os.path.join(STATE_DIR, f"{slug}_seen.json")


def load_seen(representative: str) -> set:
    path = state_path(representative)
    if not os.path.exists(path):
        return None  # signals "no baseline yet" vs. an empty set
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(representative: str, seen: set) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(representative), "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)


def format_alert(r: dict) -> str:
    emoji = {"Purchase": "\U0001F7E2", "Sale": "\U0001F534", "Exchange": "\U0001F501"}.get(r["type"], "•")
    return (
        f"{emoji} <b>{r['representative']} -- {r['type']}</b>\n\n"
        f"   Ticker: <b>{r['ticker']}</b>  ({r.get('asset_description', '')[:60]})\n"
        f"   Amount: {r['amount']}\n"
        f"   Owner: {r['owner']}\n"
        f"   Transaction date: {r['transaction_date']}\n"
        f"   Disclosed: {r['disclosure_date']}\n"
        f"   <a href=\"{r['source_url']}\">Filing PDF</a>"
    )


def main():
    parser = argparse.ArgumentParser(description="Alert on new congressional stock trade disclosures")
    parser.add_argument("--representative", default="Nancy Pelosi")
    parser.add_argument("--dry-run", action="store_true", help="Show new trades without alerting or updating state")
    args = parser.parse_args()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"  CONGRESS TRADE ALERT -- {args.representative} -- {now_str}")
    print(f"{'='*60}")

    try:
        all_rows = load_transactions()
    except Exception as e:
        print(f"  ERROR: could not fetch disclosure data: {e}")
        sys.exit(1)

    rows = [r for r in all_rows if args.representative.lower() in r["representative"].lower()]
    print(f"  Trades on file for {args.representative}: {len(rows)}")

    seen = load_seen(args.representative)
    current_keys = {trade_key(r) for r in rows}

    if seen is None:
        print(f"  No baseline found -- establishing one now (no alerts for existing history).")
        if not args.dry_run:
            save_seen(args.representative, current_keys)
        print(f"  Baseline saved: {len(current_keys)} trades. Future runs will alert on anything new.\n")
        return

    new_rows = [r for r in rows if trade_key(r) not in seen]

    if not new_rows:
        print(f"  No new trades since last check.\n")
        return

    print(f"  {len(new_rows)} new trade(s) found:\n")
    for r in sorted(new_rows, key=lambda r: r["disclosure_date"]):
        print(f"    {r['disclosure_date']} | {r['ticker']:<6} | {r['type']:<8} | {r['amount']} | {r['owner']}")
        if not args.dry_run:
            ok = send_telegram(format_alert(r))
            print(f"      -> Telegram {'sent' if ok else 'FAILED'}")

    if not args.dry_run:
        save_seen(args.representative, current_keys)
    print()


if __name__ == "__main__":
    main()
