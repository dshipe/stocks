# Data Requirements for Breakout Detection

> This document specifies what historical stock data is needed to apply Qullamaggie breakout rules,
> what changes are required to the `maximum-pain.com/candlestick/AAPL` data source,
> and how much history is necessary for reliable pattern detection.

---

## How Much Historical Stock Data Is Needed?

### For Pattern Detection (Immediate Setup Scanning)
**Minimum required: 1 year (252 trading days)**

To identify whether a stock currently has a valid Qullamaggie breakout setup, you need:

| Data Needed | Why It's Required | Minimum History |
|-------------|-------------------|-----------------|
| OHLCV daily bars | Calculate the prior move, base, volume contraction | 252 trading days (1 year) |
| 10-day moving average | Trend filter inside the base | 10 days |
| 20-day moving average | Trend filter, trailing stop | 20 days |
| 50-day moving average | Ensure stock is above 50-day during base | 50 days |
| 200-day moving average | Confirm long-term uptrend | 200 days |
| 52-week high/low | Check if stock is within 10–20% of 52-week high | 252 days |
| Average Daily Volume (ADV) | Volume contraction comparison (20-day and 50-day rolling) | 50 days |
| Average True Range (ATR-14) | Stop-loss calculation | 14 days |
| Average Daily Range % (ADR) | Filter for moveable stocks (ADR > 3%) | 20 days |

**Recommended: 2 years (504 trading days)**
- Allows detection of multiple consolidation cycles
- Provides robust comparison for relative strength vs. S&P 500
- Enables backtesting on the same dataset

### For Backtesting Breakout Strategies
**Recommended: 5 years (1,260 trading days)**

For validating that the Rules.MD criteria are working correctly and backtesting the strategy across different market conditions (bull, bear, sideways), 5 years of data covers:
- At least one complete market cycle
- COVID crash (2020) and recovery
- 2022 bear market
- 2023–2024 bull market

### For Long-Term Screening (Weekly/Monthly Patterns)
**Maximum useful: 10 years**

While 10 years of data is valuable for research, it is not required for daily breakout scanning. The 10-year lookback is primarily useful for:
- Identifying mega-cap stocks making all-time high breakouts
- Cup-with-handle patterns that develop over 1–2 years
- Understanding a stock's complete trend history

### Summary Recommendation

| Use Case | Data Needed |
|----------|------------|
| Daily breakout scanning | **1–2 years** |
| Backtesting / validation | **5 years** |
| Deep research / long patterns | **10 years** |
| System default recommendation | **2 years (504 trading days)** |

---

## Current State of maximum-pain.com/candlestick/AAPL

Based on analysis of the existing codebase, the current candlestick chart page at `http://maximum-pain.com/candlestick/AAPL` uses:

### Existing Data Model (`HistoricalStock.cs`)
```csharp
public partial class HistoricalStock
{
    public string? symbol { get; set; }
    public decimal lastPrice { get; set; }
    public decimal openPrice { get; set; }
    public decimal highPrice { get; set; }
    public decimal lowPrice { get; set; }
    public decimal closePrice { get; set; }
    public DateTime createdOn { get; set; }
}
```

### Current Limitations
1. **No volume field** — the `HistoricalStock` model does not include a `volume` field
2. **No calculated indicators** — no moving averages, ATR, ADR, or other derived fields
3. **Limited history stored** — the `HistoryService.HistoricalStock()` method takes `pastDays` / `futureDays` parameters; depth of stored data is unclear
4. **No relative strength data** — no comparison to S&P 500 / NASDAQ
5. **No breakout detection logic** — the chart is display-only, no pattern detection
6. **Single-stock view** — no batch screening capability

---

## Required Changes to the Candlestick Data Source

### Change 1: Add Volume to the HistoricalStock Model

**Priority: Critical** — Volume is essential for every breakout rule.

**Current:**
```csharp
public partial class HistoricalStock
{
    public decimal openPrice { get; set; }
    public decimal highPrice { get; set; }
    public decimal lowPrice { get; set; }
    public decimal closePrice { get; set; }
    public DateTime createdOn { get; set; }
}
```

**Required:**
```csharp
public partial class HistoricalStock
{
    public decimal openPrice { get; set; }
    public decimal highPrice { get; set; }
    public decimal lowPrice { get; set; }
    public decimal closePrice { get; set; }
    public long volume { get; set; }              // ADD: daily trading volume
    public long averageVolume20d { get; set; }    // ADD: 20-day average volume
    public DateTime createdOn { get; set; }
}
```

**Database change required:**
```sql
ALTER TABLE HistoricalStockQuote ADD volume BIGINT NULL;
ALTER TABLE HistoricalStockQuote ADD averageVolume20d BIGINT NULL;
```

---

### Change 2: Add Computed Technical Indicators

**Priority: High** — Rules R12–R22 all require moving averages and ATR.

Add a new `BreakoutIndicators` model (or extend `HistoricalStock`):

```csharp
public class BreakoutIndicators
{
    public string ticker { get; set; }
    public DateTime date { get; set; }
    
    // Moving Averages
    public decimal ma10 { get; set; }        // 10-day simple MA of close
    public decimal ma20 { get; set; }        // 20-day simple MA of close
    public decimal ma50 { get; set; }        // 50-day simple MA of close
    public decimal ma200 { get; set; }       // 200-day simple MA of close
    
    // Volume Averages
    public long avgVol20d { get; set; }      // 20-day average daily volume
    public long avgVol50d { get; set; }      // 50-day average daily volume
    
    // Volatility
    public decimal atr14 { get; set; }       // 14-day Average True Range
    public decimal adrPct { get; set; }      // Average Daily Range %
    
    // Range Context
    public decimal high52w { get; set; }     // 52-week high
    public decimal low52w { get; set; }      // 52-week low
    public decimal pctFrom52wHigh { get; set; }  // % below 52-week high
}
```

---

### Change 3: Add Prior Move Detection

**Priority: High** — Rules R6–R10 require detection of the prior explosive move.

Add to the API or a new breakout scanning service:

```csharp
public class PriorMoveResult
{
    public string ticker { get; set; }
    public DateTime moveStartDate { get; set; }
    public DateTime moveHighDate { get; set; }
    public decimal moveStartPrice { get; set; }
    public decimal moveHighPrice { get; set; }
    public decimal movePctGain { get; set; }         // % gain
    public int moveDurationDays { get; set; }        // trading days
    public bool meetsMinimumThreshold { get; set; }  // true if >= 30%
}

// Query: Find stocks with 30%+ move in last 40 trading days
// SELECT ticker, MIN(close) as low, MAX(close) as high, 
//        (MAX(close) - MIN(close)) / MIN(close) * 100 as pctMove
// FROM HistoricalStockQuote
// WHERE createdOn >= DATEADD(day, -60, GETDATE())
// GROUP BY ticker
// HAVING (MAX(close) - MIN(close)) / MIN(close) * 100 >= 30
```

---

### Change 4: Add Base Detection Logic

**Priority: High** — Rules R11–R18 require base pattern detection.

New service method needed:

```csharp
public interface IBreakoutScanService
{
    // Detect if a stock is currently in a valid base
    Task<BaseAnalysis> AnalyzeBase(string ticker, int lookbackDays = 252);
    
    // Scan all tickers for breakout setups
    Task<List<BreakoutCandidate>> ScanForBreakouts(List<string> tickers);
    
    // Get full breakout score for a single ticker
    Task<BreakoutScore> ScoreBreakout(string ticker);
}

public class BaseAnalysis
{
    public string ticker { get; set; }
    public bool isInBase { get; set; }
    public int baseDuration { get; set; }        // trading days
    public decimal baseDepthPct { get; set; }    // high-to-low %
    public decimal pivotPrice { get; set; }      // breakout trigger price
    public decimal volumeContraction { get; set; }  // vol vs. avg
    public int vcpContractionsCount { get; set; }   // number of VCP contractions
    public string patternType { get; set; }      // "FlatBase", "HTF", "VCP", "Pennant"
}

public class BreakoutCandidate
{
    public string ticker { get; set; }
    public decimal currentPrice { get; set; }
    public decimal pivotPrice { get; set; }
    public decimal priorMovePct { get; set; }
    public decimal riskRewardRatio { get; set; }
    public string patternType { get; set; }
    public int setupGrade { get; set; }          // 1-5 (A+ to F)
    public bool isBreakingOut { get; set; }      // currently crossing pivot
}
```

---

### Change 5: Add Breakout Alert Endpoint

**Priority: Medium** — New API endpoint for `maximum-pain.com/candlestick/AAPL`

New controller endpoint:

```csharp
// GET /api/breakout/{ticker}
[HttpGet("breakout/{ticker}")]
public async Task<IActionResult> GetBreakoutAnalysis(string ticker)
{
    var analysis = await _breakoutScanService.AnalyzeBase(ticker);
    var score = await _breakoutScanService.ScoreBreakout(ticker);
    return Ok(new { analysis, score });
}

// GET /api/breakout/scan?minPriorMove=30&minAdv=300000
[HttpGet("breakout/scan")]
public async Task<IActionResult> ScanBreakouts(
    decimal minPriorMove = 30, 
    int minAdv = 300000,
    decimal minPrice = 5)
{
    var tickers = await _stockService.GetAllActiveTickers();
    var candidates = await _breakoutScanService.ScanForBreakouts(tickers);
    return Ok(candidates);
}
```

---

### Change 6: Extend Historical Data Retention

**Priority: High** — To support breakout scanning, 2 years of daily OHLCV data must be retained.

**Current estimated retention:** Based on the `HistoricalStock` model and data service, retention may be less than 252 days (1 year).

**Required:**
```sql
-- Ensure at least 504 trading days (2 years) of daily stock OHLCV data per ticker
-- Currently: unknown retention window
-- Required: minimum 504 rows per active ticker in HistoricalStockQuote table

-- To verify current data availability:
SELECT ticker, 
       MIN(createdOn) as oldest_date, 
       MAX(createdOn) as newest_date,
       COUNT(*) as total_bars
FROM HistoricalStockQuote
GROUP BY ticker
ORDER BY COUNT(*) DESC
```

**Recommended data ingestion change:**
- Import 2 years of OHLCV + volume data for all active tickers via the existing `FinImportService` or a new Schwab/data provider API call
- Store in the existing `HistoricalStockQuote` table with the volume field added (Change 1)

---

### Change 7: Add Relative Strength vs. Index

**Priority: Medium** — Rules R10 and R43–R46 require market context.

```csharp
public class RelativeStrength
{
    public string ticker { get; set; }
    public DateTime date { get; set; }
    public decimal rsRating { get; set; }        // 1–99 scale (O'Neil style)
    public decimal rs3m { get; set; }            // 3-month relative performance vs. SPY
    public decimal rs6m { get; set; }            // 6-month relative performance vs. SPY
    public bool outperformingMarket { get; set; } // stock > S&P 500 return in same period
}
```

---

## Candlestick Chart Page Enhancement Needed

The existing `http://maximum-pain.com/candlestick/AAPL` page currently displays a basic candlestick chart. To support breakout analysis, the following UI additions are recommended:

### Required UI Elements

| Element | Description | Implementation |
|---------|-------------|----------------|
| Volume bars | Daily volume bars below the price chart | Add volume series to Google Charts or switch to a charting library like TradingView or Highcharts |
| Moving averages | Lines for MA10, MA20, MA50, MA200 | Overlay line series on price chart |
| Pivot price line | Horizontal line at the detected breakout price | Static horizontal annotation |
| Base highlight | Shaded region showing the detected base area | Annotation band |
| Breakout alert badge | Visual indicator if stock is at/near pivot | Badge/label overlay |
| Volume relative indicator | Bar color to show above/below average volume | Conditional color on volume bars |

### Suggested Charting Library Upgrade
The current implementation uses Google Charts, which has limited candlestick capabilities.

Consider upgrading to:
1. **TradingView Lightweight Charts** (free, highly capable) — `https://tradingview.github.io/lightweight-charts/`
2. **Highcharts Stock** (licensed, full-featured)
3. **ApexCharts** (free, good candlestick support)

---

## Data Source Options for Historical OHLCV

The current system uses Schwab API for live data. For 2-year historical OHLCV + volume:

| Source | Coverage | Cost | Notes |
|--------|----------|------|-------|
| **Schwab API** (existing) | 10 years daily | Free (with account) | Already integrated |
| **Polygon.io** | 20+ years | Free tier: 5 years | Good REST API |
| **Alpha Vantage** | 20+ years | Free tier limited | Rate limits |
| **Yahoo Finance (yfinance)** | 10+ years | Free | Python, no official API |
| **Tiingo** | 30+ years | Free tier | Good data quality |

**Recommendation:** Use the existing Schwab API connection to backfill 2 years of OHLCV + volume data for all tracked tickers. This avoids adding a new data provider dependency.

---

## Implementation Priority Order

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Add volume to `HistoricalStock` model + DB | Low | Critical |
| 2 | Extend historical data retention to 2 years | Medium | Critical |
| 3 | Compute MA10, MA20, MA50 and volume averages | Medium | High |
| 4 | Add prior move detection query | Medium | High |
| 5 | Build `IBreakoutScanService` | High | High |
| 6 | Add breakout API endpoints | Medium | High |
| 7 | Enhance candlestick chart UI (volume + MAs) | Medium | Medium |
| 8 | Add relative strength calculation | High | Medium |
| 9 | Upgrade charting library | High | Low-Medium |
