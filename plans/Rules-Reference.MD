# Qullamaggie Rules — Quick Numeric Reference

> All rules in order, R1 through R46, with thresholds used in the scanner.
> Full explanations: `Rules.MD` | Implementation: `scan/shared/criteria.py` | Config: `scan/config.py`

---

| # | Stage | Rule | Threshold / Action | Scanner |
|---|-------|------|--------------------|---------|
| **R1** | Universe | Price ≥ $5.00 | Filter out penny stocks | ✅ |
| **R2** | Universe | 20-day avg daily volume ≥ 300,000 shares | Institutional liquidity floor | ✅ |
| **R3** | Universe | Average Daily Range (ADR%) ≥ 3% | Enough daily movement for profit | ✅ |
| **R4** | Universe | Not OTC / pink sheets | Liquid exchange only | — |
| **R5** | Universe | Market cap ≥ $300M preferred | Institutional-quality names | — |
| **R6** | Prior Move | Price ≥ +25% from a recent low ~~(was 30%)~~ | Within 60 trading days ~~(was 40)~~ | ✅ |
| **R7** | Prior Move | ≥ 1 day with volume ≥ 2× 20-day average during the move | Confirms institutional buying | ✅ |
| **R8** | Prior Move | Clear catalyst (earnings, news, FDA, contract) | Optional — strongly preferred | — |
| **R9** | Prior Move | Stock within 10–20% of its 52-week high | Must be setting up near highs | ✅ |
| **R10** | Prior Move | Prior move ≥ 50% more than S&P 500 in same period | Market leadership confirmation | — |
| **R11** | Base | Consolidation duration: 5–40 trading days | After the high of the prior move | ✅ |
| **R12** | Base | Base depth ≤ 15% (high-to-low / high × 100) | Ideally ≤ 10% | ✅ |
| **R13** | Base | No single candle body > 10% range in the base | No massive distribution days | — |
| **R14** | Base | Price does not close below 50-day MA during base | Trend integrity | ✅ |
| **R15** | Base | Price stays above 20-day MA for most of the base | Short-term trend intact | ✅ |
| **R16** | Base | 10-day MA above 20-day MA during consolidation | Short-term bullish structure | ✅ |
| **R17** | Base | At least 2 volume-contraction legs visible (VCP) | Each leg smaller than prior | — |
| **R18** | Base | No earnings within base (unless earnings caused the prior move) | Avoids earnings surprise risk | — |
| **R19** | Volume | Base avg volume ≤ 75% of 50-day average ~~(was 60%)~~ | Sellers exhausted | ✅ |
| **R20** | Volume | ≥ 3 consecutive below-average volume days before breakout | Volume dry-up confirmed | ✅ |
| **R21** | Volume | No high-volume down days in final 5 days of base | No institutional distribution | — |
| **R22** | Volume | Volume declines as base narrows (VCP contraction visible) | Profile slopes downward | — |
| **R23** | Breakout | Price breaks above high of consolidation base (pivot) | This is the buy trigger | ✅ |
| **R24** | Breakout | Breakout volume ≥ 150% of 20-day average | Institutional demand confirmed | ✅ |
| **R25** | Breakout | Candle closes within 5% of its high | Strong close = conviction | ✅ |
| **R26** | Breakout | No earnings within 3 trading days of breakout | Avoids earnings gap risk | — |
| **R27** | Breakout | S&P 500 / NASDAQ in uptrend on breakout day | Market tailwind | ✅ |
| **R28** | Breakout | Intraday entry: break of Opening Range High (ORH) | Aggressive intraday trigger | — |
| **R29** | Risk | Stop = below consolidation low − 0.5% buffer | Hard stop placement | ✅ |
| **R30** | Risk | Stop distance ≤ 1× ATR-14 from entry | No overly wide stops | — |
| **R31** | Risk | Max risk per trade = 0.5% of account (range 0.25–1%) | Dollar risk rule | — |
| **R32** | Risk | Share size = Dollar Risk ÷ (Entry − Stop) | Standard sizing formula | — |
| **R33** | Risk | Max overnight position = 20% of account per stock | Concentration limit | — |
| **R34** | Risk | Do not buy > 1% of stock's average daily volume | Prevents slippage | — |
| **R35** | Risk | Minimum R/R ≥ 2:1 before entry | (Target − Entry) / (Entry − Stop) | ✅ |
| **R36** | Exit | At 2R profit: sell 1/3–1/2 of position | Lock in partial gain | — |
| **R37** | Exit | After first partial sale: move stop to breakeven | Protect remaining position | — |
| **R38** | Exit | At 3R profit: sell another 1/4 | Scale out further | — |
| **R39** | Exit | Trail remainder with 10-day MA — exit on close below | Primary trailing stop | — |
| **R40** | Exit | Alternative: trail with 20-day MA for extended moves | Larger trend trail | — |
| **R41** | Exit | Exit full position if stock closes back below pivot | Failed breakout rule | ✅ |
| **R42** | Exit | Do not hold through earnings without ≥ 30% cushion | Earnings event risk | — |
| **R43** | Market | S&P 500 above its 50-day and 200-day MA | Broad market uptrend | ✅ |
| **R44** | Market | No confirmed distribution phase in broad market | No overhead selling | — |
| **R45** | Market | VIX < 30 preferred | Low fear environment | — |
| **R46** | Market | Stock's sector is in an uptrend | Sector tailwind | — |

---

## Scanner Coverage

**✅ Implemented** — rule is checked in `scan/shared/criteria.py`
**—** — not yet automated (manual check or future enhancement)

Of the 46 rules, **16 are automated** in the current scanner. The remaining rules
require either manual review, real-time data (earnings calendar, sector trend), or
apply only at the trade management stage.

---

## Thresholds (Current Config)

Modify in `scan/config.py` or override via `scan/.env`:

| Setting | Default | Rule |
|---------|---------|------|
| `MIN_PRICE` | $5.00 | R1 |
| `MIN_AVG_VOLUME` | 300,000 | R2 |
| `MIN_ADR_PCT` | 3.0% | R3 |
| `MIN_PRIOR_MOVE_PCT` | ~~30%~~ **25%** | R6 |
| `MAX_PRIOR_MOVE_DAYS` | ~~40~~ **60** | R6 |
| `MIN_VOL_SURGE_RATIO` | 2.0× | R7 |
| `MAX_FROM_52W_HIGH` | 20% | R9 |
| `MIN_BASE_DAYS` | 5 | R11 |
| `MAX_BASE_DAYS` | 40 | R11 |
| `MAX_BASE_DEPTH_PCT` | 15% | R12 |
| `MAX_BASE_VOL_RATIO` | ~~60%~~ **75%** | R19 |
| `MIN_CONSEC_LOW_VOL_DAYS` | 3 | R20 |
| `MAX_DIST_FROM_PIVOT_PCT` | 5% | Watchlist trigger |
| `MIN_BREAKOUT_VOL_RATIO` | 1.5× | R24 |
| `MAX_CLOSE_FROM_HIGH_PCT` | 5% | R25 |

---

## Stage Flow

```
R1–R5    Universe Filter      → price, volume, ADR minimum bars
    ↓
R6–R10   Prior Move           → 30%+ explosive move near 52w high
    ↓
R11–R18  Base Quality         → tight consolidation 5–40 days, ≤15% depth
    ↓
R19–R22  Volume Contraction   → base avg vol ≤ 60% of 50d avg
    ↓
         Watchlist Trigger    → within 5% of pivot → add to watchlist
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

| Date | Parameter | Old Value | New Value | Reason |
|------|-----------|-----------|-----------|--------|
| 2026-04-27 | `MIN_PRIOR_MOVE_PCT` | 30% | 25% | Analysis showed 25 additional stocks would qualify; prior move still confirmed with volume surge |
| 2026-04-27 | `MAX_PRIOR_MOVE_DAYS` | 40 days | 60 days | Analysis showed 29 additional stocks would qualify; valid setups often form 10–12 weeks after the move |
| 2026-04-27 | `MAX_BASE_VOL_RATIO` | 60% | 75% | Stage 4 was the binding constraint after prior move changes; loosened to capture more setups with adequate (not extreme) volume contraction |

---

*Source: `qullamaggie/breakouts/Rules.MD`*
*Last updated: 2026-04-27*
