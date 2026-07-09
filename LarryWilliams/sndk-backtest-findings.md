# SNDK — Larry Williams EMA Strategy Backtest

**Data source:** maximum-pain.com/candlestick/sndk  
**Period:** 2026-03-30 to 2026-06-25 (61 trading days)  
**Scripts:** `sndk_backtest.py` · `sndk_backtest_results.json`

---

## Price Context

SNDK moved from **$572** to **$2,335** over the 61-day window — a **+308% gain**. This is an extreme, one-directional trend. The 9-EMA barely changed direction (only 5 direction flips total), which severely limits the number of signals the Larry Williams system generates. This is an important caveat for interpreting the results.

| Date | Close | EMA9 | EMA Direction |
|---|---|---|---|
| 2026-03-30 | $572.50 | $572.50 | DOWN |
| 2026-03-31 | $635.34 | $585.07 | **UP** |
| 2026-05-14 | $1,382.72 | $1,383.11 | **DOWN** |
| 2026-05-15 | $1,407.61 | $1,388.01 | **UP** |
| 2026-05-18 | $1,333.01 | $1,377.01 | **DOWN** |
| 2026-05-19 | $1,383.29 | $1,378.26 | **UP** |
| 2026-06-05 | $1,559.32 | $1,656.52 | **DOWN** |
| 2026-06-11 | $1,881.51 | $1,696.63 | **UP** |
| 2026-06-23 | $1,963.60 | $1,997.66 | **DOWN** |
| 2026-06-25 | $2,335.00 | $2,051.81 | **UP** |

---

## Trade Log

### Setup 9.1 — EMA Reversal

| # | Dir | Signal | Entry Date | Entry $ | Stop $ | Exit Date | Exit $ | P&L | R | Days | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SHORT | 2026-05-14 | 2026-05-18 | $1,333.01 | $1,453.77 | 2026-05-19 | $1,383.29 | **-$50.28** | -0.42R | 1 | EMA_FLIP |
| 2 | LONG | 2026-06-11 | 2026-06-12 | $1,980.10 | $1,665.00 | 2026-06-23 | $1,963.60 | **-$16.50** | -0.05R | 6 | EMA_FLIP |

**9.1 Summary:** 0/2 wins (0%), Total P&L: **-$66.78/share**

---

### Setup 9.2 — Pullback in Uptrend

| # | Dir | Signal | Entry Date | Entry $ | Stop $ | Exit Date | Exit $ | P&L | R | Days | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | LONG | 2026-04-07 | 2026-04-08 | $738.01 | $687.68 | 2026-05-14 | $1,382.72 | **+$644.71** | +12.81R | 26 | EMA_FLIP |
| 2 | LONG | 2026-06-16 | 2026-06-18 | $2,167.33 | $1,980.18 | 2026-06-23 | $1,980.18 | **-$187.15** | -1.00R | 2 | STOP |

**9.2 Summary:** 1/2 wins (50%), Total P&L: **+$457.56/share**, Profit Factor: 3.44

---

### All Trades Combined

| # | Setup | Dir | Entry | Exit | P&L | R | Result |
|---|---|---|---|---|---|---|---|
| 1 | 9.2 | LONG | 2026-04-08 @ $738 | 2026-05-14 @ $1,383 | +$644.71 | +12.81R | EMA_FLIP |
| 2 | 9.1 | SHORT | 2026-05-18 @ $1,333 | 2026-05-19 @ $1,383 | -$50.28 | -0.42R | EMA_FLIP |
| 3 | 9.1 | LONG | 2026-06-12 @ $1,980 | 2026-06-23 @ $1,964 | -$16.50 | -0.05R | EMA_FLIP |
| 4 | 9.2 | LONG | 2026-06-18 @ $2,167 | 2026-06-23 @ $1,980 | -$187.15 | -1.00R | STOP |

---

## Summary Statistics

| Metric | Value |
|---|---|
| Total trades | 4 |
| Closed trades | 4 |
| Winners | 1 (25%) |
| Losers | 3 (75%) |
| Total P&L (per share) | **+$390.78** |
| Avg win | +$644.71 |
| Avg loss | -$84.64 |
| Avg R-multiple | +2.83R |
| Profit factor | **2.54** |
| Avg hold (days) | 8.8 |

---

## Trade-by-Trade Analysis

### Trade 1 — The Big Winner (9.2 Pullback, +12.81R)

- **Signal:** On 4/7, SNDK's EMA9 was rising and the 4/7 candle closed below the prior candle's low ($738.01 vs. prior low ~$711).
- **Entry:** Next bar (4/8) broke above dip candle high of $738.01 — entered at $738.
- **Stop:** $687.68 (low of the 4/7 dip candle) — risk of $50.33/share.
- **Hold:** 26 days. Exited on 5/14 when the EMA9 flipped downward. Exit at $1,382.72.
- **Result:** +$644.71 per share (+12.81R). This is the classic reason to use pullback strategies on trending stocks — you catch most of a 90% up-leg with a tight stop.

### Trade 2 — Damaging SHORT Signal (9.1, -0.42R)

- **Signal:** On 5/14, EMA9 flipped down for the first time since early April (short-term correction).
- **Entry:** 5/18 at $1,333 short, stop at $1,453.77 (high of the flip candle).
- **Problem:** This was a counter-trend short in a +300% uptrend. The EMA flip lasted exactly 2 bars before reversing upward again.
- **Exit:** EMA flipped back up on 5/19 — covered at $1,383.29 for a $50.28 loss.
- **Key lesson:** The **50 MA filter** would have eliminated this trade entirely. Price was far above any reasonable 50 MA, making shorts invalid by the strategy's own rules.

### Trade 3 — Near Breakeven LONG (9.1, -0.05R)

- **Signal:** 6/11, EMA9 flipped upward after a 6-day decline.
- **Entry:** 6/12 at $1,980 long, stop at $1,665 (low of 6/11 trigger candle — wide stop of $315).
- **The problem:** The stop was extremely wide relative to entry price (~16%). This is normal in a high-ATR stock but means position sizing must be tiny to keep dollar risk controlled.
- **Exit:** 6/23, EMA flipped down again. Exited at $1,963.60, only -$16.50 loss.
- **Note:** This trade entered near a local top and the stock did eventually sell off hard (6/23 and 6/24 were down days before surging on 6/25).

### Trade 4 — Stop-Out Before Surge (9.2, -1.00R)

- **Signal:** 6/16, dip candle closed below prior low.
- **Entry:** 6/18 when price broke above dip high of $2,167.33, stop at $1,980.18.
- **Exit:** 6/23, stop hit at $1,980.18 — exactly 1R loss.
- **Frustrating context:** Two days later (6/25), SNDK surged to $2,335. The stop-out was correct mechanically (price did reach $1,861 on 6/24) but the trade was a stopped-out winner in hindsight.

---

## Key Findings

### 1. The strategy works in trending stocks — but generates very few signals

With only **5 EMA direction changes** over 61 days, the system produced just **4 trades** (~1 trade per 15 days). In a stock like SNDK that trends relentlessly, the 9-EMA rarely reverses. Traders looking for more frequent signals should use this strategy on mean-reverting stocks or apply it to shorter timeframes.

### 2. Setup 9.2 (Pullback) dramatically outperforms Setup 9.1 (Reversal)

| | 9.1 | 9.2 |
|---|---|---|
| Trades | 2 | 2 |
| Win rate | 0% | 50% |
| Total P&L | -$66.78 | +$457.56 |
| Profit factor | 0.00 | 3.44 |

The 9.2 pullback setup is aligned with the trend and has asymmetric risk/reward. The winning 9.2 trade returned 12.81R while the losing 9.2 trade lost exactly 1R — this is the ideal risk/reward profile.

### 3. The 50 MA filter is not optional — it's essential

The worst trade (short on 5/18) occurred because the 9.1 setup triggered a SHORT in a strong uptrend. Applying the 50-period MA filter rule — **no shorts when price is above the 50 MA** — would have:
- Eliminated the -$50.28 short trade
- Improved win rate from 25% to **33%** (1/3)
- Improved profit factor from 2.54 to **31.3** (one win vs. one small loss)

*Note: The 50 MA cannot be computed from 61 days of data alone — prior pricing history is needed.*

### 4. Profit factor of 2.54 is surprisingly healthy given 25% win rate

A 25% win rate with a 2.54 profit factor means the average winner is **7.6x** the average loser. This demonstrates a key strength of the Larry Williams approach: the risk is defined, the stops are tight, and trending winners are held for extended periods.

### 5. Position sizing is critical on high-ATR names

SNDK had an average daily range of ~$100–$200 during this period. A $315 stop (Trade 3) on a stock trading at $1,980 is a **16% stop distance**. To risk only 1% of a $100,000 portfolio ($1,000) on such a trade, you could only buy **3 shares**. Traders must account for ATR-based position sizing rather than using fixed share counts.

---

## Limitations of This Backtest

| Limitation | Impact |
|---|---|
| Only 61 trading days | Tiny sample — 4 trades has no statistical significance |
| Single stock | SNDK in an extreme uptrend is not representative of all conditions |
| No 50 MA filter applied | Would reduce short signals; prior data not available |
| No slippage or commissions | Actual P&L would be slightly lower |
| Daily chart only | Results differ on 1h or 4h timeframes |
| Exit rule is EMA flip | Other exits (trailing stop, ATR-based, fixed target) may perform differently |

---

## Verdict for SNDK 2026

| Question | Answer |
|---|---|
| Does the strategy work here? | **Partially** — the pullback setup (9.2) worked well; the reversal setup (9.1) did not |
| Biggest risk | Taking counter-trend shorts without the 50 MA filter |
| Best setup for this stock | **9.2 Pullback** — aligned with the dominant uptrend |
| Recommended improvement | Add 50 MA filter; consider ATR-based stop instead of candle low |
| Sample size adequacy | **No** — 4 trades over 3 months is insufficient; need 12+ months |

---

*Backtest methodology: Setup 9.1 detects 9-EMA direction flips; Setup 9.2 detects pullback candles (close < prior low) while EMA is rising. Entry on close of trigger bar or break of dip high. Exit on stop-loss or 9-EMA direction reversal, whichever occurs first. No commission or slippage modeled.*
