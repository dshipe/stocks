# Qullamaggie Breakout Setup — Index

> Master index of all files in the `stocks/qullamaggie/breakouts/` folder.
> This folder contains comprehensive documentation on the Qullamaggie-style breakout trading setup,
> including rules, chart patterns, historical examples, and technical data requirements.

---

## About This Collection

Kristjan Kullamägi (known online as "Qullamaggie") is a Swedish-based momentum trader who grew a small account into over $100 million using a disciplined breakout and momentum strategy. This documentation captures his "breakout" setup methodology for use in identifying stocks ready to make explosive moves.

**Primary Resources Researched:**
- [Qullamaggie.com](https://qullamaggie.com) — Official blog and trade recaps
- [AskLivermore Qullamaggie Guide](https://asklivermore.com/docs/qullamaggie) — Complete scanner explanation
- [ChartMill Continuation Breakout Screen](https://www.chartmill.com/documentation/stock-screener/technical-analysis-trading-strategies/467-Kristjan-Kullamagi-Continuation-Breakout-Screen) — Screener criteria
- [SharePredictions Breakout Planner](https://sharepredictions.com/tools/qullamaggie-breakout-planner/) — Position sizing tool
- [BreakoutDB](https://breakoutdb.com/) — Historical chart pattern library
- [Jack Corsellis Trading Guide](https://jackcorsellis.com/kristjan-qullamaggie-stock-trading-strategy/) — Strategy summary
- [Vinny Stone Breakout Compilation](https://vinnystone.com/breakout-setup-compilation/) — Setup examples
- [Qullamaggie Swing Laws (StudyLib)](https://studylib.net/doc/27055345/qullamaggie%E2%80%99s-laws-of-swing) — Direct interview notes

---

## File Index

### 📋 Summary.MD
**Purpose:** High-level overview of the breakout strategy for quick reference.

**Contents:**
- The 5 most repeated concepts for identifying a breakout setup
- When to set alerts and buy the breakout (detailed entry rules)
- When to take profit and sell (exit strategy with profit targets)
- Quick reference resource links

**Best for:** Understanding the strategy at a glance, decision framework during live trading

---

### 📏 Rules.MD
**Purpose:** Comprehensive, numbered rules checklist for identifying and trading breakouts.

**Contents:**
- R1–R5: Stock universe filters (price, volume, ADR)
- R6–R10: Prior move requirements
- R11–R18: Base quality criteria
- R19–R22: Volume contraction requirements
- R23–R28: Breakout entry trigger rules
- R29–R35: Risk management and position sizing formulas
- R36–R42: Profit taking and exit rules
- R43–R46: Market conditions filter
- Quick go/no-go checklist
- Pattern-specific sub-rules (HTF, Flat Base, VCP, Pennant, Episodic Pivot)

**Best for:** Systematic screening, building automated breakout scanners, pre-trade checklist

---

### 📊 examples.MD
**Purpose:** Historical examples of successful Qullamaggie-style breakouts with detailed pattern analysis.

**Contents:**
- TSLA July 2020 (cup-with-handle breakout)
- NVDA August 2020 (flat base / earnings episodic pivot)
- ANF 2023 (high-tight flag)
- SHOP October 2020 (VCP breakout)
- GRPN May 2025 (high-tight flag)
- PLTR November 2024 (episodic pivot + continuation)
- CRWD 2021 (flat base breakout)
- Generic breakout template with ASCII chart
- Reference list of 15+ classic Qullamaggie breakout stocks by year and pattern

**Best for:** Pattern recognition training, understanding what "ideal" looks like, chart study

---

### 🔷 chart_patterns.MD
**Purpose:** Detailed visual guide to each pattern type used in the Qullamaggie methodology.

**Contents:**
- Pattern 1: High-Tight Flag (HTF) — with ASCII chart
- Pattern 2: Flat Base / Rectangle — with ASCII chart
- Pattern 3: Volatility Contraction Pattern (VCP) — with ASCII chart
- Pattern 4: Pennant / Symmetrical Triangle — with ASCII chart
- Pattern 5: Cup-With-Handle (CWH) — with ASCII chart
- Pattern 6: Episodic Pivot (EP) — with ASCII chart
- Pattern comparison table
- Pattern identification decision tree

**Best for:** Visual reference when reviewing charts, learning to distinguish pattern types

---

### ⚡ episodic_pivot.MD
**Purpose:** Deep dive into the Episodic Pivot (EP) — the catalyst-driven variant of the breakout.

**Contents:**
- What is an episodic pivot and why it works
- Pre-catalyst conditions to look for
- The catalyst event requirements
- Gap day requirements and rejection signals
- Entry methods (intraday ORH, 30-min ORH, next-day continuation)
- Position sizing example
- Exit rules (short-term, partial profit, trailing)
- EP vs. standard breakout comparison table
- Famous EP examples (NFLX, NVDA, META, PLTR)
- Screening criteria for EP discovery

**Best for:** Trading earnings catalysts, understanding gap-up setups, high-volatility entry rules

---

### 📉 vcp_setup.MD
**Purpose:** Detailed guide to the Volatility Contraction Pattern (VCP) — the most precise breakout variant.

**Contents:**
- VCP structure with detailed visual anatomy
- Measurement table for contraction stages
- Psychology behind why VCP works (supply/demand explanation)
- VCP entry rules and checklist
- Stop loss placement rules
- Position sizing worked example
- Common VCP mistakes to avoid
- VCP in different timeframes (daily, weekly, 60-min)
- VCP grading system (A+ to F quality grades)
- Real stock examples (SHOP, DDOG)

**Best for:** Finding the highest-quality, lowest-risk breakout entries

---

### 💾 data_requirements.MD
**Purpose:** Technical specification for the data changes needed to implement breakout scanning at `maximum-pain.com/candlestick/AAPL`.

**Contents:**
- How much historical data is needed (1 year / 2 years / 5 years / 10 years — with justification)
- Analysis of the current `HistoricalStock` model limitations
- Change 1: Add volume to `HistoricalStock` model
- Change 2: Add computed technical indicators (MA, ATR, ADR)
- Change 3: Add prior move detection query
- Change 4: Add `IBreakoutScanService` interface
- Change 5: Add breakout alert API endpoints
- Change 6: Extend historical data retention
- Change 7: Add relative strength vs. index
- Candlestick chart UI enhancements needed
- Data source options (Schwab, Polygon, Alpha Vantage)
- Implementation priority table

**Best for:** Developers implementing the breakout scanner, understanding system requirements

---

## Quick Reference: The Breakout Setup in One Paragraph

> A Qullamaggie breakout setup requires a stock to first make an explosive move of 30%+ in under 8 weeks, driven by a clear fundamental catalyst. After this surge, the stock enters a tight consolidation (less than 10–15% range) for 1–8 weeks, during which volume dries up significantly (50%+ below average). When the stock breaks above the high of this consolidation on expanding volume (1.5–2×+ average), that is the buy trigger. Enter with a stop below the consolidation low, risk 0.5% of capital, target at least 2:1 reward-to-risk, take partial profits at 2–3× risk, and trail the remainder with the 10-day moving average.

---

## Setup Quality Grading Summary

| Grade | Description |
|-------|-------------|
| **A+** | 60%+ prior move, 4+ VCP contractions, volume near zero, strong catalyst, market uptrend |
| **A** | 40%+ prior move, 3+ contractions, good volume dry-up, bullish market |
| **B** | 30%+ prior move, 2–3 contractions, adequate volume contraction |
| **C** | Borderline setup — only trade with other confirming factors |
| **F** | Skip — choppy base, expanding volume, or poor prior move |

---

## Pattern Type Summary

| Pattern | Rarity | Expected Return | Risk |
|---------|--------|-----------------|------|
| High-Tight Flag | Rare | 20–50%+ | Moderate |
| Flat Base | Common | 15–40% | Low-Moderate |
| VCP | Moderate | 20–60%+ | Very Low (tight stop) |
| Pennant | Common | 15–30% | Moderate |
| Cup-with-Handle | Common | 20–50% | Moderate |
| Episodic Pivot | Rare (news-driven) | 20–100%+ | Moderate-High |

---

## Chart Study Tickers (For Pattern Practice)

Open these on TradingView with daily candles and study the 2020–2025 price history:

```
High-Tight Flags: ANF (2023), BKKT (2025), GRPN (2025), CELH (2023)
Flat Bases: NVDA (2020), SHOP (2020), CRWD (2021), DDOG (2021)
VCP: SHOP (Oct 2020), ENPH (2022), AXON (2023)
Episodic Pivots: PLTR (Nov 2024), NVDA (May 2023), META (Q2 2023)
Cup-with-Handle: TSLA (Jul 2020), AAPL (various), AMZN (2016–2017)
```

---

*Last updated: 2026-04-12*  
*Source: Qullamaggie.com, AskLivermore, ChartMill, BreakoutDB, Vinny Stone, Jack Corsellis*
