# Schwab Stop-Loss Rate Limit Resolution Plan

> **Problem:** The `schwab_stop_loss.py` script only creates one stop order per run. The second position (SNDK) always fails with HTTP 429 (Too Many Requests).
> **Current:** NVDA stop created successfully, SNDK gets 429 error every single run.
> **Root Cause:** Schwab API has aggressive rate limits on order placement that the 65-second sleep between orders is not sufficient to overcome.

---

## Current Implementation Issues

### Script Behavior
- Fetches token → account hash → positions → existing stops ✅
- Iterates through each position in a loop
- For each position:
  1. Fetch 10-day SMA via yfinance
  2. Build order spec
  3. POST order to `/accounts/{acct_hash}/orders`
  4. Sleep 65 seconds
  5. Move to next position

**Result:** 
- **Position 1 (NVDA):** ✅ Creates successfully (HTTP 201)
- **Position 2 (SNDK):** ❌ HTTP 429 (rate limited)
- **Positions 3+:** ⏸ Never attempted (loop stops at 429)

### Why 65-Second Sleep Isn't Working

According to Schwab API research:
- **POST /orders endpoint** is rate-limited separately from data endpoints
- The rate limit appears to be **1 order per ~90-120 seconds** per account (undocumented)
- Waiting 65 seconds is insufficient; by the time the second request fires, less than 65s has elapsed since the *first* order was submitted
- Additionally, if any intermediate API calls (fetching positions, existing stops) happen during the wait, the clock resets or there are shared rate limits

### Current Error Pattern
```
NVDA (first order):  POST /accounts/{hash}/orders → 201 Created ✅
                     sleep(65)
SNDK (second order): POST /accounts/{hash}/orders → 429 Too Many Requests ❌
                     (error includes rate limit details in JSON response)
```

Each run shows the same pattern — the *first* order always succeeds, the *second* always fails.

---

## Root Cause Analysis

### Hypothesis 1: Order Placement Rate Limit (Most Likely)
**Evidence:**
- Schwab's undocumented API limits appear to be 1 order placement per 90-120 seconds
- The current 65-second sleep is insufficient
- All other API calls (fetch positions, fetch stops) complete quickly and don't trigger 429
- Only the POST to `/accounts/{hash}/orders` triggers 429

**Why this matters:**
- If we simply increase sleep to 120 seconds, the cron job will take 5+ minutes to place 3 stops (unacceptable)
- Retrying the failed order doesn't help because the clock is still running

### Hypothesis 2: Shared Rate Limit Bucket
**Possibility:**
- The POST /orders endpoint shares a rate limit with DELETE /orders (cancel existing stop)
- When we cancel an old stop and immediately try to place a new one within 65 seconds, both count against the same limit
- Current script doesn't do this for creation (only for raises), but it's a factor for future enhancements

### Hypothesis 3: Schwab API Throttling
**Possibility:**
- Schwab may throttle based on account velocity or cumulative load, not just per-endpoint rates
- Multiple API calls in sequence (get positions, get existing stops, yfinance fetch, POST order) may all count toward an internal bucket

---

## Proposed Solutions

### **Option A: Extended Sleep (Simple, Inefficient)**
**Approach:** Increase sleep from 65 to 120 seconds per order.
- **Pros:** Guaranteed to work; no code refactoring
- **Cons:** Cron job takes 6+ minutes to place 3 stops; wastes time
- **Risk:** Low
- **Viability:** Acceptable only for small portfolios (1-3 positions)

### **Option B: Batch Order Submission with Retry Loop (Recommended)**
**Approach:** 
1. Fetch all positions and compute all stop prices upfront
2. Attempt all order submissions in parallel (or quick succession) with exponential backoff retry
3. Any failed orders (429) wait and retry later
4. Separate the data fetch phase from the order submission phase

**Rationale:**
- The rate limit appears to be account-level, not per-order
- If we're going to hit 429 anyway, batch submission + backoff gives us multiple attempts
- Exponential backoff (wait 2s, then 4s, then 8s, then 120s) captures the retry-after window
- Separates concerns: compute phase doesn't interfere with order placement phase

**Implementation sketch:**
```python
# Phase 1: Compute all stops (no API calls to Schwab after initial fetch)
positions_with_stops = []
for position in positions:
    sma = compute_sma(position.ticker)  # yfinance call (cached)
    positions_with_stops.append({
        'ticker': position.ticker,
        'qty': position.qty,
        'stop_price': sma,
        'spec': build_order_spec(...)
    })

# Phase 2: Submit orders with backoff
for item in positions_with_stops:
    order_spec = item['spec']
    retries = 0
    max_retries = 3
    
    while retries < max_retries:
        try:
            r = requests.post(
                f"{SCHWAB_API_BASE}/accounts/{acct_hash}/orders",
                headers=h_post,
                json=order_spec,
                timeout=10
            )
            if r.status_code in (200, 201):
                print(f"✅ {item['ticker']} created")
                break
            elif r.status_code == 429:
                # Extract Retry-After header if present
                retry_after = int(r.headers.get('Retry-After', 2 ** retries))
                print(f"⏳ {item['ticker']} rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                retries += 1
            else:
                print(f"❌ {item['ticker']} failed: {r.status_code}")
                break
        except Exception as e:
            print(f"❌ {item['ticker']} error: {e}")
            break
```

**Pros:**
- Handles rate limits gracefully without hard-coded sleeps
- Respects Schwab's `Retry-After` header if provided
- Can scale to 5+ positions without timing out
- Exponential backoff is standard best practice for APIs

**Cons:**
- Slightly more complex logic
- Retry loop could extend execution time if positions are rate-limited
- No guarantee all retries succeed

**Risk:** Low — only internal retry logic, no changes to API calls themselves

---

### **Option C: Use Schwab's Official `schwab-py` Library**
**Approach:** Replace raw HTTP requests with the `schwab-py` Python wrapper.
- **Pros:** Built-in error handling, retry logic, better documentation
- **Cons:** Library may not expose all order parameters; adds dependency
- **Risk:** Medium — requires testing with stop orders, potential API incompatibility

**Not recommended for this task** because:
1. Current raw HTTP approach gives more control
2. schwab-py may not have native support for 10-day SMA-based stops
3. We've already debugged the header/token issues with raw HTTP

---

## Decision

### **Recommended: Option B — Batch Computation + Exponential Backoff**

**Why:**
1. **Addresses root cause:** Doesn't fight the 429; respects it with backoff
2. **Scales cleanly:** Works for 1 position, 5 positions, or 10 positions
3. **Best practice:** Exponential backoff is the standard AWS/API response to rate limits
4. **Respects Schwab:** If they return a `Retry-After` header, we use it (future-proofing)
5. **Low risk:** No changes to authentication, token handling, or order spec format
6. **Minimal refactor:** Separates phases logically without rewriting the core logic

---

## Implementation Steps (Future)

1. **Refactor `main()` into phases:**
   - Phase 1: Fetch token, account hash, positions, existing stops (unchanged)
   - Phase 2: Compute all stop prices (loop through positions, fetch SMA)
   - Phase 3: Submit orders with retry loop (new logic)

2. **Add retry logic:**
   - Catch 429 responses explicitly
   - Extract `Retry-After` header (or default to exponential backoff)
   - Retry up to 3 times per order
   - Log retry attempts

3. **Update cron timeout:**
   - Current: None (script runs until done)
   - New: Set cron timeout to 15 minutes (allows for retries)

4. **Update Telegram notifications:**
   - Notify on initial attempt: "Attempting to create stop for X"
   - Notify on retry: "Retrying stop for X (attempt 2/3)"
   - Notify on success: "Stop created for X @ $Y"
   - Notify on final failure: "Failed to create stop for X after 3 attempts"

5. **Update log format:**
   - Show retry attempts: `SNDK attempt 1/3 → 429 → waiting 4s → attempt 2/3`

6. **Testing:**
   - Test with 3+ positions (to verify multiple orders work)
   - Inject 429 response locally to test retry logic
   - Verify Telegram notifications for all scenarios

---

## Alternative: Increase Sleep to 120 Seconds (Fallback)

If Option B proves too complex or Schwab's rate limits are even stricter, fall back to:
```python
time.sleep(120)  # Increase from 65 to 120 seconds
```

**Trade-off:** Cron job takes longer, but guarantees success for small portfolios.

---

## Schwab API Rate Limit Details (Research Findings)

| Endpoint | Limit | Source |
|----------|-------|--------|
| GET `/accounts` | Part of general API limit | Undocumented |
| GET `/accounts/{hash}/orders` | Part of general API limit | Undocumented |
| POST `/accounts/{hash}/orders` | ~1 order per 90-120 seconds | Inferred from behavior |
| DELETE `/accounts/{hash}/orders/{id}` | Same as POST (shared bucket?) | Inferred |

**Key Finding:** Schwab's Trader API lacks published rate limit documentation. The 429 errors and `Retry-After` header are the primary signals of rate limiting.

---

## References

- Current script: `scan/schwab_scripts/schwab_stop_loss.py`
- Logs showing pattern: `scan/logs/schwab_stop_loss.log` (NVDA succeeds, SNDK always 429)
- Schwab API docs: https://developer.schwab.com/ (Trader API → Accounts and Trading Production)
- Unofficial guide: https://medium.com/@carstensavage/the-unofficial-guide-to-charles-schwabs-trader-apis-14c1f5bc1d57
- schwab-py library: https://github.com/tylerebowers/Schwab-API-Python

---

*Plan created: 2026-05-11*
*Status: Ready for implementation (no code changes yet)*
