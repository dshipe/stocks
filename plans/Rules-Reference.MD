# Qullamaggie Rules — Quick Numeric Reference

> All rules in order, R1 through R46, with thresholds used in the scanner.
> Full explanations: `Rules.MD` | Implementation: `scan/shared/criteria.py` | Config: `scan/config.py`
>
> **🔧 Modified rules:** R6 (prior move % and lookback window), R19 (volume contraction ratio) — see [Criteria Change Log](#criteria-change-log) below.

---

| # | Stage | Rule | Original Criteria | Current Criteria | Modified | Scanner |
|---|-------|------|-------------------|-----------------|----------|---------|
| **R1** | Universe | Price minimum | ≥ $5.00 | ≥ $5.00 | | ✅ |
| **R2** | Universe | Avg daily volume | ≥ 300,000 shares (20-day) | ≥ 300,000 shares (20-day) | | ✅ |
| **R3** | Universe | ADR% minimum | ≥ 3% | ≥ 3% | | ✅ |
| **R4** | Universe | Exchange | Not OTC / pink sheets | Not OTC / pink sheets | | — |
| **R5** | Universe | Market cap | ≥ $300M preferred | ≥ $300M preferred | | — |
| **R6** | Prior Move | Minimum move % | ≥ **30%** from a recent low | ≥ **25%** from a recent low | 🔧 2026-04-27 | ✅ |
| **R6** | Prior Move | Move lookback window | Within **40** trading days | Within **60** trading days | 🔧 2026-04-27 | ✅ |
| **R7** | Prior Move | Volume surge in move | ≥ 1 day with vol ≥ 2× avg | ≥ 1 day with vol ≥ 2× avg | | ✅ |
| **R8** | Prior Move | Catalyst | Clear identifiable catalyst | Clear identifiable catalyst | | — |
| **R9** | Prior Move | 52-week high proximity | Within 10–20% of 52w high | Within 20% of 52w high | | ✅ |
| **R10** | Prior Move | Relative strength | ≥ 50% more than S&P 500 | ≥ 50% more than S&P 500 | | — |
| **R11** | Base | Duration | 5–40 trading days | 5–40 trading days | | ✅ |
| **R12** | Base | Depth | ≤ **15%** (ideally ≤ 10%) | ≤ **20%** (ideally ≤ 10%) | 🔧 2026-04-27 | ✅ |
| **R13** | Base | Single candle body | ≤ 10% body range | ≤ 10% body range | | — |
| **R14** | Base | 50-day MA | Price above 50d MA | Price above 50d MA | | ✅ |
| **R15** | Base | 20-day MA | Price above 20d MA | Price above 20d MA | | ✅ |
| **R16** | Base | MA alignment | 10d MA above 20d MA | 10d MA above 20d MA | | ✅ |
| **R17** | Base | VCP legs | ≥ 2 contraction legs | ≥ 2 contraction legs | | — |
| **R18** | Base | Earnings in base | No earnings in base | No earnings in base | | — |
| **R19** | Volume | Base vol contraction | Base avg vol ≤ **60%** of 50d avg | Base avg vol ≤ **75%** of 50d avg | 🔧 2026-04-27 | ✅ |
| **R20** | Volume | Consecutive low-vol days | ≥ 3 consecutive days | ≥ 3 consecutive days | | ✅ |
| **R21** | Volume | Distribution days | No high-vol down days (last 5) | No high-vol down days (last 5) | | — |
| **R22** | Volume | Volume profile | Declining as base narrows | Declining as base narrows | | — |
| **R23** | Breakout | Price trigger | Above consolidation high (pivot) | Above consolidation high (pivot) | | ✅ |
| **R24** | Breakout | Breakout volume | ≥ 150% of 20-day avg | ≥ 150% of 20-day avg | | ✅ |
| **R25** | Breakout | Candle strength | Closes within 5% of candle high | Closes within 5% of candle high | | ✅ |
| **R26** | Breakout | Earnings proximity | No earnings within 3 days | No earnings within 3 days | | — |
| **R27** | Breakout | Market trend | S&P 500 / NASDAQ uptrend | S&P 500 / NASDAQ uptrend | | ✅ |
| **R28** | Breakout | Intraday entry | Break of Opening Range High | Break of Opening Range High | | — |
| **R29** | Risk | Stop placement | Base low − 0.5% buffer | Base low − 0.5% buffer | | ✅ |
| **R30** | Risk | Stop distance | ≤ 1× ATR-14 | ≤ 1× ATR-14 | | — |
| **R31** | Risk | Max risk per trade | 0.5% of account | 0.5% of account | | — |
| **R32** | Risk | Position size | Dollar Risk ÷ (Entry − Stop) | Dollar Risk ÷ (Entry − Stop) | | — |
| **R33** | Risk | Max position | 20% of account per stock | 20% of account per stock | | — |
| **R34** | Risk | Volume impact | ≤ 1% of stock's ADV | ≤ 1% of stock's ADV | | — |
| **R35** | Risk | Min R/R ratio | ≥ 2:1 | ≥ 2:1 | | ✅ |
| **R36** | Exit | First partial sale | Sell 1/3–1/2 at 2R | Sell 1/3–1/2 at 2R | | — |
| **R37** | Exit | Stop move | Move to breakeven after 2R | Move to breakeven after 2R | | — |
| **R38** | Exit | Second partial sale | Sell 1/4 at 3R | Sell 1/4 at 3R | | — |
| **R39** | Exit | Trail stop | 10-day MA close | 10-day MA close | | — |
| **R40** | Exit | Alt trail | 20-day MA (extended trends) | 20-day MA (extended trends) | | — |
| **R41** | Exit | Failed breakout | Exit on close below pivot | Exit on close below pivot | | ✅ |
| **R42** | Exit | Earnings hold | Exit unless ≥ 30% cushion | Exit unless ≥ 30% cushion | | — |
| **R43** | Market | S&P trend | Above 50d and 200d MA | Above 50d and 200d MA | | ✅ |
| **R44** | Market | Distribution | No distribution phase | No distribution phase | | — |
| **R45** | Market | VIX | VIX < 30 | VIX < 30 | | — |
| **R46** | Market | Sector | Sector in uptrend | Sector in uptrend | | — |

---

## Scanner Coverage

**✅ Implemented** — rule is checked in `scan/shared/criteria.py`
**—** — not yet automated (manual check or future enhancement)

Of the 46 rules, **19 are automated** in the current scanner (R6a, R6b, R6c added 2026-04-29).

---

## Thresholds (Current Config)

Modify in `scan/config.py` or override via `scan/.env`:

| Setting | Original | Current | Rule | Modified |
|---------|----------|---------|------|----------|
| `MIN_PRICE` | $5.00 | $5.00 | R1 | |
| `MIN_AVG_VOLUME` | 300,000 | 300,000 | R2 | |
| `MIN_ADR_PCT` | 3.0% | 3.0% | R3 | |
| `MIN_MOMENTUM_1M_PCT` | — | **5%** | R6a | 🔧 2026-04-29 |
| `MIN_MOMENTUM_3M_PCT` | — | **15%** | R6b | 🔧 2026-04-29 |
| `MIN_MOMENTUM_6M_PCT` | — | **30%** | R6c | 🔧 2026-04-29 |
| `MIN_PRIOR_MOVE_PCT` | **30%** | **25%** | R6 (2b bonus) | 🔧 2026-04-27 |
| `MAX_PRIOR_MOVE_DAYS` | **40** | **60** | R6 | 🔧 2026-04-27 |
| `MIN_VOL_SURGE_RATIO` | 2.0× | 2.0× | R7 | |
| `MAX_FROM_52W_HIGH` | 20% | 20% | R9 | |
| `MIN_BASE_DAYS` | 5 | 5 | R11 | |
| `MAX_BASE_DAYS` | 40 | 40 | R11 | |
| `MAX_BASE_DEPTH_PCT` | **15%** | **20%** | R12 | 🔧 2026-04-27 |
| `MAX_BASE_VOL_RATIO` | **60%** | **75%** | R19 | 🔧 2026-04-27 |
| `MIN_CONSEC_LOW_VOL_DAYS` | 3 | 3 | R20 | |
| `MAX_DIST_FROM_PIVOT_PCT` | 5% | **8%** | Watchlist trigger | 🔧 2026-04-29 |
| `MIN_BREAKOUT_VOL_RATIO` | 1.5× | 1.5× | R24 | |
| `MAX_CLOSE_FROM_HIGH_PCT` | 5% | 5% | R25 | |

---

## Stage Flow

```
R1–R5    Universe Filter         → price ≥ $5, vol ≥ 300k, ADR ≥ 3%
    ↓
R6a–R6c  Momentum Trend (Stage 2)→ up ≥10%/20%/30% over 1M/3M/6M — NEVER AGES OUT (🔧 2026-04-29)
    ↓
R6–R10   Prior Move (Stage 2b)   → ≥25% in 60 days w/ vol surge — bonus grading only (🔧 2026-04-29)
    ↓
R11–R18  Base Quality            → tight consolidation 5–40 days, ≤20% depth (🔧 was 15%)
    ↓
R19–R22  Volume Contraction      → bonus grading only, not a gate (🔧 demoted 2026-04-29)
    ↓
         Watchlist Trigger       → within 8% of pivot → add to watchlist (🔧 was 5%)
    ↓
R23–R28  Breakout             → price > pivot + volume ≥ 1.5× avg + strong candle
    ↓
R29–R35  Position Sizing      → stop below base low, 0.5% account risk, ≥2:1 R/R
    ↓
R36–R42  Exit Management      → scale out at 2R/3R, trail 10d MA, exit failed breakouts
    ↓
R43–R46  Market Filter        → S&P above MAs, low VIX, sector uptrend
```

---

## Criteria Change Log

| Date | Parameter | Original Value | New Value | Reason |
|------|-----------|----------------|-----------|--------|
| 2026-04-27 | `MIN_PRIOR_MOVE_PCT` | 30% | 25% | Analysis of 516 tickers showed 25 additional stocks would qualify; prior move still confirmed with volume surge (R7) |
| 2026-04-27 | `MAX_PRIOR_MOVE_DAYS` | 40 days | 60 days | Analysis showed 29 additional stocks would qualify; valid setups often form 10–12 weeks after the explosive move |
| 2026-04-27 | `MAX_BASE_VOL_RATIO` | 60% | 75% | After prior move changes, Stage 4 became the binding constraint; loosened to capture setups with adequate but not extreme volume contraction |
| 2026-04-27 | `MAX_BASE_DEPTH_PCT` | 15% | 20% | 21 stocks failing Stage 3 due to depth > 15%; energy/commodity stocks form wider bases by nature. Analysis showed +12 additional stocks at 20% threshold |
| 2026-04-29 | `MAX_DIST_FROM_PIVOT_PCT` | 5% | **8%** | SNDK was 6.3% below its pivot after a brief pullback from all-time high — a valid pre-breakout setup excluded by the old 5% trigger |
| 2026-04-29 | `find_prior_explosive_move` logic | uncapped end_idx | capped at `len-1-MIN_BASE_DAYS` | WDC peaked 4 days ago; uncapped loop set peak_date=today leaving <5 days for base detection. Both SNDK and WDC were silently dropped at Stage 3 |
| 2026-04-29 | Stage 2 gate | Prior explosive move (ages out after 60d) | **Multi-timeframe momentum** (1M/3M/6M — never ages out) | CVNA fell off watchlist when its initial move aged past the 60d window despite being a market leader. Prior move demoted to Stage 2b bonus grading. |
| 2026-04-29 | `MIN_MOMENTUM_1M_PCT` | — (new) | **10%** | New Stage 2 gate parameter |
| 2026-04-29 | `MIN_MOMENTUM_3M_PCT` | — (new) | **20%** | New Stage 2 gate parameter |
| 2026-04-29 | `MIN_MOMENTUM_6M_PCT` | — (new) | **30%** | New Stage 2 gate parameter |
| 2026-04-29 | `MIN_MOMENTUM_1M_PCT` | 10% | **5%** | Diagnostic: 112/174 stocks failing 1M gate alone; consolidating stocks have naturally flat 1M |
| 2026-04-29 | `MIN_MOMENTUM_3M_PCT` | 20% | **15%** | Recovers ~20 additional stocks with strong 6M trends but moderate 3M |
| 2026-04-29 | `MAX_BASE_VOL_RATIO` | 0.75 | **0.85** | 13 stocks (KLAC, MRVL, BKR, JBL, FIX etc.) failing Stage 4 with ratios 0.76–0.85 |
| 2026-04-29 | Stage 4 gate | Hard gate (drops stock) | **Bonus grading only** | 17/20 Stage 3 stocks dropped at vol contraction; consistent with Stage 2b philosophy — use quality signals for ranking, not exclusion |

---

*Source: `qullamaggie/breakouts/Rules.MD`*
*Last updated: 2026-04-29*
