# Schwab Integration

> Two scripts in `scan/schwab_scripts/` connect the daily scan pipeline to Charles Schwab:
>
> | Script | What it does | When it runs |
> |--------|-------------|--------------|
> | `schwab_stop_loss.py` | Sets/raises GTC stop-loss orders at the 10-day SMA for every open equity position | 8:15 AM EDT weekdays (cron) |
> | `schwab_watchlist_sync.py` | Pushes today's A/A+ watchlist and runners into Schwab as named watchlists | End of `watchlist_scanner.py` run (auto) or `--schwab-only` / standalone |

Both scripts authenticate via the same Lambda token endpoint and share the same Schwab Trader API base URL.

---

## Shared Auth & API

```
Token endpoint: https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab
Password:       LAMBDA_TOKEN_PASSWORD env var (default: 6#10oz)
API base:       https://api.schwabapi.com/trader/v1
```

**Header rules (important):**
- `GET` and `DELETE` requests: `Authorization: Bearer <token>` only — no `Content-Type`
- `POST` requests: add `Content-Type: application/json`
- Violating this causes Schwab to return 400/500 errors

**Credentials in `scan/.env` (never committed):**
```env
LAMBDA_TOKEN_ENDPOINT=https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab
LAMBDA_TOKEN_PASSWORD=6#10oz
TELEGRAM_BOT_TOKEN=<your_bot_token>
TELEGRAM_CHAT_ID=<your_chat_id>
```

---

## Stop-Loss Manager (`schwab_stop_loss.py`)

### What It Does

Runs in three phases each morning:

```
Phase 1 — Fetch: token → account hash → equity positions → existing GTC stops
Phase 2 — Compute: 10-day SMA via yfinance for each position (no Schwab calls)
Phase 3 — Submit: place/raise orders with exponential backoff on 429
```

**Only raises or creates stops — never lowers them.** If the 10-day SMA is below the current stop price, the stop is left unchanged.

### Key Endpoints

| Action | Method | Endpoint |
|--------|--------|----------|
| Get account hash | GET | `/accounts/accountNumbers` |
| Get positions | GET | `/accounts?fields=positions` |
| Get open orders | GET | `/accounts/{hash}/orders?status=WORKING` |
| Place order | POST | `/accounts/{hash}/orders` |
| Cancel order | DELETE | `/accounts/{hash}/orders/{orderId}` |

### Rate Limit Handling (Option B — implemented 2026-05-11)

Schwab's order placement endpoint is rate-limited to approximately **1 order per 90–120 seconds** (undocumented). The script handles this with three mechanisms:

**Phase 3a — Batch all DELETEs first:**
All old stops are cancelled before any new ones are placed. This avoids sharing the rate-limit bucket between a cancel and the immediately-following create.

```python
# All DELETEs happen here
for item in pending:
    if item["action"] == "raise":
        requests.delete(f"{API}/accounts/{hash}/orders/{item['order_id']}", ...)
time.sleep(5)  # brief pause after cancellations
```

**Phase 3b — Exponential backoff on 429:**
```python
RETRY_DELAYS = [30, 90, 150]   # seconds (configurable via SCHWAB_RETRY_DELAYS env var)
MAX_RETRIES  = 3
```
On each 429 response, the script checks for a `Retry-After` header and uses it if present; otherwise falls back to the configured delay sequence. After `MAX_RETRIES` failures, it logs, sends a Telegram alert, and moves on.

**Telegram notifications** fire for every outcome: stop raised, created, unchanged, retry attempt, and final failure.

**To adjust retry delays:**
```env
SCHWAB_RETRY_DELAYS=60,120,180   # comma-separated seconds
```

### Output

```
======================================================================
  SCHWAB STOP-LOSS MANAGER — LIVE
======================================================================

🔐 Fetching token...
✅ Token ready

Phase 2 — Computing stop prices
NVDA      qty=100  curr=$128.40  SMA10=$122.50
  → will raise $119.00 → $122.50
CELH      qty=50   curr=$48.20   SMA10=$46.30
  → will create @ $46.30

Phase 3 — Submitting 2 order(s)
NVDA      Attempting raise @ $122.50 (attempt 1/3)...
  ✅ raised $119.00 → $122.50
CELH      Attempting create @ $46.30 (attempt 1/3)...
  ✅ created @ $46.30

2/2 order(s) placed successfully
```

### Safety Notes

- Only `EQUITY` positions with `longQuantity > 0` are processed — options are skipped
- If `SMA >= current_price`, the stop would trigger immediately — position is skipped with a warning
- Stop price is rounded to 2 decimal places
- There is a brief window between cancel and re-place where no stop exists; this is a known limitation

### Scheduling

```
15 12 * * 1-5  cd scan/ && python3 schwab_scripts/schwab_stop_loss.py >> logs/schwab_stop_loss.log 2>&1
```

Runs at **8:15 AM EDT (12:15 UTC)** — 15 minutes after the watchlist scanner, well before the 9:30 AM market open.

### Running Manually

```bash
cd scan/
python3 schwab_scripts/schwab_stop_loss.py              # live run
python3 schwab_scripts/schwab_stop_loss.py --token XYZ  # pass token directly (skips Lambda)
```

### Implementation Notes

| Date | Change |
|------|--------|
| 2026-05-04 | Initial implementation. Auth via Lambda token endpoint. |
| 2026-05-04 | 65s sleep between order placements to handle dev API rate limit. |
| 2026-05-05 | Only raise or create stops, never lower. Telegram notifications added. |
| 2026-05-05 | Fixed Schwab HTTP header issue: GET must NOT include Content-Type. Switched to direct `requests` calls instead of schwab-py. |
| 2026-05-11 | **Option B refactor:** Three-phase approach. All DELETEs batched before POSTs. Exponential backoff 30s/90s/150s. Respects `Retry-After` header. `SCHWAB_RETRY_DELAYS` env override added. |

---

## Watchlist Sync (`schwab_watchlist_sync.py`)

### What It Does

After `watchlist_scanner.py` writes to the DB, this module:
1. Queries the most recent `scan_date` from `watchlist_entries`
2. Fetches **A/A+ grade tickers** → `Watch_{yyyymmdd}` watchlist
3. Fetches **all runner tickers** → `Runners_{yyyymmdd}` watchlist
4. Deletes any existing same-name Schwab watchlist, then creates fresh

Both watchlists appear in the Schwab app and thinkorswim immediately.

### Schwab Watchlist API

| Action | Method | Endpoint |
|--------|--------|----------|
| List all watchlists | GET | `/accounts/{hash}/watchlists` |
| Create watchlist | POST | `/accounts/{hash}/watchlists` |
| Delete watchlist | DELETE | `/accounts/{hash}/watchlists/{watchlistId}` |

**Create body schema:**
```json
{
  "name": "Watch_20260506",
  "watchlistItems": [
    { "sequenceId": 1, "instrument": { "symbol": "AAPL", "assetType": "EQUITY" } }
  ]
}
```

Max 50 items per watchlist (Schwab enforces this). Lists are ordered A+ first, then A, then closest-to-pivot. Runners ordered by 3M momentum descending.

### Integration into `watchlist_scanner.py`

The sync runs automatically at the end of each full scan (non dry-run, non single-ticker):

```python
# After DB writes, before Telegram
if not args.dry_run and not args.ticker:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "schwab_watchlist_sync",
        os.path.join(os.path.dirname(__file__), "schwab_scripts", "schwab_watchlist_sync.py")
    )
    sync_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync_mod)
    wl_result = sync_mod.sync_watchlists()
```

> **Why `importlib.util`?** The directory is named `schwab_scripts/` (not `schwab/`) to avoid namespace conflicts with the installed `schwab` (schwab-py) package. Direct file loading bypasses the conflict.

Telegram filtering also happens at this point — only A/A+ setups are sent to Telegram (same subset as the Schwab watchlist), while the full list is written to the DB.

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| No A/A+ stocks today | `Watch_{date}` skipped; logged |
| No runners today | `Runners_{date}` skipped; logged |
| Watchlist already exists (re-run) | Delete existing, recreate fresh |
| > 50 tickers in either list | Truncate to 50; highest-grade / highest-momentum first |
| Schwab 429 / transient error | Retry once after 5s; if still failing, log and continue |
| `--dry-run` | Skips API calls; prints what would be created |
| `--ticker AAPL` single-ticker | Schwab sync skipped entirely |
| `--schwab-only` | Skips scan; reads DB and syncs directly |
| No DB records found | Logs warning, exits with code 1 |

### Running the Sync

| Command | What it does |
|---------|-------------|
| `python watchlist_scanner.py` | Full scan → DB write → Schwab sync → Telegram |
| `python watchlist_scanner.py --schwab-only` | Skip scan; read DB and push to Schwab only |
| `python schwab_scripts/schwab_watchlist_sync.py` | Standalone sync — latest scan date from DB |
| `python schwab_scripts/schwab_watchlist_sync.py --date 2026-05-05` | Sync a specific past date |
| `python schwab_scripts/schwab_watchlist_sync.py --dry-run` | Print what would be created; no API calls |

---

## Profit Target Alerts (`check_profit_targets.py`) — added 2026-07-08

### What It Does

Implements Rules.MD R36-R38 (sell 1/3-1/2 at 2R, move stop to breakeven, sell another 1/4
at 3R) as **Telegram alerts only — it never places an order.** R29 (initial stop) and R39
(10-day-MA trailing stop) are unaffected and still handled live by `schwab_stop_loss.py`
above; this script only covers the profit-taking side, and only as a notification.

This was a deliberate scope decision: implementing R36-R38 as live order placement would
mean writing code that can sell real shares automatically, which is a materially different
risk profile than adjusting a stop price. Alert-only was chosen over full automation.

Flow:
1. Fetches live Schwab equity positions (ticker + quantity only — read-only, same auth
   pattern as `schwab_stop_loss.py`)
2. For each position, looks up the most recent `breakout_entries` row for that ticker
   (`get_latest_breakout_entry()` in `db_writer.py`) to get the entry price and stop price
   this system's own breakout scanner recorded at detection time
3. Computes the live R-multiple: `(current_price - breakout_price) / risk_per_share`,
   using a real-time price when the market is open, else the latest daily close
4. Sends one Telegram alert per R-level crossed (2R, then separately 3R), recommending what
   Rules.MD says to do — you place the actual order

A position with no matching `breakout_entries` row (predates this system, or wasn't sourced
from an alert) is skipped with a note — there's no reliable way to know its original risk.

### Dedup: `profit_target_alerts` table

One row per `(breakout_id, r_level)`, written after each alert, so a position doesn't get
re-alerted for the same R-level on every run:

```sql
CREATE TABLE profit_target_alerts (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    breakout_id INT NOT NULL,
    ticker      VARCHAR(10) NOT NULL,
    r_level     DECIMAL(3,1) NOT NULL,   -- 2.0 (R36) or 3.0 (R38)
    r_multiple  DECIMAL(6,2) NULL,
    alerted_at  DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (breakout_id) REFERENCES breakout_entries(id)
);
```

### Dependency on the breakout pipeline

This script depends entirely on `breakout_entries` having rows with `stop_price`/
`risk_per_share` — which was empty for 2+ months due to the `avg_30min_volume`
self-referential bug (see `docs/breakout-scanner-plan.md`, issue #11). It will only start
producing real alerts once new breakouts actually get detected and logged going forward.

### Running Manually

```bash
cd scan/
python3 schwab_scripts/check_profit_targets.py              # live — sends Telegram, marks DB
python3 schwab_scripts/check_profit_targets.py --dry-run    # print only, no Telegram, no DB write
```

### Scheduling

**Not currently in `cron_setup.sh`.** Cadence is a deliberate open choice — intraday (to
catch a profit target as soon as it's hit, like `breakout_scanner.py`'s 30-minute cycle) vs.
daily (simpler, alongside `schwab_stop_loss.py` at 8:15 AM, but could miss same-day 2R/3R
moves until the next day). Add manually to `cron_setup.sh` once a cadence is decided.

---

## Full Daily Schedule

| Time (EDT) | UTC | Job |
|------------|-----|-----|
| 8:00 AM | 12:00 | `watchlist_scanner.py` — scan + DB write + Schwab watchlist sync + Telegram |
| 8:15 AM | 12:15 | `schwab_stop_loss.py` — set/raise GTC stops at 10d SMA |
| 9:30 AM | 13:30 | Market opens |
| Every :00/:30 | 13:30–21:00 | `breakout_scanner.py` |
| — | — | `check_profit_targets.py` — **not yet scheduled**, see above |
| 4:30 PM | 20:30 | `performance_tracker.py` |

---

*Created: 2026-05-16 (consolidated from schwab-stop-loss-plan.md, schwab-stop-loss-rate-limit-plan.md, schwab-watchlist-sync-plan.md)*
*Updated: 2026-07-08 — added `check_profit_targets.py` (R36-R38 profit-target alerts, alert-only)*
*See also: `docs/watchlist-plan.md`, `docs/Rules-Reference.MD`, `scan/config.py`, `scan/cron_setup.sh`*
