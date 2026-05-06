#!/usr/bin/env python3
"""
schwab_watchlist_sync.py — Push daily scan results into Schwab as named watchlists.

After watchlist_scanner.py writes to the DB, this module:
  1. Queries the most recent scan_date from watchlist_entries
  2. Fetches A/A+ grade tickers for Watch_{yyyymmdd}
  3. Fetches all runner tickers for Runners_{yyyymmdd}
  4. Creates both watchlists in Schwab (deletes existing same-name lists first)

Usage (standalone):
    python schwab_watchlist_sync.py
    python schwab_watchlist_sync.py --dry-run
"""

import argparse
import logging
import os
import sys
import time
from datetime import date

import requests

# ── Path setup so shared/ and config are importable ───────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as cfg
from shared.db_writer import get_connection

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Schwab API config (mirrors schwab_stop_loss.py) ───────────────────────────
SCHWAB_API_BASE       = "https://api.schwabapi.com/trader/v1"
LAMBDA_TOKEN_ENDPOINT = os.getenv(
    "LAMBDA_TOKEN_ENDPOINT",
    "https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab"
)
LAMBDA_TOKEN_PASSWORD = os.getenv("LAMBDA_TOKEN_PASSWORD", "6#10oz")

# Schwab enforces a 50-item max per watchlist
MAX_WATCHLIST_ITEMS = 50


# ── DB queries ────────────────────────────────────────────────────────────────

def get_latest_scan_date() -> date | None:
    """Return the most recent scan_date present in watchlist_entries, or None."""
    sql = "SELECT MAX(scan_date) FROM watchlist_entries"
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        row  = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception as e:
        logger.error(f"get_latest_scan_date: {e}")
        return None


def get_grade_stocks(scan_date: date) -> list[str]:
    """
    Return tickers with pattern_grade IN ('A', 'A+') for scan_date.
    Ordered A+ first, then A, then closest-to-pivot first.
    Capped at MAX_WATCHLIST_ITEMS.
    """
    sql = """
        SELECT TOP (?) ticker
        FROM   watchlist_entries
        WHERE  scan_date = ?
          AND  pattern_grade IN ('A+', 'A')
        ORDER BY
            CASE pattern_grade WHEN 'A+' THEN 0 ELSE 1 END,
            pct_from_pivot ASC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (MAX_WATCHLIST_ITEMS, scan_date))
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        logger.error(f"get_grade_stocks({scan_date}): {e}")
        return []


def get_runner_stocks(scan_date: date) -> list[str]:
    """
    Return all tickers from runner_entries for scan_date,
    ordered by 3M momentum descending.
    Capped at MAX_WATCHLIST_ITEMS.
    """
    sql = """
        SELECT TOP (?) ticker
        FROM   runner_entries
        WHERE  scan_date = ?
        ORDER BY pct_3m DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (MAX_WATCHLIST_ITEMS, scan_date))
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        logger.error(f"get_runner_stocks({scan_date}): {e}")
        return []


# ── Schwab API helpers ────────────────────────────────────────────────────────

def get_token() -> str:
    """Fetch a fresh Schwab access token from the Lambda endpoint."""
    r = requests.get(
        LAMBDA_TOKEN_ENDPOINT,
        params={"pw": LAMBDA_TOKEN_PASSWORD},
        timeout=10
    )
    if r.status_code != 200:
        raise RuntimeError(f"Token fetch failed: {r.status_code} — {r.text[:80]}")
    return r.json()["access_token"]


def get_account_hash(h_get: dict) -> str:
    """Return the primary account hash from Schwab."""
    r = requests.get(
        f"{SCHWAB_API_BASE}/accounts/accountNumbers",
        headers=h_get,
        timeout=10
    )
    if r.status_code != 200:
        raise RuntimeError(f"accountNumbers failed: {r.status_code} — {r.text[:80]}")
    data = r.json()
    if isinstance(data, dict) or not data:
        raise RuntimeError(f"Unexpected accountNumbers response: {data}")
    return data[0]["hashValue"]


def get_existing_watchlists(acct_hash: str, h_get: dict) -> dict[str, str]:
    """
    Return a dict mapping watchlist name → watchlistId for all existing watchlists.
    """
    r = requests.get(
        f"{SCHWAB_API_BASE}/accounts/{acct_hash}/watchlists",
        headers=h_get,
        timeout=10
    )
    if r.status_code != 200:
        logger.warning(f"get_existing_watchlists: {r.status_code} — {r.text[:80]}")
        return {}
    try:
        return {wl["name"]: wl["watchlistId"] for wl in r.json()}
    except Exception as e:
        logger.warning(f"get_existing_watchlists parse error: {e}")
        return {}


def delete_watchlist(acct_hash: str, watchlist_id: str, h_get: dict) -> bool:
    """Delete a Schwab watchlist by ID. Returns True on success."""
    r = requests.delete(
        f"{SCHWAB_API_BASE}/accounts/{acct_hash}/watchlists/{watchlist_id}",
        headers=h_get,
        timeout=10
    )
    if r.status_code in (200, 204):
        return True
    logger.warning(f"delete_watchlist({watchlist_id}): {r.status_code} — {r.text[:80]}")
    return False


def create_watchlist(acct_hash: str, name: str, tickers: list[str],
                     h_post: dict) -> bool:
    """
    Create a Schwab watchlist with the given name and tickers.
    Returns True on success (200 or 201).
    """
    if not tickers:
        logger.info(f"create_watchlist: no tickers for '{name}' — skipping")
        return False

    items = [
        {
            "sequenceId": i + 1,
            "instrument": {"symbol": sym, "assetType": "EQUITY"}
        }
        for i, sym in enumerate(tickers)
    ]

    body = {"name": name, "watchlistItems": items}

    r = requests.post(
        f"{SCHWAB_API_BASE}/accounts/{acct_hash}/watchlists",
        headers=h_post,
        json=body,
        timeout=10
    )
    if r.status_code in (200, 201):
        return True

    # One retry after a brief pause (handles transient 429 / 503)
    logger.warning(f"create_watchlist '{name}': {r.status_code} — retrying in 5s")
    time.sleep(5)
    r = requests.post(
        f"{SCHWAB_API_BASE}/accounts/{acct_hash}/watchlists",
        headers=h_post,
        json=body,
        timeout=10
    )
    if r.status_code in (200, 201):
        return True

    logger.error(f"create_watchlist '{name}' failed: {r.status_code} — {r.text[:120]}")
    return False


# ── Orchestrator ──────────────────────────────────────────────────────────────

def sync_watchlists(dry_run: bool = False, scan_date: date | None = None) -> dict:
    """
    Full sync flow.  Does NOT require the scanner to have just run — it reads
    directly from the DB, so it can be called at any time after records exist.

    Args:
        dry_run:   Print what would be created without calling the Schwab API.
        scan_date: Use this specific date instead of the latest one in the DB.
                   Useful when re-syncing a past scan or targeting a specific day.
                   Pass as a datetime.date object or None to auto-detect.

    Returns a summary dict:
        {
            "scan_date":      date,
            "watch_name":     str,
            "watch_count":    int,
            "runners_name":   str,
            "runners_count":  int,
        }
    Raises RuntimeError if the token or account hash cannot be fetched.
    """
    # ── 1. Determine scan date ─────────────────────────────────────────────────
    if scan_date is not None:
        scan_dt = scan_date
        logger.info(f"sync_watchlists: using provided scan_date={scan_dt}")
    else:
        scan_dt = get_latest_scan_date()

    if scan_dt is None:
        logger.warning("sync_watchlists: no records found in watchlist_entries — "
                       "run the scanner first, or pass --date to target a specific day")
        return {"scan_date": None, "watch_name": None, "watch_count": 0,
                "runners_name": None, "runners_count": 0}

    date_str     = scan_dt.strftime("%Y%m%d")
    watch_name   = f"Watch_{date_str}"
    runners_name = f"Runners_{date_str}"

    # ── 2. Query tickers ───────────────────────────────────────────────────────
    watch_tickers   = get_grade_stocks(scan_dt)
    runners_tickers = get_runner_stocks(scan_dt)

    logger.info(
        f"sync_watchlists: scan_date={scan_dt}  "
        f"watch={len(watch_tickers)} tickers  "
        f"runners={len(runners_tickers)} tickers"
    )

    if dry_run:
        print(f"\n  [DRY RUN] Would create '{watch_name}': {watch_tickers or '(none)'}")
        print(f"  [DRY RUN] Would create '{runners_name}': {runners_tickers or '(none)'}\n")
        return {
            "scan_date":     scan_dt,
            "watch_name":    watch_name,
            "watch_count":   len(watch_tickers),
            "runners_name":  runners_name,
            "runners_count": len(runners_tickers),
        }

    # ── 3. Authenticate ────────────────────────────────────────────────────────
    token  = get_token()
    h_get  = {"Authorization": f"Bearer {token}"}
    h_post = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ── 4. Get account hash ────────────────────────────────────────────────────
    acct_hash = get_account_hash(h_get)

    # ── 5. Get existing watchlists ─────────────────────────────────────────────
    existing = get_existing_watchlists(acct_hash, h_get)

    # ── 6. Delete stale copies if present, then create fresh ──────────────────
    for name, tickers in [(watch_name, watch_tickers), (runners_name, runners_tickers)]:
        if not tickers:
            logger.info(f"  {name}: no tickers — skipping")
            continue

        if name in existing:
            logger.info(f"  {name}: deleting existing watchlist ({existing[name]})")
            delete_watchlist(acct_hash, existing[name], h_get)

        ok = create_watchlist(acct_hash, name, tickers, h_post)
        if ok:
            logger.info(f"  {name}: created with {len(tickers)} tickers ✓")
        else:
            logger.error(f"  {name}: creation failed ✗")

    return {
        "scan_date":     scan_dt,
        "watch_name":    watch_name,
        "watch_count":   len(watch_tickers),
        "runners_name":  runners_name,
        "runners_count": len(runners_tickers),
    }


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description=(
            "Push scan results from the DB into Schwab as named watchlists.\n"
            "The scanner does NOT need to be running — records are read directly\n"
            "from watchlist_entries and runner_entries."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be created without calling the Schwab API",
    )
    parser.add_argument(
        "--date", metavar="YYYY-MM-DD", default=None,
        help=(
            "Target a specific scan date (e.g. 2026-05-06). "
            "Defaults to the most recent scan_date found in the DB."
        ),
    )
    args = parser.parse_args()

    # Parse --date if provided
    target_date = None
    if args.date:
        try:
            from datetime import datetime as _dt
            target_date = _dt.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid --date '{args.date}' — expected YYYY-MM-DD")
            sys.exit(1)

    try:
        result = sync_watchlists(dry_run=args.dry_run, scan_date=target_date)
        if result["scan_date"]:
            print(f"\n  Schwab watchlist sync complete — {result['scan_date']}")
            print(f"  {result['watch_name']}: {result['watch_count']} tickers")
            print(f"  {result['runners_name']}: {result['runners_count']} tickers\n")
        else:
            print("\n  No records found — nothing synced.\n")
            sys.exit(1)
    except Exception as e:
        logger.error(f"sync_watchlists failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
