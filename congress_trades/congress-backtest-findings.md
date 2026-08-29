# Congressional Trade Performance — Trailing 12 Months

**Data source:** [TattooedHead/house-stock-watcher-data](https://github.com/TattooedHead/house-stock-watcher-data) — **House of Representatives only; the Senate is not covered by this feed.** Equity trades only.
**Window:** 2025-08-28 → 2026-08-28
**Scripts:** `congress_backtest.py` · `congress_backtest_results.json`
**Methodology:** identical to `pelosi_backtest.py` — entry/exit at the next trading day's close after the disclosure date (not the transaction date), position size = disclosed amount range's midpoint, FIFO Purchase→Sale pairing per (representative, ticker, owner), open positions marked to the latest close. SPY benchmark uses the same cashflow schedule (same dates, same dollar amounts) for a fair timing-matched comparison.

---

## Headline numbers

| Metric | Value |
|---|---:|
| Trades analyzed | 1,149 (of 1,166 disclosed Purchases — 17 skipped for missing price data) |
| Members represented | 42 |
| Distinct tickers | 505 (12 failed to price — see Data Quality below) |
| Win rate | 57% |
| Total notional invested | $19,905,010 |
| Total ending value | $22,138,307 |
| Total P&L | +$2,233,297 (+11.2%) |
| **Portfolio XIRR** | **+27.9%/yr** |
| SPY, same schedule | +22.7%/yr |
| **Alpha vs. SPY** | **+5.3 pts/yr** |

Congress as a whole modestly beat a timing-matched SPY over this window — a much thinner edge than the Pelosi-specific 3-year result (+16.5 pts/yr), and it's concentrated in a handful of names/members rather than broad-based.

## Top 15 trades by return

| Representative | Ticker | Disclosed | Return |
|---|---|---|---:|
| Valerie Hoyle | MU | 2025-09-11 | +520.5% |
| Tim Moore | INTC | 2025-09-02 | +269.6% |
| Byron Donalds | LRCX | 2025-09-01 | +212.9% |
| Jared Moskowitz | DELL | 2025-10-31 | +184.2% |
| Gilbert Cisneros | SNDK | 2026-02-11 | +147.8% |
| Jared Moskowitz | PANW | 2026-03-31 | +131.8% |
| Gilbert Cisneros | CRNX | 2026-04-06 | +125.0% |
| Gilbert Cisneros | CNC | 2025-09-08 | +124.5% |
| Cleo Fields | MU | 2026-02-03 | +122.5% |
| Gilbert Cisneros | BE | 2025-12-12 | +121.9% |

*(top 10 of 15 shown; full list in the JSON)*

## Bottom 5 trades by return

| Representative | Ticker | Disclosed | Return |
|---|---|---|---:|
| Julia Letlow | ICON | 2026-01-01 | −70.0% |
| Tim Moore | GNPX | 2026-01-03 | −90.7% |
| Cleo Fields | OPEN | 2025-09-19 | −65.6% |
| Lisa McClain | FMC | 2025-10-01 | −63.6% |
| Gilbert Cisneros | AVAV | 2026-01-09 | −59.5% |

## Member leaderboard (dollar-weighted return, ≥2 trades)

| Representative | Trades | Invested | Return |
|---|---:|---:|---:|
| Tim Moore | 23 | $692,000 | +42.9% |
| Scott Franklin | 2 | $83,000 | +37.9% |
| Robert E. Latta | 5 | $47,001 | +27.2% |
| Byron Donalds | 18 | $144,000 | +24.6% |
| Jared Moskowitz | 41 | $401,500 | +19.1% |
| Cleo Fields | 40 | $2,545,500 | +17.5% |
| Valerie Hoyle | 95 | $784,500 | +16.0% |
| Josh Gottheimer | 27 | $216,000 | +13.4% |
| Nancy Pelosi | 4 | $5,250,000 | +12.1% |
| Marjorie Taylor Greene | 25 | $273,500 | +12.0% |
| Gilbert Cisneros | 381 | $3,863,003 | +9.0% |

---

## Caveats — important context before reading anything into this

- **House only.** No Senate data — a real gap if you're thinking "Congress" broadly. A separate Senate-specific source (`timothycarambat/senate-stock-watcher-data`) exists and could be added as a follow-up.
- **100% unrealized.** Nearly every trade in the Top/Bottom lists is still "held" — this is mark-to-market paper P&L over an unusually strong 12 months for AI/semiconductor names (MU, INTC, LRCX, DELL, SNDK, AMD all appear near the top), not a realized track record.
- **High trade counts ≠ stock-picking skill.** Gilbert Cisneros (381 trades!), Valerie Hoyle (95), and Cleo Fields (40) show up repeatedly with small, uniform dollar amounts ($1,001–$15,000 range) across many trades — a pattern consistent with an automated/managed brokerage account making frequent small periodic purchases, not discretionary conviction bets. Their "leaderboard" position mostly reflects "was in the market broadly during a good stretch," not information edge. Compare to Nancy Pelosi's 4 trades at $5.25M notional — very different risk/signal profile from the same feed.
- **Small-N members dominate extremes.** Scott Franklin's +37.9% comes from just 2 trades; Robert E. Latta's +27.2% from 5. These are noisy estimates, not stable "this member beats the market" claims.
- **Amount is a disclosed range, not an exact figure** — `amount_mid` is a proxy for position size, same limitation as the Pelosi backtest.
- **12 tickers failed to price** (ALEX, AZSEY, BK, CTRA, K, MMC, PSTG, SATS, SQ, THR, USOU, XMEX) — most of these (BK, CTRA, K, MMC, PSTG, SQ) are real, currently-listed tickers, so this looks like transient Yahoo bulk-download flakiness rather than genuine delisting; a retry would likely recover most of them. 17 trades (1.5%) were dropped as a result.
- **No transaction costs, slippage, or taxes.** Same as the Pelosi backtest.

**Bottom line**: over the last 12 months, mechanically following House members' disclosed trades — as a whole — modestly beat a timing-matched SPY benchmark, but the outperformance is thin, concentrated in a semiconductor/AI rally that lifted nearly everything in that sector, and the most eye-catching individual numbers come from accounts that look automated rather than conviction-driven. This is a snapshot of one favorable window for one sector, not evidence of a durable "insider edge" in congressional trading.
