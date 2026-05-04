# Schwab Stop-Loss Manager — Plan

> A Python script that connects to the Schwab brokerage API, retrieves all open equity
> positions, calculates the 10-day Simple Moving Average (SMA) for each ticker, and
> creates or updates a Good-Till-Cancelled (GTC) stop-loss sell order at the 10-day SMA.

---

## Overview

Run this script manually (or on a schedule) to keep stop-loss orders aligned with the
trailing 10-day SMA across all positions. If a stop already exists for a position, it
is replaced with the updated SMA price. If no stop exists, one is created.

---

## What It Does (Step by Step)

```
1. Authenticate with Schwab API (OAuth2 — app key + secret)
2. Fetch all open positions across linked accounts
3. For each equity position:
   a. Fetch 10 trading days of daily OHLCV history (yfinance fallback if needed)
   b. Calculate 10-day SMA on closing prices
   c. Check for an existing GTC stop-loss order on that ticker
   d. If stop exists  → cancel it, place new stop at SMA price
      If no stop      → place new GTC stop-loss order at SMA price
4. Print a summary: ticker | qty | current price | 10d SMA | stop action taken
```

---

## Schwab API Overview

Token is fetched from Lambda API endpoint. The `schwab-py` library provides
clean wrappers around the Trader API endpoints.

### Authentication Flow
- Fetch token from Lambda endpoint: `https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab?pw=6%2310oz`
- Token is cached to `schwab_token.json` for subsequent runs (5-minute TTL recommended)
- Query the endpoint periodically to refresh the token
- Token file: `scan/schwab_token.json` (excluded from git via `.gitignore`)

### Key Endpoints Used

| Action | Endpoint |
|--------|----------|
| Get accounts + positions | `GET /trader/v1/accounts?fields=positions` |
| Get open orders | `GET /trader/v1/accounts/{acctHash}/orders?status=WORKING` |
| Place order | `POST /trader/v1/accounts/{acctHash}/orders` |
| Cancel order | `DELETE /trader/v1/accounts/{acctHash}/orders/{orderId}` |

---

## Architecture

```
schwab/
├── schwab_stop_loss.py     # Main script
├── schwab_token.json       # OAuth2 token (auto-created, NOT in git)
└── (shared scan/.env for credentials)
```

Runs as a standalone script — no SQL Server dependency, no new tables needed.

---

## Python Code Plan

### `schwab_stop_loss.py`

```python
# 1. Auth — Fetch token from Lambda API
import requests
import json
from datetime import datetime, timedelta

TOKEN_ENDPOINT = "https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab"
TOKEN_PASSWORD = "6#10oz"
TOKEN_FILE = "schwab/schwab_token.json"

def get_or_refresh_token():
    """Fetch token from Lambda API, or use cached token if still valid."""
    # Check if cached token exists and is fresh (< 5 min old)
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            cached = json.load(f)
        if datetime.now() - datetime.fromisoformat(cached['fetched_at']) < timedelta(minutes=5):
            return cached['token']
    
    # Fetch new token from Lambda
    params = {'pw': TOKEN_PASSWORD}
    resp = requests.get(TOKEN_ENDPOINT, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    # Cache token with timestamp
    token_data = {
        'token': data['access_token'],
        'fetched_at': datetime.now().isoformat()
    }
    os.makedirs('schwab', exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f)
    
    return data['access_token']

# Fetch token
access_token = get_or_refresh_token()

# Create schwab client with token
client = schwab.auth.client_from_token_dict(
    token_dict={'access_token': access_token, 'token_type': 'Bearer'},
)

# 2. Get positions
accounts = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
positions = []
for account in accounts.json():
    acct_hash = account["hashValue"]
    for pos in account.get("securitiesAccount", {}).get("positions", []):
        instrument = pos["instrument"]
        if instrument["assetType"] == "EQUITY":
            positions.append({
                "account_hash": acct_hash,
                "ticker":       instrument["symbol"],
                "qty":          pos["longQuantity"],
                "avg_price":    pos["averagePrice"],
                "market_value": pos["marketValue"],
            })

# 3. Compute 10-day SMA for each ticker
for pos in positions:
    df = yf.download(pos["ticker"], period="20d", interval="1d", auto_adjust=True)
    sma_10 = round(df["Close"].tail(10).mean(), 2)
    pos["sma_10"] = sma_10

# 4. Cancel existing stop + place new one
for pos in positions:
    ticker    = pos["ticker"]
    acct_hash = pos["account_hash"]
    sma_10    = pos["sma_10"]
    qty       = int(pos["qty"])

    # Find and cancel any existing GTC STOP orders for this ticker
    orders = client.get_orders_for_account(
        account_hash=acct_hash,
        status=client.Order.Status.WORKING,
    )
    for order in orders.json():
        if (order["orderType"] == "STOP"
                and order["duration"] == "GOOD_TILL_CANCEL"
                and order["orderLegCollection"][0]["instrument"]["symbol"] == ticker):
            client.cancel_order(acct_hash, order["orderId"])
            print(f"  {ticker}: cancelled existing stop @ ${order['stopPrice']:.2f}")

    # Place new GTC stop-loss at 10-day SMA
    order_spec = (
        schwab.orders.equities.equity_sell_market(ticker, qty)
        .set_order_type(schwab.orders.common.OrderType.STOP)
        .set_duration(schwab.orders.common.Duration.GOOD_TILL_CANCEL)
        .set_stop_price(sma_10)
        .build()
    )
    resp = client.place_order(acct_hash, order_spec)
    if resp.status_code in (200, 201):
        print(f"  {ticker}: ✅ stop set @ ${sma_10:.2f} (10d SMA) | qty {qty}")
    else:
        print(f"  {ticker}: ❌ order failed — {resp.status_code} {resp.text}")
```

---

## Output

```
=================================================================
  SCHWAB STOP-LOSS MANAGER — 2026-05-04
=================================================================
  Positions found: 6

  Ticker   Qty   Avg Cost   Current   10d SMA   Action
  ──────────────────────────────────────────────────────────────
  NVDA     100   $115.20    $128.40   $122.50   ✅ stop updated (was $119.00)
  CELH      50   $44.10     $48.20    $46.30    ✅ stop placed (new)
  AXON      25   $295.00    $312.50   $308.10   ✅ stop updated (was $301.00)
  SMCI      75   $26.80     $29.10    $27.90    ✅ stop placed (new)
  CRWD      30   $380.00    $410.00   $398.20   ✅ stop updated (was $390.00)
  TSLA      40   $240.00    $265.00   $258.40   ✅ stop placed (new)
  ──────────────────────────────────────────────────────────────
  6/6 stops set successfully
```

---

## Config & Credentials

Credentials are loaded from `scan/.env` (not committed to git):

```env
SCHWAB_APP_KEY=your_app_key
SCHWAB_SECRET=your_secret
```

Token file is created on first run at `schwab/schwab_token.json`.
Add to `.gitignore`: `schwab/schwab_token.json`.

---

## Dependencies

```bash
pip install schwab-py           # Official Schwab API client
pip install yfinance            # Price history (already installed)
pip install python-dotenv       # .env loading (already installed)
```

Add to `requirements.txt`:
```
schwab-py>=1.4.0
```

---

## Scheduling (Cron)

The script runs automatically every weekday at **8:15 AM EDT (12:15 UTC)** —
15 minutes after the watchlist scanner, well before the market opens at 9:30 AM.

```
# Cron schedule (installed via cron_setup.sh or manually)
15 12 * * 1-5  cd scan/ && python3 schwab/schwab_stop_loss.py >> logs/schwab_stop_loss.log 2>&1
```

Full daily schedule:

| Time (EDT) | UTC | Job |
|------------|-----|-----|
| 8:00 AM | 12:00 | `watchlist_scanner.py` — scan full market |
| 8:15 AM | 12:15 | `schwab_stop_loss.py` — set GTC stops at 10d SMA |
| 9:30 AM | 13:30 | Market opens |
| Every :00/:30 | 13:30–20:00 | `breakout_scanner.py` |
| 4:30 PM | 20:30 | `performance_tracker.py` |

Check the log:
```bash
tail -50 /home/ubuntu/.openclaw/workspace/stocks-repo/scan/logs/schwab_stop_loss.log
```

---

## First-Run Authentication

No manual OAuth2 flow needed. The script automatically fetches the token from the Lambda API.

**First run:**
```bash
cd scan
python3 schwab/schwab_stop_loss.py --dry-run
# Token automatically fetched from Lambda, cached to schwab/schwab_token.json
```

Subsequent runs reuse the cached token (refreshed every 5 minutes).

Normal run / dry run:
```bash
python3 schwab/schwab_stop_loss.py --dry-run   # preview, no orders placed
python3 schwab/schwab_stop_loss.py             # live
```

**Token endpoint:**
```
GET https://hcapr4ndhwksq5dq7ird3yujpq0edbbt.lambda-url.us-east-1.on.aws/api/token/schwab?pw=6%2310oz

Response:
{
  "access_token": "<token_string>",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

---

## Safety Notes

- **Always dry-run first** (`--dry-run`) to verify SMA prices before live orders
- Stop price is rounded to 2 decimal places
- Script only touches EQUITY positions — options are skipped
- Only long positions are handled (`longQuantity > 0`)
- Orders with `qty = 0` are skipped
- The script cancels the old stop before placing the new one — there is a brief window
  with no stop. Future improvement: place new stop first, then cancel old.

---

## Phased Rollout

| Phase | Work | Outcome |
|-------|------|---------| 
| 1 | Install `schwab-py`, run `--auth` flow | Token file created, API confirmed working |
| 2 | Build position fetch + print | Confirm accounts and positions are returned correctly |
| 3 | Add SMA calculation | Verify 10d SMA values look correct vs charting tool |
| 4 | Add dry-run mode | Full simulation before any live orders |
| 5 | Add cancel + place order logic | Live orders placed on first confirmed run |
| 6 | Add scheduling (optional) | Cron at market open or after close to keep stops current |

---

## Known Behaviour / Constraints

- **Schwab dev API rate limit:** ~60s between order placements. Script sleeps 65s between each position. 5 positions = ~6 min total runtime. This is expected for developer-tier apps.
- **SMA ≥ current price:** Positions where the 10d SMA is at or above the current price are skipped — placing a stop there would trigger an immediate fill.
- **`PENDING_ACTIVATION` is normal:** GTC stop orders show as `PENDING_ACTIVATION` outside market hours. They activate at the open.
- **Duplicate stops from retries:** If the script is run multiple times (or retried), duplicate stops may appear. The cancel-existing logic handles this on the next run.

---

## Tech Debt / Future Improvements

- Replace cancel-then-place with place-then-cancel (eliminates brief stop gap)
- Support short positions (`shortQuantity > 0`) with buy-stop orders
- Add ATR-based floor: never set stop below `SMA - 1×ATR` to avoid noise stops
- Add Telegram notification after each run (mirrors watchlist scanner pattern)
- Support percentage-based stop as an alternative to SMA (config flag)
- Cache SMA calculations to avoid redundant yfinance calls if run multiple times per day
- Investigate Schwab production API approval to lift the 60s rate limit

---

## Implementation Notes

| Date | Change |
|------|--------|
| 2026-05-04 | Initial implementation. Auth via `client_from_manual_flow` (headless). |
| 2026-05-04 | Account hash fetched via `get_account_numbers()` (not in positions response). |
| 2026-05-04 | 65s sleep between order placements to handle Schwab dev API rate limit. |
| 2026-05-04 | Cron installed: 8:15 AM EDT (12:15 UTC) weekdays. |
| 2026-05-04 | **[TOKEN BRANCH]** Switched to Lambda API token endpoint. No browser OAuth2 needed. Token cached locally (5-min TTL). |

---

*Created: 2026-05-04*
*See also: `plans/watchlist-plan.md`, `scan/config.py`, `scan/cron_setup.sh`*
