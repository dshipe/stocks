# Schwab Watchlist Sync — Plan

> After each daily scan, automatically push today's best setups into Schwab as named
> watchlists so they're visible in the Schwab app and thinkorswim immediately.
> Two watchlists are created per scan:
> - **`Watch_{yyyymmdd}`** — A and A+ grade stocks from `watchlist_entries`
> - **`Runners_{yyyymmdd}`** — all stocks from `runner_entries`

---

## Overview

At the end of `watchlist_scanner.py`, after all DB writes are complete, call a new
module `scan/schwab/schwab_watchlist_sync.py`. It queries the DB for the most recent
`scan_date`, builds two ticker lists, and POSTs each to the Schwab Trader API as a
named watchlist. If a watchlist with the same name already exists (e.g. from a re-run),
it is deleted first and recreated fresh.

---

## What It Does (Step by Step)

```
1. Query DB for most recent scan_date:
      SELECT MAX(scan_date) FROM watchlist_entries

2. Build watchlist ticker list:
      SELECT ticker FROM watchlist_entries
      WHERE  scan_date = <most_recent>
        AND  pattern_grade IN ('A', 'A+')
      ORDER  BY pattern_grade ASC, pct_from_pivot ASC

3. Build runners ticker list:
      SELECT ticker FROM runner_entries
      WHERE  scan_date = <most_recent>
      ORDER  BY pct_3m DESC

4. Authenticate with Schwab (Lambda token endpoint — same as schwab_stop_loss.py)

5. Get account hash:
      GET /trader/v1/accounts/accountNumbers → [0]["hashValue"]

6. Get existing watchlists:
      GET /trader/v1/accounts/{acctHash}/watchlists
   → build a dict: name → watchlistId

7. For each of the two watchlists (Watch_{yyyymmdd}, Runners_{yyyymmdd}):
   a. If name already exists → DELETE /trader/v1/accounts/{acctHash}/watchlists/{id}
   b. POST /trader/v1/accounts/{acctHash}/watchlists
      Body: { "name": "Watch_20260506",
               "watchlistItems": [
                 { "sequenceId": 1, "instrument": { "symbol": "AAPL", "assetType": "EQUITY" } },
                 ...
               ] }
   c. Log success/failure per watchlist

8. Return summary: how many tickers landed in each watchlist
```

---

## Schwab Watchlist API

Base URL and auth are identical to `schwab_stop_loss.py`.

| Action | Method | Endpoint |
|--------|--------|----------|
| List all watchlists | GET | `/trader/v1/accounts/{acctHash}/watchlists` |
| Create watchlist | POST | `/trader/v1/accounts/{acctHash}/watchlists` |
| Delete watchlist | DELETE | `/trader/v1/accounts/{acctHash}/watchlists/{watchlistId}` |

**Create body schema:**
```json
{
  "name": "Watch_20260506",
  "watchlistItems": [
    {
      "sequenceId": 1,
      "instrument": { "symbol": "AAPL", "assetType": "EQUITY" }
    }
  ]
}
```

- `sequenceId` is 1-based and controls display order in Schwab.
- Max items per watchlist: 50 (Schwab enforces this). If the list exceeds 50, truncate
  and log a warning — the highest-graded / highest-momentum items sort first so the
  most important ones are kept.
- Use `Content-Type: application/json` on POST; omit it on GET/DELETE (same rule as
  `schwab_stop_loss.py`).

---

## New File: `scan/schwab/schwab_watchlist_sync.py`

### Function outline

```python
def get_latest_scan_date(conn) -> date | None:
    """SELECT MAX(scan_date) FROM watchlist_entries"""

def get_grade_stocks(conn, scan_date: date) -> list[str]:
    """
    Return tickers with pattern_grade IN ('A', 'A+') for scan_date,
    ordered A+ first then A, then by pct_from_pivot ascending.
    Returns up to 50 tickers.
    """

def get_runner_stocks(conn, scan_date: date) -> list[str]:
    """
    Return all tickers from runner_entries for scan_date,
    ordered by pct_3m descending.
    Returns up to 50 tickers.
    """

def get_existing_watchlists(acct_hash: str, headers: dict) -> dict[str, str]:
    """
    GET /trader/v1/accounts/{acctHash}/watchlists
    Returns dict mapping name → watchlistId.
    """

def delete_watchlist(acct_hash: str, watchlist_id: str, headers: dict) -> bool:
    """DELETE /trader/v1/accounts/{acctHash}/watchlists/{id}"""

def create_watchlist(acct_hash: str, name: str, tickers: list[str],
                     headers: dict) -> bool:
    """
    POST /trader/v1/accounts/{acctHash}/watchlists
    Builds the watchlistItems array from tickers list.
    Returns True on 200/201.
    """

def sync_watchlists(dry_run: bool = False, scan_date: date | None = None) -> dict:
    """
    Orchestrates the full flow. Does NOT require the scanner to have just run —
    reads directly from the DB so it can be called any time records exist.

    scan_date: target a specific date; defaults to MAX(scan_date) from the DB.
    Returns { "scan_date": date, "watch_name": str, "watch_count": int,
              "runners_name": str, "runners_count": int }
    """

def main():
    """
    CLI entry point. Flags:
        --dry-run          Print what would be created; no API calls.
        --date YYYY-MM-DD  Target a specific scan date instead of latest.
    """
```

### DB connection

Reuse `get_connection()` from `shared/db_writer.py` — same `config.DB_CONNECTION_STRING`.
Import pattern:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.db_writer import get_connection
import config as cfg
```

### Token / auth

Identical to `schwab_stop_loss.py` — `get_token()` hits the Lambda endpoint.
No new auth logic needed.

---

## Integration into `watchlist_scanner.py`

Two changes are needed in `main()`.

### 1. Filter Telegram to A/A+ only (around line 449)

`send_watchlist_summary()` currently receives the full `watchlist` list (all grades).
Filter it before the call so Telegram only shows A and A+ setups:

```python
# Send Telegram notifications (always, even on dry-run)
if not args.ticker:  # skip single-ticker test runs
    tg_stats = { ... }  # unchanged
    scan_date_str = str(_date.today())

    # ── Filter watchlist to A/A+ grades only for Telegram ─────────────────
    tg_watchlist = [e for e in watchlist if e.get("pattern_grade") in ("A+", "A")]

    sent = send_watchlist_summary(
        scan_date=scan_date_str,
        results=tg_watchlist,      # ← was `watchlist`
        stats=tg_stats,
    )
```

`send_watchlist_summary()` itself does not change — the filtering happens at the call
site so the full list remains available in memory for Schwab sync and any future use.

The stats footer in the Telegram message (total scanned, S1/S2/S3/S4 counts) is
unchanged — it still reflects the full scan, not just the A/A+ subset. This keeps
the numbers consistent with what's in the DB.

### 2. Schwab watchlist sync (after DB writes, before Telegram)

Insert after the runner DB-write `print` statement, before the Telegram block:

```python
# ── Schwab watchlist sync ──────────────────────────────────────────────────
if not args.dry_run and not args.ticker:   # skip on dry-run and single-ticker tests
    try:
        from schwab.schwab_watchlist_sync import sync_watchlists
        wl_result = sync_watchlists()
        logger.info(
            f"Schwab watchlists created: "
            f"{wl_result['watch_name']} ({wl_result['watch_count']} tickers), "
            f"{wl_result['runners_name']} ({wl_result['runners_count']} tickers)"
        )
    except Exception as e:
        logger.warning(f"Schwab watchlist sync failed (non-fatal): {e}")
```

Wrapping in try/except keeps a Schwab API failure from aborting Telegram notifications.

### 3. `--schwab-only` flag (skip scan entirely)

Added to `watchlist_scanner.py` argparse. When set, `main()` short-circuits before
the yfinance fetch and scan: it verifies the DB connection, calls `sync_watchlists()`,
prints the result, and exits. No ticker universe fetch, no criteria eval, no DB writes.

```python
# Usage:
python watchlist_scanner.py --schwab-only
```

Useful when the scan has already run and you just need to re-push to Schwab — e.g.
after a token refresh, or to fix a watchlist name without re-scanning.

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| No A/A+ stocks today | `Watch_{date}` skipped; logged as "no tickers — skipping" |
| No runners today | `Runners_{date}` skipped; logged as "no tickers — skipping" |
| Watchlist already exists (re-run) | Delete existing, recreate fresh |
| > 50 tickers in either list | Truncate to 50; highest-grade / highest-momentum items kept |
| Schwab API rate limit / 429 | Retry once after 5s; if still failing, log and continue |
| `--dry-run` flag | Skips API calls; prints what would be created |
| `--ticker AAPL` single-ticker mode | Schwab sync skipped entirely |
| `--schwab-only` flag | Skips scan; reads DB and syncs directly — scanner not invoked |
| No DB records found | Logs warning and exits with code 1 |

---

## Files Changed

| File | Change |
|------|--------|
| `scan/schwab/schwab_watchlist_sync.py` | **New** — full sync module with `--dry-run` and `--date` CLI flags |
| `scan/watchlist_scanner.py` | (1) `--schwab-only` flag — skips scan, syncs from DB and exits; (2) Schwab sync block after DB writes; (3) A/A+ filter before `send_watchlist_summary()` |
| `scan/shared/telegram_notify.py` | No changes — filtering happens at the call site |

No schema changes. No new dependencies (uses `requests`, `pyodbc`, `config` — all
already present).

---

## Running the Sync

| Command | What it does |
|---------|-------------|
| `python watchlist_scanner.py` | Full daily run — scan + DB write + Schwab sync + Telegram |
| `python watchlist_scanner.py --schwab-only` | Skip scan; read existing DB records and push to Schwab |
| `python schwab/schwab_watchlist_sync.py` | Standalone sync — latest scan date from DB |
| `python schwab/schwab_watchlist_sync.py --date 2026-05-05` | Sync a specific past date |
| `python schwab/schwab_watchlist_sync.py --dry-run` | Print what would be created; no API calls |

---

## Testing

1. **Dry run**: `python schwab/schwab_watchlist_sync.py --dry-run` — prints what would
   be created without hitting the API.
2. **Standalone**: `python schwab/schwab_watchlist_sync.py` — syncs latest scan from DB.
3. **Specific date**: `python schwab/schwab_watchlist_sync.py --date 2026-05-05`
4. **Via scanner**: `python watchlist_scanner.py --schwab-only` — same as standalone
   but invoked through the scanner entry point.
5. **Verify in Schwab app**: Open Schwab → Watchlists and confirm `Watch_<date>` and
   `Runners_<date>` appear with the correct tickers.
6. **Re-run idempotency**: Run again for the same date — old lists are deleted and
   cleanly recreated.
