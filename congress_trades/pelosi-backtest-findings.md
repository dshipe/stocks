# Nancy Pelosi Follow-Trade Backtest

**Data source:** [TattooedHead/house-stock-watcher-data](https://github.com/TattooedHead/house-stock-watcher-data) — free, actively-scraped mirror of official House Clerk PTR filings under the STOCK Act. Equity trades only (options/other assets are filtered out at the source).
**Price data:** yfinance (split/dividend-adjusted daily closes)
**Window:** 2023-08-28 → 2026-08-28 (3 years)
**Scripts:** `pelosi_backtest.py` · `pelosi_backtest_results.json`

---

## Strategy

1. **Universe** — every Nancy Pelosi "Purchase" *disclosure* in the trailing 3 years (transaction date is not public knowledge until the disclosure lands, so disclosure date is the earliest realistic entry signal).
2. **Entry** — next trading day's close on/after the disclosure date.
3. **Size** — the disclosed amount range's midpoint (`amount_mid`), used as notional dollars for that trade. STOCK Act filings only require a range (e.g. "$1,000,001 – $5,000,000"), never an exact figure.
4. **Exit** — a later Sale disclosure for the same ticker/owner closes the position FIFO, at the next trading day's close. No matching Sale → marked to the latest available close ("held").
5. **Benchmark** — SPY bought on the *identical* cashflow schedule (same dates, same dollar amounts) rather than a single lump-sum 3 years ago. This isolates stock-picking skill from timing/sizing luck.
6. Portfolio-level return is an **XIRR** (money-weighted annualized return) over the staggered entry dates, since trades don't all start on day one and none were exited.

---

## Trade Log

| Ticker | Disclosed | Entry | Entry $ | Exit | Exit $ | Return | Status |
|---|---|---|---:|---|---:|---:|---|
| NVDA | 2024-06-26 | 2024-06-26 | 126.19 | 2026-08-28 | 217.55 | +72.4% | held |
| NVDA | 2024-07-26 | 2024-07-26 | 112.87 | 2026-08-28 | 217.55 | +92.7% | held |
| NVDA | 2024-12-20 | 2024-12-20 | 134.50 | 2026-08-28 | 217.55 | +61.8% | held |
| PANW | 2024-12-20 | 2024-12-20 | 186.78 | 2026-08-28 | 371.59 | +99.0% | held |
| AVGO | 2025-06-20 | 2025-06-20 | 248.17 | 2026-08-28 | 368.79 | +48.6% | held |
| GOOGL | 2026-01-16 | 2026-01-16 | 329.57 | 2026-08-28 | 346.59 | +5.2% | held |
| BE | 2026-07-24 | 2026-07-24 | 184.89 | 2026-08-28 | 210.77 | +14.0% | held |
| INTC | 2026-07-24 | 2026-07-24 | 92.32 | 2026-08-28 | 89.47 | −3.1% | held |
| BE | 2026-07-28 | 2026-07-28 | 166.84 | 2026-08-28 | 210.77 | +26.3% | held |

Not simulated: **DIS** and **PYPL** were sold by the Pelosis on 2025-12-30, but both were originally purchased years before the 3-year window (2014 and 2020 respectively) — a copier starting 3 years ago never held them, so those Sale disclosures are correctly excluded rather than fabricating a phantom entry. One **VSNT "Exchange"** ($15 notional) was excluded as a non-directional corporate action, not a buy/sell decision.

---

## Results

| Metric | Value |
|---|---:|
| Trades simulated | 9 |
| Win rate | 89% (8/9) |
| Total notional invested | $14,000,002 |
| Total ending value | $21,525,573 |
| Total P&L | +$7,525,571 (+53.8%) |
| **Pelosi strategy XIRR** | **+36.2%/yr** |
| SPY same-schedule XIRR | +19.7%/yr |
| **Alpha vs. SPY** | **+16.5 pts/yr** |

The strategy beat a same-schedule SPY benchmark, driven almost entirely by three NVDA lots and PANW bought in mid-to-late 2024 — right before/during the AI-stock run — plus a second AVGO leg in mid-2025. INTC is the lone loser, roughly flat/down since the July 2026 disclosure.

---

## Caveats — read before trusting this number

- **N = 9.** This is not a statistically meaningful sample. Congressional disclosure volume is low and lumpy (there's a ~13-month gap with zero Pelosi filings between mid-2023 and mid-2024 in this window). A three-year backtest of nine trades is a case study, not a robust edge estimate.
- **All 9 positions are still "held," none exited.** Every dollar of the reported gain is unrealized mark-to-market as of 2026-08-28. A single sharp drawdown in NVDA/AVGO/PANW before an actual exit would materially change — or reverse — the result. This isn't a track record of realized wins; it's a paper P&L on open positions.
- **No transaction costs, slippage, taxes, or borrowing costs** are modeled. Real execution — especially on $500K–$5M position sizes — would move markets and incur costs a backtest ignores.
- **Amount is a range, not a figure.** `amount_mid` (e.g. $3,000,000 for a "$1,000,001–$5,000,000" filing) could be off by ±$2M per trade; position sizing here is a rough proxy for conviction, not a real number.
- **Disclosure-date entry is optimistic vs. some real-world friction** — same-day/next-day execution assumes you're watching filings closely (several trackers/alerts exist for this) and can transact in size immediately; large-block execution in practice may slip over several days.
- **This is heavily AI/semiconductor-concentrated** (NVDA ×3, AVGO, PANW, INTC — 6 of 9 trades). The result mostly reflects "was long AI hardware through 2024–2026," which was a strong trade for nearly everyone, not necessarily insight specific to congressional trading. The SPY-same-schedule comparison controls for *timing* but not for *sector concentration* — a same-schedule QQQ or SOXX benchmark would be a fairer test of stock-picking skill specifically.
- **Small sample survivorship**: this window happens to catch Pelosi's (well-known, frequently reported on) large NVDA and tech positions. A different 3-year window, or a different member of Congress, would very plausibly look far less impressive — congressional-trading-tracker strategies as a category have a mixed, and disputed, academic track record (some studies find modest outperformance in Senate trades pre-2012 STOCK Act reforms, weaker/no effect since disclosure requirements tightened).
- **Data quality**: the source dataset documents its own known OCR imperfections (garbled characters in `asset_description`, occasional truncated amount ranges — see two 2024-12-20/2026-07-24 rows with a single-bound amount like `"$1,000,001"` instead of a range). Core fields used here (ticker, type, dates, amount_mid) were spot-checked but not independently verified against the source PDFs.

**Bottom line**: over this specific 3-year window, mechanically following Nancy Pelosi's disclosed equity purchases outperformed a timing-matched SPY benchmark by a wide margin — but on 9 trades, all unrealized, concentrated in one sector during its best stretch in years. Treat the +36%/yr XIRR as "what happened to look at, in this one window," not as an expected forward return.
