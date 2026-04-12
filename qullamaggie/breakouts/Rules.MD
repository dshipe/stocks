# Qullamaggie Breakout Setup — Rules

> A comprehensive checklist of criteria for identifying and trading the Qullamaggie-style breakout setup.
> These rules can be applied programmatically to stock screeners and candlestick chart data.

---

## Stage 1: Stock Universe Filter (Minimum Requirements)

These filters must be met before evaluating any setup. Screen the entire market with these first.

| Rule | Criterion | Notes |
|------|-----------|-------|
| R1 | Price ≥ $5.00 | Filter out penny stocks |
| R2 | Average Daily Volume (20-day) ≥ 300,000 shares | Ensures institutional liquidity |
| R3 | Average Daily Range (ADR%) ≥ 3% | Ensures enough daily movement for profit |
| R4 | Stock is in a liquid sector (not OTC, pink sheets) | Avoid illiquid names |
| R5 | Market cap ≥ $300M preferred | Focus on institutional-quality stocks |

---

## Stage 2: Prior Move Requirement (Trend Qualification)

The stock must have made a powerful prior move to qualify as a breakout candidate.

| Rule | Criterion | Lookback |
|------|-----------|----------|
| R6 | Price increased ≥ 30% from a low point | Within 8 weeks (40 trading days) |
| R7 | Prior move had at least 1 day with volume ≥ 2× average | During the explosive phase |
| R8 | There is a clear identifiable catalyst (earnings, news) | Optional but strongly preferred |
| R9 | Stock is within 10–20% of its 52-week high at time of base | Must be near the highs |
| R10 | The prior move was ≥ 50% more than the S&P 500 return in same period | Confirms market leadership |

---

## Stage 3: Base / Consolidation Quality

The stock must form a tight, orderly base after the prior explosive move.

| Rule | Criterion | Measurement |
|------|-----------|-------------|
| R11 | Consolidation duration: 5 to 40 trading days | After the high of the prior move |
| R12 | Base depth: high-to-low range ≤ 15% (ideally ≤ 10%) | (High – Low) / High × 100 |
| R13 | No single candle in base exceeds 10% body range | No massive distribution days |
| R14 | Price does not close below the 50-day moving average during base | Trend integrity |
| R15 | Price stays above the 20-day moving average for most of the base | Short-term trend intact |
| R16 | The 10-day MA is above the 20-day MA during consolidation | Short-term bullish structure |
| R17 | Base has at least 2 volume-contraction legs (VCP) | Each leg is smaller than the prior |
| R18 | No earnings announcement within the base (or earnings caused the move up) | Avoid surprise risk in base |

---

## Stage 4: Volume Contraction During Base

Volume must dry up inside the consolidation. This confirms that sellers are absent.

| Rule | Criterion | Measurement |
|------|-----------|-------------|
| R19 | Average volume in the base is ≤ 60% of the 50-day volume average | (Base avg vol) / (50-day avg vol) |
| R20 | At least 3 consecutive days of below-average volume before the breakout | Immediately before pivot break |
| R21 | No distribution days (high-volume down days) in final 5 days of base | Confirms no institutional selling |
| R22 | Volume declines as the base narrows (VCP pattern visible) | Volume profile slopes downward |

---

## Stage 5: Breakout Trigger — Entry Confirmation

The actual entry signal. These rules define the precise buy trigger.

| Rule | Criterion | Notes |
|------|-----------|-------|
| R23 | Price breaks above the high of the consolidation base (pivot price) | This is the breakout line |
| R24 | Breakout volume ≥ 150% of 20-day average volume (intraday or daily) | Confirms institutional demand |
| R25 | Breakout candle closes near its high (within 5% of candle top) | Strong close = conviction |
| R26 | Breakout does not occur within 3 trading days of an earnings report | Avoids earnings gap risk |
| R27 | Broad market (S&P 500 or NASDAQ) is in an uptrend on breakout day | Market confirms |
| R28 | For intraday: enter on break of 1-min or 5-min Opening Range High (ORH) | Aggressive intraday entry |

---

## Stage 6: Risk Management and Position Sizing

These rules govern how much to buy and where to exit if wrong.

| Rule | Criterion | Formula |
|------|-----------|---------|
| R29 | Initial stop = below the consolidation low | Stop price = base low − 0.5% buffer |
| R30 | Stop distance ≤ 1× Average True Range (ATR-14) from entry | Prevents overly wide stops |
| R31 | Max risk per trade = 0.5% of total account (range: 0.25%–1%) | Dollar Risk = Account × 0.5% |
| R32 | Share size = Dollar Risk ÷ (Entry – Stop) | Standard position sizing |
| R33 | Max overnight position = 20% of account per stock | Concentration limit |
| R34 | Do not buy > 1% of the stock's average daily volume | Prevents slippage |
| R35 | Minimum reward-to-risk ratio ≥ 2:1 before entry | (Target – Entry) / (Entry – Stop) |

---

## Stage 7: Profit Taking and Exit Rules

Rules for managing a winning trade.

| Rule | Criterion | Action |
|------|-----------|--------|
| R36 | At 2R profit: sell 1/3 to 1/2 of position | Lock in partial profit |
| R37 | After partial profit: move stop to breakeven (entry price) | Protect remaining position |
| R38 | At 3R profit: sell another 1/4 of original position | Scale out further |
| R39 | Trail remaining with 10-day MA close | Sell when close below 10-day MA |
| R40 | Alternative trail: sell on close below 20-day MA (for larger trends) | For extended movers |
| R41 | Exit full position if stock closes back below the pivot/breakout level | Failed breakout |
| R42 | Do not hold through earnings without a significant profit cushion (≥ 30%) | Earnings event risk |

---

## Stage 8: Market Conditions Filter

Only trade breakouts in favorable market environments.

| Rule | Criterion | Notes |
|------|-----------|-------|
| R43 | S&P 500 is above its 50-day and 200-day moving averages | Broad uptrend |
| R44 | Market is not in a confirmed distribution phase (multiple high-volume down days) | No overhead selling |
| R45 | VIX (volatility index) is not in an extreme spike (VIX < 30 preferred) | Low fear = better breakouts |
| R46 | Sector the stock belongs to is in an uptrend | Sector tailwind adds conviction |

---

## Quick Checklist (Go/No-Go at Breakout)

Use this before entering any trade:

```
PRE-ENTRY BREAKOUT CHECKLIST
=============================
[ ] R1-R5:  Stock meets universe filters (price, volume, ADR)
[ ] R6-R10: Stock had a prior explosive move of 30%+
[ ] R11-R18: Base is tight and orderly (≤15% depth, 5-40 days)
[ ] R19-R22: Volume has contracted significantly in the base
[ ] R23-R27: Breakout is happening NOW with expanded volume
[ ] R28:    Entry is on ORH or confirmed close above pivot
[ ] R29-R35: Stop is placed, position is sized correctly
[ ] R35:    Risk/reward is at least 2:1
[ ] R43-R46: Market conditions are favorable

ALL BOXES CHECKED → ENTER TRADE
ANY RED FLAG → SKIP THIS SETUP
```

---

## Pattern-Specific Criteria

### High-Tight Flag (HTF)
- Prior move: 50–100%+ in under 8 weeks
- Flag depth: less than 20% pullback from the high
- Flag duration: 1–4 weeks
- Breakout: above the flag high on volume surge

### Flat Base / Rectangle
- Prior move: 30%+ in under 12 weeks
- Base depth: less than 10% range
- Duration: 2–8 weeks
- Breakout: above the flat base high on volume

### Pennant / Triangle
- Prior move: 30%+ (the flagpole)
- Higher lows and lower highs converge to apex
- Volume contracts as apex approaches
- Breakout: above upper trendline on volume

### Volatility Contraction Pattern (VCP)
- Series of contractions, each smaller than the last (e.g., 20%, 12%, 7%, 3%)
- Volume declines with each contraction
- Final contraction is very tight: 3–5% range
- Breakout: above the final contraction high on volume

### Episodic Pivot (EP)
- 8%+ gap up on earnings or major catalyst
- Massive opening volume (100%+ of ADV in first 15–20 min)
- Consolidation of 1–5 days near the high of the gap day
- Entry: break of opening range high with stop at opening range low

---

## Applying Rules to maximum-pain.com/candlestick/AAPL Data

See `data_requirements.MD` for the full specification of what data fields are needed and what changes are required to the existing candlestick data source to support these rules computationally.
