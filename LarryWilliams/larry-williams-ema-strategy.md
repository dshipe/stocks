# Larry Williams EMA Strategy — Analysis & Findings

## Quick Verdict

| Question | Answer |
|---|---|
| **Asset class** | **Stocks** (equities) — not options |
| **Trading style** | **Swing trading** (primary), adaptable to day trading |
| **Typical hold period** | 2–10 days on daily charts; same-day on intraday charts |
| **Timeframe target** | Daily (canonical); 1h/4h for shorter-term swing |

---

## Strategy Overview

Larry Williams' "Setup 9" family is a **momentum/pullback system** built around the **9-period Exponential Moving Average (EMA)**. The core idea: identify the direction of short-term momentum using the 9-EMA, then time entries at low-risk points (reversals or pullbacks) with well-defined stops.

---

## Is This Stock or Options Trading?

**It is a stock trading strategy.**

- All entry/exit logic is price-based (candlestick highs/lows, EMA crossovers).
- No mention of Greeks, implied volatility, expiration, or premium — the hallmarks of an options-specific system.
- Stop-loss placement is defined by the trigger candle's low, which works cleanly for equity shares but would require translation to options (e.g., a stop on delta-equivalent notional value).
- Larry Williams' public work (his books *Long-Term Secrets to Short-Term Trading*, *How I Made One Million Dollars*) is squarely focused on futures and equities.

**Could it be adapted for options?** Yes — traders sometimes buy short-dated calls/puts on the Setup 9 signal to gain leverage. But that is an adaptation, not the strategy as described.

---

## Is This Day Trading?

**No — it is primarily swing trading on the daily chart.**

- The 9-EMA on a daily chart captures momentum shifts that resolve over **2–10 days**, not intraday.
- The stop-loss is placed at a prior candle's low — meaningful on daily bars, often too wide for true day trading.
- The 50-period MA filter is explicitly a broader trend guard, which only makes sense when positions are held long enough for the macro trend to matter.
- Williams himself teaches these setups as **short-term swing trades**, not scalps.

**Day trading adaptation:** The setups can be applied to 1h or 15m charts, converting them into day trades, but that is an off-label use with reduced backtested reliability.

---

## Setup-by-Setup Breakdown

### Setup 9.1 — EMA Trend Reversal

**Concept:** Catch the moment the 9-EMA changes direction — a sign that short-term momentum has flipped.

| Step | Detail |
|---|---|
| **Signal** | 9-EMA turns upward (long) or downward (short) |
| **Trigger entry** | Price closes **above the high** of the candle where EMA turned |
| **Stop-loss** | Below the **low** of that same trigger candle |
| **Risk profile** | Defined-risk; tight stop relative to the swing |

**Assessment:** High-frequency signal — generates many trades. Works best in trending markets; will whipsaw in choppy, range-bound conditions. The stop placement is logical but can be violated quickly in volatile names.

---

### Setup 9.2 — Pullback (Buy the Dip in Trend)

**Concept:** Enter an already-established uptrend after a brief pullback, rather than chasing the breakout.

| Step | Detail |
|---|---|
| **Prerequisite** | 9-EMA is trending upward |
| **Dip identification** | A candle closes below the prior candle's low |
| **Mark** | Note the high of that dip candle |
| **Entry trigger** | Price crosses back above that marked high |
| **Stop-loss** | At the lowest point of the dip candle |

**Assessment:** Better risk/reward than 9.1 because you're entering after confirmation of a resumption, not at the first flip. The stop is still defined by a recent candle structure. Drawback: you can miss the move if the price reverses sharply after the dip.

---

### Dynamic 3-EMA Strategy

**Concept:** Use dual 3-period EMAs offset by a few bars to identify short-duration momentum bursts.

- Faster-reacting than the 9-EMA setups.
- More signals, more noise — best reserved for high-volume, liquid stocks where the signal-to-noise ratio is higher.
- Requires tight discipline on stops given the speed of false signals.

**Assessment:** Aggressive, higher-frequency variation. Day-trading friendly on intraday charts but difficult to execute manually without alerts.

---

### 10-EMA Visual Shift (Crossover)

**Concept:** Plot the 10-EMA shifted a few bars to the right; a buy signal occurs when price crosses above the lagging EMA after a downleg.

- A visual smoothing technique rather than a fundamentally new signal.
- Reduces false entries by requiring price to stay above the "shifted" average longer.

**Assessment:** More of a confirmation tool than a standalone system.

---

## Macro Filter: 50-Period MA

All setups are significantly improved by adding a **50-period moving average filter**:

- **Long trades only** when price is above the 50 MA.
- **Short trades only** when price is below the 50 MA.

This ensures you are trading with the intermediate trend, not fighting it. Published backtests (e.g., Livio Alves' Setup 9.1 analysis) show materially better win rates when this filter is applied.

---

## Backtesting Notes

From available published backtests (primarily on U.S. equities, daily timeframe):

| Metric | Typical Range |
|---|---|
| Win rate (9.1 no filter) | ~45–52% |
| Win rate (9.1 + 50 MA filter) | ~54–60% |
| Avg. R:R (reward-to-risk) | 1.5:1 – 2.5:1 |
| Avg. hold time | 3–7 days |
| Drawdown sensitivity | High in choppy/sideways markets |

> **Caveat:** Backtests are highly sensitive to the universe of stocks used, the period tested, and how "slippage" is modeled. These are illustrative ranges, not guarantees.

---

## Strengths

- **Defined risk** on every trade — stop is always anchored to a candle structure.
- **Rule-based** — removes discretion, making it systematic and backtestable.
- **Flexible timeframe** — the 9-EMA logic translates across daily, 4h, 1h without changing rules.
- **Momentum-aligned** — entering on EMA direction change keeps you on the right side of short-term momentum.

---

## Weaknesses & Risks

- **Whipsaw in range-bound markets** — the 9-EMA will flip repeatedly with no follow-through; the 50 MA filter helps but does not eliminate this.
- **Execution speed required** — the trigger is a close above a specific candle high; missing the close means chasing the next day.
- **No volatility adjustment** — stop distance is fixed by candle structure, not by ATR or implied vol. Wide-ranging stocks will stop you out frequently.
- **No volume confirmation** — the system is price-only; adding a volume or relative strength filter would improve signal quality.

---

## Recommended Usage

1. **Screen** for stocks above their 50-period MA (macro filter).
2. **Apply Setup 9.2** for entries — better R:R than 9.1 since you're buying after confirmed pullback resumption.
3. **Use daily charts** as the primary timeframe; confirm on weekly for broader trend direction.
4. **Size positions** so that the stop-loss distance equals 1–2% of portfolio (risk-per-trade discipline).
5. **Do not use on options without adjusting** — the stop placement and hold duration need translation to options strategy (e.g., debit spreads with defined max loss matching the stock stop level).

---

## References

- Setup 9.1 Backtest: [Medium — Livio Alves](https://livioalves.medium.com/backtest-setup-9-1-larry-williams-896220f769e2)
- Setup 9.1 TradingView Script: [hh3LpDza](https://www.tradingview.com/script/hh3LpDza-Setup-9-1-Larry-Williams/)
- Setup 9.1 with MA Filter: [cdmqtoOf](https://in.tradingview.com/script/cdmqtoOf/)
- Setup 9.2 TradingView Script: [PvlNX5yL](https://www.tradingview.com/script/PvlNX5yL/)
- 3-Period EMA Strategy: [QhIS0dEW](https://www.tradingview.com/script/QhIS0dEW-Larry-Williams-3-Period-EMAs-strategy/)
- Community scripts: [TradingView Larry Williams tag](https://id.tradingview.com/scripts/larrywiliams/)
