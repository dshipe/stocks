# Quallamaggie SMA Trailing Stop Implementation Plan

**Date:** 2026-06-02  
**Status:** PLANNING  
**Goal:** Implement SMA-based trailing stop that executes on daily close below SMA

---

## Current State

**Current Implementation (`schwab_stop_loss.py`):**
- Sets GTC (Good-Till-Cancelled) stops at **10-day SMA** of entry price
- Only **raises** stops, never lowers
- Static order submitted once, doesn't adapt to SMA movement
- Sends Telegram notification for order status

**Limitation:**
- Stop price doesn't trail upward as stock rises and SMA increases
- No mechanism to execute on "daily close below SMA"

---

## Quallamaggie SMA Trailing Stop Strategy (Simplified)

### Core Logic
1. **After Entry:** Set initial stop at 10-day SMA (current behavior ✓)
2. **Daily Check:** Each trading day, compute new 10-day SMA
3. **Trailing Rule:** 
   - If new SMA > current stop price → raise stop to new SMA
   - If new SMA ≤ current stop price → keep stop unchanged (never lower)
4. **Exit Condition:** Position exits when **daily close falls below current stop price**
   - NOT just hitting the stop; requires actual daily close below it

### Key Principle
- Stop **ratchets upward** with rising SMA
- Stop **never falls** even if SMA dips
- Exit triggers on daily close, not intraday touch

---

## The Challenge: Daily Close Below SMA

### Problem
Schwab's GTC stop orders execute on any trade hitting the price, not specifically on "daily close below SMA." 

Options:

**Option A: Set Stop = SMA, Monitor Daily**
- Set GTC stop at current SMA value (Schwab order)
- Schwab executes whenever price touches stop (intraday or close)
- Daily monitor script checks: Did close end below yesterday's SMA?
- If YES: Do nothing (order will execute today or next day)
- If NO: Raise stop to today's SMA

**Risk:** Intraday spike/dip could trigger stop before daily close validation

**Option B: Manual Daily Exit Workflow** (Recommended)
- Do NOT set GTC stops for trailing portion
- Daily script (at market close):
  1. Fetch today's close price
  2. Fetch yesterday's 10-day SMA
  3. Compare: close < SMA?
  4. If YES: Send Telegram alert "Ready to Exit"
  5. User manually sells at market open next day
- Set a GTC stop as **backup** only for emergency gaps (not scale-out version)

**Option C: Automated Daily Exit (More Complex)**
- Daily script at 4:15 PM ET (15 min before close)
  1. Compute current SMA
  2. If current intraday price is below SMA → place market sell order
  3. Execute during final 15 minutes
- Requires active monitoring, not set-and-forget

**Option D: Hybrid Approach** (Practical)
- Set GTC stop at SMA (for accidental/gap protection)
- Daily monitor script raises stop to new SMA each day
- Alert user if close is near or below SMA (for manual review)
- User decides: hold overnight or sell

---

## Recommended Implementation: Option B (Manual Daily Exit Alerts)

### Why?
- Quallamaggie himself uses alerts + manual execution (not pure automation)
- Ensures you capture "daily close below SMA" not intraday touches
- Aligns with "daily close" requirement
- Less API call overhead
- Clear audit trail of decisions

### Workflow

**Daily Stop Update (`update_trailing_stops.py` - runs at 8:00 AM EST):**
```
For each open position:
  1. Fetch yesterday's SMA10
  2. Fetch current GTC stop price
  3. If yesterday's SMA10 > current stop:
     - Raise stop to yesterday's SMA10
     - Send Telegram: "Stop raised from $X to $Y"
     - Log to DB
  4. Else:
     - Log: "Stop held at $X"
```

**Daily Exit Monitor (`check_sma_exits.py` - runs at 4:30 PM EST):**
```
For each open position:
  1. Fetch today's OHLCV
  2. Fetch today's SMA10
  3. If today's close < SMA10:
     - Send Telegram alert:
       "⚠️ SELL SIGNAL: $TICKER
        Today close: $X (below SMA10: $Y)
        Action: Ready to exit. Sell at market open tomorrow?"
     - Mark in DB: ready_for_exit = true
  4. Else:
     - Log: "Position still above SMA"
```

**User Action:**
- Reviews Telegram alert before market open next day
- Manually sells via Schwab app or API market order
- Records exit in DB

---

## Implementation Details

### Phase 1: Database Schema Updates

**Modify `breakout_entries` table:**
```sql
ALTER TABLE breakout_entries ADD COLUMN
  entry_date              DATE,
  entry_price             DECIMAL(10,4),
  current_stop_price      DECIMAL(10,4),
  trailing_start_date     DATE,
  last_sma_10             DECIMAL(10,4),
  sma_as_of_date          DATE,
  is_position_closed      BOOLEAN DEFAULT 0,
  close_date              DATE,
  close_price             DECIMAL(10,4),
  close_reason            VARCHAR(50),
  last_stop_update_date   DATE,
  days_held               INT;
```

**New table: `position_trailing_log`:**
```sql
CREATE TABLE position_trailing_log (
  id                  INT PRIMARY KEY IDENTITY(1,1),
  breakout_id         INT,
  ticker              VARCHAR(10),
  log_date            DATE,
  sma_10              DECIMAL(10,4),
  previous_stop       DECIMAL(10,4),
  new_stop            DECIMAL(10,4),
  action              VARCHAR(20),  -- 'raised' | 'held'
  reason              VARCHAR(255),
  created_at          DATETIME DEFAULT GETDATE()
);
```

**New table: `position_exit_alerts`:**
```sql
CREATE TABLE position_exit_alerts (
  id                  INT PRIMARY KEY IDENTITY(1,1),
  breakout_id         INT,
  ticker              VARCHAR(10),
  alert_date          DATE,
  close_price         DECIMAL(10,4),
  sma_10              DECIMAL(10,4),
  alert_sent          BOOLEAN,
  telegram_message    TEXT,
  user_action         VARCHAR(50),  -- 'sold' | 'held' | 'pending'
  created_at          DATETIME DEFAULT GETDATE()
);
```

### Phase 2: Core Functions

**Function 1: Daily Stop Update**
```python
def update_trailing_stops(dry_run=False):
    """
    Run at 8:00 AM EST daily.
    For each open position, check if SMA has risen since last update.
    Raise GTC stop if needed.
    """
    positions = get_open_positions()  # DB query
    
    for pos in positions:
        ticker = pos['ticker']
        df = fetch_history(ticker, days=20)
        yesterday_sma = df.iloc[-2]['sma_10']  # day before today
        current_stop = pos['current_stop_price']
        
        if yesterday_sma > current_stop:
            # Update GTC stop via Schwab API
            raise_stop_order(ticker, current_stop, yesterday_sma)
            log_stop_update(ticker, current_stop, yesterday_sma, 'raised')
            send_telegram(f"✅ Stop raised: {ticker} ${current_stop} → ${yesterday_sma}")
        else:
            log_stop_update(ticker, current_stop, current_stop, 'held')
    
    if not dry_run:
        save_to_db()
```

**Function 2: Daily Exit Alert**
```python
def check_sma_exits(dry_run=False):
    """
    Run at 4:30 PM EST daily (market close).
    Check if any open positions closed below their SMA10.
    Alert user via Telegram.
    """
    positions = get_open_positions()
    
    for pos in positions:
        ticker = pos['ticker']
        df = fetch_history(ticker, days=20)
        
        today = df.iloc[-1]
        today_close = today['close']
        today_sma = today['sma_10']
        
        if today_close < today_sma:
            msg = (
                f"🔔 EXIT ALERT\n"
                f"Ticker: {ticker}\n"
                f"Today close: ${today_close:.2f}\n"
                f"SMA10: ${today_sma:.2f}\n"
                f"→ Close below SMA. Ready to exit tomorrow?"
            )
            send_telegram(msg)
            log_exit_alert(ticker, today_close, today_sma, msg)
        else:
            days_above = df[df['close'] > df['sma_10']].shape[0]
            print(f"{ticker}: Close above SMA ({days_above} consecutive days)")
    
    if not dry_run:
        save_to_db()
```

**Function 3: Manual Exit Execution** (User triggers)
```python
def manual_exit_position(ticker, qty, exit_reason="daily_close_below_sma"):
    """
    User-initiated market sell order.
    Called after Telegram alert review.
    """
    # Get current market price
    price = get_current_price(ticker)
    
    # Place market order
    order_id = place_market_sell_order(ticker, qty)
    
    # Log to DB
    close_position(ticker, price, exit_reason, order_id)
    
    # Confirm via Telegram
    send_telegram(f"✅ Sold {qty} shares of {ticker} @ ${price:.2f}")
```

### Phase 3: New Scripts

**Script 1: `update_trailing_stops.py`**
```bash
#!/usr/bin/env python3
"""
Daily trailing stop updater.
Compares yesterday's SMA to current stop, raises if needed.
Run at 8:00 AM EST (12:00 UTC) weekdays.
"""
```

**Script 2: `check_sma_exits.py`**
```bash
#!/usr/bin/env python3
"""
Daily exit monitor.
Alerts user if any position closed below SMA10.
Run at 4:30 PM EST (20:30 UTC) weekdays.
"""
```

### Phase 4: Cron Jobs

```bash
# 8:00 AM EST (12:00 UTC) — Update trailing stops
0 12 * * 1-5 cd /home/ubuntu/.openclaw/workspace/stocks-repo && \
  python3 scan/update_trailing_stops.py >> scan/logs/trailing_stops.log 2>&1

# 4:30 PM EST (20:30 UTC) — Check for SMA exit signals
30 20 * * 1-5 cd /home/ubuntu/.openclaw/workspace/stocks-repo && \
  python3 scan/check_sma_exits.py >> scan/logs/sma_exits.log 2>&1
```

### Phase 5: Configuration

**Update `config.py`:**
```python
# Trailing stop configuration
TRAILING_STOP_SMA_PERIOD = 10       # days for SMA calculation
TRAILING_STOP_MIN_DAYS_HELD = 1     # begin trailing immediately after entry
```

---

## Workflow Summary

```
Day 1 (Breakout Entry)
├─ breakout_scanner.py detects breakout
├─ schwab_stop_loss.py creates GTC stop at 10d SMA
├─ position added to DB with current_stop_price
└─ Telegram: "✅ Stop created at $X"

Day 2 (8:00 AM)
├─ update_trailing_stops.py runs
├─ Computes yesterday's SMA (more data points now)
├─ If SMA > stop → Raise GTC stop via API
├─ Log to position_trailing_log
└─ Telegram: "Stop raised $X → $Y" (if raised)

Day 2 (4:30 PM)
├─ check_sma_exits.py runs at market close
├─ Checks: Did close < today's SMA?
├─ If YES → Log to position_exit_alerts
└─ Telegram: "⚠️ SELL SIGNAL: Close below SMA. Exit tomorrow?"

Day 3 (User Action)
├─ User reviews Telegram alert
├─ Manually sells via Schwab (market order)
├─ Records exit in DB via manual_exit_position()
└─ Telegram: "✅ Sold 1667 shares @ $210.50"

Repeat: Days continue with daily SMA updates until close < SMA
```

---

## Comparison: GTC Stop vs. Daily Alerts

| Aspect | Pure GTC Stop | Daily Alert + Manual |
|--------|---------------|---------------------|
| **Exit Trigger** | Intraday hit of stop price | Daily close below SMA |
| **Ratcheting** | Manual daily updates | Automated check each morning |
| **Speed** | Instant (worst case: wrong price) | Deliberate (next market open) |
| **Control** | No — automatic | Yes — manual confirmation |
| **Quallamaggie Alignment** | Not quite | Yes — his method uses alerts |
| **API Calls** | High (update each day) | Low (2 scripts/day) |
| **Complexity** | Moderate | Low |

---

## Key Design Decisions

1. **No Scale-Out:** Full position held until SMA exit signal
2. **No Hard Stop:** Rely on GTC stop as only protection; trust SMA
3. **Daily Alerts:** User reviews and executes manually (not automated sell)
4. **Ratcheting Only:** Stop rises with SMA but never falls
5. **SMA10 Only:** Fixed 10-day period; no dynamic switching

---

## Implementation Roadmap

### Week 1: Database & Core Logic
- [ ] Deploy schema changes (position_trailing_log, position_exit_alerts tables)
- [ ] Write `update_trailing_stops()` function
- [ ] Write `check_sma_exits()` function
- [ ] Unit tests

### Week 2: Scripts & Cron
- [ ] Create `update_trailing_stops.py` script
- [ ] Create `check_sma_exits.py` script
- [ ] Set up cron jobs (8:00 AM & 4:30 PM)
- [ ] Test on paper account with 1-2 positions

### Week 3: Integration & Monitoring
- [ ] Integrate with existing Telegram notifications
- [ ] Add manual exit flow (`manual_exit_position()`)
- [ ] Test edge cases (gaps, splits, extreme moves)
- [ ] Documentation & runbooks

---

## Risk Mitigation

1. **Overnight Gaps:** User reviews alerts before market open; can skip if gap is minor
2. **False Alerts:** If SMA is choppy (rare), user has discretion to hold
3. **Forgotten Exits:** Cron logs all alerts; dashboard shows pending exits
4. **API Failures:** Fallback to manual stop adjustment via Schwab UI

---

## Success Metrics

- **Capture Trends:** Positions held longer than current approach
- **Better Exits:** Exits at daily close (not intraday touches)
- **Clear Signals:** User receives clear Telegram alerts with prices
- **Audit Trail:** DB logs every stop update and alert

---

## Example Execution

```
NVDA Breakout on 2026-06-01
├─ Entry: $210.00, Qty: 1667
├─ Stop created: $205.50 (10d SMA on entry day)

2026-06-02 (Day 1)
├─ 8:00 AM: update_trailing_stops() → SMA10 = $206.25 → Stop raised to $206.25
├─ 4:30 PM: check_sma_exits() → Close $212.50 > SMA $206.25 → No action

2026-06-03 (Day 2)
├─ 8:00 AM: update_trailing_stops() → SMA10 = $208.00 → Stop raised to $208.00
├─ 4:30 PM: check_sma_exits() → Close $214.00 > SMA $208.00 → No action

2026-06-04 (Day 3)
├─ 8:00 AM: update_trailing_stops() → SMA10 = $210.50 → Stop raised to $210.50
├─ 4:30 PM: check_sma_exits() → Close $209.80 < SMA $210.50 → ALERT SENT
├─ Telegram: "⚠️ EXIT ALERT: NVDA close $209.80 below SMA $210.50. Exit tomorrow?"

2026-06-05 (Day 4 — User Action)
├─ User sees alert, decides to exit
├─ Places market sell order: 1667 shares @ $211.25
├─ manual_exit_position('NVDA', 1667) logs exit
├─ Telegram: "✅ Sold 1667 NVDA @ $211.25"
├─ Position closed, profit = ~$1,675 ($211.25 - $210.00) * 1667
```

---

## Next Steps

1. **Review** this simplified plan with Dan
2. **Approve** database schema
3. **Begin** Phase 1 (database changes)
4. **Code** Phase 2 (core functions)
5. **Test** on paper account before live
