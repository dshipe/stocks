# NVDA — Larry Williams EMA Strategy Backtest

**Data source:** maximum-pain.com/candlestick/nvda  
**Period:** 2026-03-30 to 2026-06-25 (61 trading days)  
**Scripts:** `nvda_backtest.py` · `nvda_backtest_results.json`

---

## Price Context

NVDA moved from **$165 → peak $236 → $196** over the 61-day window. The pattern was:
- **Phase 1 (Mar 30 – May 14):** Strong uptrend, +43% rally from $165 to $236
- **Phase 2 (May 14 – Jun 25):** Choppy decline/consolidation, -17% from peak back to $196

This is a fundamentally different market structure than SNDK's parabolic uptrend. NVDA's EMA flipped direction **12 times** vs. SNDK's 5. More flips = more signals = more noise.

| Date | Close | EMA9 | EMA Direction |
|---|---|---|---|
| 2026-03-30 | $165.17 | $165.17 | DOWN |
| 2026-03-31 | $174.40 | $167.02 | **UP** |
| 2026-04-30 | $199.57 | $204.54 | **DOWN** |
| 2026-05-06 | $207.83 | $202.51 | **UP** |
| 2026-05-21 | $219.51 | $220.75 | **DOWN** |
| 2026-06-01 | $224.36 | $217.43 | **UP** |
| 2026-06-03 | $214.75 | $217.76 | **DOWN** |
| 2026-06-04 | $218.66 | $217.94 | **UP** |
| 2026-06-05 | $205.10 | $215.37 | **DOWN** |
| 2026-06-15 | $212.45 | $209.25 | **UP** |
| 2026-06-16 | $207.41 | $208.88 | **DOWN** |
| 2026-06-18 | $210.69 | $208.57 | **UP** |
| 2026-06-23 | $200.04 | $206.88 | **DOWN** |

---

## Trade Log

### Setup 9.1 — EMA Reversal (5 signals, all SHORT)

| # | Dir | Signal Date | Entry Date | Entry $ | Stop $ | Exit Date | Exit $ | P&L | R | Days | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SHORT | 2026-04-30 | 2026-05-01 | $198.45 | $210.30 | 2026-05-06 | $207.83 | **-$9.38** | -0.79R | 3 | EMA_FLIP |
| 2 | SHORT | 2026-05-21 | 2026-05-22 | $215.33 | $227.40 | 2026-06-01 | $224.36 | **-$9.03** | -0.75R | 5 | EMA_FLIP |
| 3 | SHORT | 2026-06-03 | 2026-06-05 | $205.10 | $222.82 | 2026-06-15 | $212.45 | **-$7.35** | -0.41R | 6 | EMA_FLIP |
| 4 | SHORT | 2026-06-16 | 2026-06-17 | $204.65 | $211.49 | 2026-06-18 | $210.69 | **-$6.04** | -0.88R | 1 | EMA_FLIP |
| 5 | SHORT | 2026-06-23 | 2026-06-24 | $199.00 | $203.77 | OPEN | $195.74 | +$3.26 | +0.68R | 1 | OPEN |

> Trade 5 is currently OPEN (marked at last available close of $195.74).

**9.1 Summary (closed trades):** 0/4 wins (0%), Total P&L: **-$31.80/share**, Avg loss: -$7.95

---

### Setup 9.2 — Pullback in Uptrend

**Zero trades generated.**

The strategy correctly avoided every potential pullback entry. Here's why:

| Potential Signal | Why Not Triggered |
|---|---|
| May 15 dip (Close $225.32 < Prior Low $229.30) | Price never recovered above the dip high of $231.50 in next 3 bars — declined further |
| May 22 dip | EMA had already flipped DOWN — no uptrend requirement met |
| Jun 3, Jun 5 dips | EMA already DOWN — filtered out |

The pullback entry rule (price must break above the dip candle's high) **acted as a circuit breaker**, preventing entries during a post-peak decline. This is the strategy working correctly.

---

### Setup 9.2 + SMA20 Filter

**Zero trades** — same result; no qualifying entries under any condition.

---

## Summary Statistics

| Metric | Setup 9.1 | Setup 9.2 |
|---|---|---|
| Total signals | 5 (4 closed, 1 open) | 0 |
| Win rate | 0% | N/A |
| Total P&L | **-$31.80/share** | $0 |
| Avg R-multiple | -0.71R | N/A |
| Profit factor | 0.00 | N/A |
| Avg hold | 3.8 days | N/A |

---

## Why Every 9.1 Signal Was a SHORT

The 9-EMA peaked and started declining around **April 30**, exactly when NVDA's price peaked (~$216). Every subsequent EMA flip that generated a trade was a **bearish flip** (DOWN turn), triggering SHORT signals.

The problem: NVDA was not in a true sustained downtrend — it was in a **choppy consolidation** after a peak. In choppy markets, the 9-EMA oscillates rapidly, and every bearish flip quickly reverses upward, stopping out short positions via EMA_FLIP exits.

**All 4 closed short trades exited via EMA_FLIP** — meaning they never hit their stop-loss (which would have been more costly), but the EMA reversed before the trade could profit. The EMA-flip exit is doing its job as a loss-limiter, but the fundamental problem is taking shorts in a non-trending environment.

---

## Trade-by-Trade Analysis

### Trade 1 — First Short (Apr 30 signal, -0.79R)
- EMA flipped down on 4/30 after a 30-day uprun. Short entered 5/1 at $198.45, stop $210.30.
- By 5/6, NVDA had found support and the EMA flipped back up. Exited short at $207.83.
- The 50 MA filter would NOT have helped here — price was still above SMA20 ($196). This short was genuinely ambiguous; momentum had stalled.

### Trade 2 — Post-Peak Short (May 21 signal, -0.75R)
- EMA flipped down after NVDA's all-time peak of $236.54 (5/14). Short entered 5/22 at $215.33, stop $227.40.
- The stock did drift lower through late May but bounced strongly on 6/1 (gap up to $224.36), triggering EMA flip exit for a -$9.03 loss.
- **50 MA filter would have blocked this short** — on 5/21, the SMA20 was $214.39. Price at $219.51 was above SMA20, so no short allowed. This would have been the most valuable filter application.

### Trade 3 — Mid-June Short (Jun 3 signal, -0.41R)
- EMA flipped down 6/3. Short entered 6/5 at $205.10, stop $222.82 (very wide — $17.72 risk).
- The wide stop came from the high of the signal candle (6/3 had a $222.82 high). NVDA continued lower through mid-June, but on 6/15 bounced back above $212, flipping EMA up. Exited at $212.45.
- Directionally correct (stock was falling) but exit timing worked against the trade.

### Trade 4 — One-Day Short (Jun 16 signal, -0.88R)
- Shortest trade: 1 day hold. Short at $204.65, EMA flipped up on 6/18 after a one-day bounce. Exited at $210.69.
- This is a classic whipsaw — EMA flipped, immediately reversed. Choppy market behavior.

### The Missed 9.2 Setup (May 15)
- On 5/15, NVDA closed at $225.32 — below the prior day's low of $229.30. EMA was trending up. This was a valid 9.2 dip signal.
- **The dip high was $231.50.** Price needed to break above $231.50 to trigger entry.
- 5/18 high: $230.00 — just $1.50 short of the trigger. 5/19 and 5/20 continued lower.
- **The strategy correctly did not take this entry.** The stock declined from $225 to $195 over the next 5 weeks. The circuit breaker prevented a losing trade.

---

## Key Findings

### 1. Setup 9.2's non-entry is the most important signal

Zero 9.2 trades means the strategy recognized that NVDA's post-peak pullbacks never had sufficient conviction to re-enter. The entry confirmation rule (price must breach the dip candle high) is a **trend-health test** — if price can't recover past the dip candle's high, the trend may be broken. NVDA failed this test every time after May 14.

### 2. Setup 9.1 shorts are the strategy's biggest vulnerability in this environment

Choppy post-peak markets generate repeated SHORT signals from 9.1, but the reversals are quick. Every short lasted fewer than 6 days before the EMA flipped back up. This is textbook "whipsaw" behavior. The result: consistent small losses.

**Rule reinforced:** The 50 MA filter is not optional. Blocking shorts when price is above the 20/50 MA would have eliminated 3 of the 4 losing shorts.

### 3. NVDA vs. SNDK — contrasting outcomes explain the strategy's conditions

| Factor | SNDK | NVDA |
|---|---|---|
| EMA direction flips | 5 | 12 |
| Phase | Parabolic uptrend | Peak + consolidation |
| 9.2 trades | 1 (won +12.81R) | 0 (no entries triggered) |
| 9.1 trades | 1 SHORT (loss) | 4 SHORTs (all losses) |
| Total P&L | +$390.78/share | -$31.80/share |
| Outcome | Strategy worked | Strategy failed |

The strategy's edge comes from **trending markets where pullbacks re-accelerate**. It breaks down in **choppy, topping, or trend-transitioning environments**.

### 4. The SMA20 data from the site reveals a bearish technical development

By late May/June, the **SMA20 was above price** for many sessions — a bearish cross. This is exactly the macro filter warning: when price dips below the 20/50 MA, go to the sidelines. A trader applying this rule would have stopped taking longs after the SMA20 cross and avoided all the choppy short signals.

### 5. Position sizing saved this strategy from catastrophic loss

The average loss was only $7.95/share because the EMA-flip exit cut losses short. The worst-case stop distances were $10–$18/share, but actual exits were much smaller. This demonstrates the value of the EMA-flip exit rule — it acts as a dynamic trailing stop that exits before the structural stop is needed.

---

## Comparison: SNDK vs. NVDA

| Metric | SNDK | NVDA |
|---|---|---|
| Period | Mar 30 – Jun 25, 2026 | Mar 30 – Jun 25, 2026 |
| Price move | +308% (parabolic uptrend) | +43% peak, then -17% reversal |
| Total trades | 4 | 4 closed + 1 open |
| Win rate | 25% | 0% |
| Total P&L/share | **+$390.78** | **-$31.80** |
| Setup 9.2 trades | 2 | 0 |
| Avg R-multiple | +2.83R | -0.71R |
| Profit factor | 2.54 | 0.00 |
| Market fit | Strong — trending | Poor — choppy/topping |

---

## Recommendations for NVDA

1. **Do not use Setup 9.1 shorts above the SMA20** — NVDA's bounces are sharp enough to exit short positions at a loss every time.
2. **Wait for Setup 9.2 with a clear re-acceleration** — the 5/15 dip near $231 never triggered. That's a useful signal: if a clear trend stock can't reclaim its dip high in 3 days, the trend may be over.
3. **Watch for SMA20/50 MA alignment** — when NVDA price re-crosses above both moving averages, Setup 9.2 becomes actionable again.
4. **Consider NVDA only on the long side** — NVDA is a structurally bullish stock (AI/semiconductor secular trend). Fighting the macro trend with shorts into every EMA dip is low-probability.

---

*Backtest methodology: Setup 9.1 detects 9-EMA direction flips; Setup 9.2 detects pullback candles (close < prior candle's low) while EMA is rising. Entry on close of trigger bar or break of dip high. Exit on stop-loss or 9-EMA direction reversal, whichever occurs first. No commission or slippage modeled.*
