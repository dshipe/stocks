"""
data_fetcher.py — Market data retrieval and indicator computation.

Uses yfinance as the primary data source (free, no API key required).
Polygon.io can be swapped in later by changing the fetch functions.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import yfinance as yf

# ─── Constants ────────────────────────────────────────────────────────────────
BULK_BATCH_SIZE = 200   # tickers per yf.download() call

try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False

logger = logging.getLogger(__name__)


# ─── Ticker Universe ───────────────────────────────────────────────────────────

# Hyphen-suffixed warrant/right/unit patterns common in Nasdaq listings
_JUNK_SUFFIXES = ("-W", "-WS", "-WD", "-WT", "-R", "-RT", "-U", "-UN", "-RI")


def _is_valid_ticker(ticker: str) -> bool:
    """
    Return False for obvious non-common-stock symbols:
      - warrants  (e.g. ACHRW, JOBY-WS)
      - rights    (e.g. XYZ-R)
      - units     (e.g. ABC-U)
      - pure-digit or empty symbols
    """
    t = ticker.upper()
    if not t or len(t) > 5:
        return False
    # Hyphen-suffix junk
    for suffix in _JUNK_SUFFIXES:
        if t.endswith(suffix):
            return False
    # 5-char Nasdaq warrants: all-alpha base + trailing W (e.g. ACHRW, NUVBW)
    if len(t) == 5 and t.endswith("W") and t[:4].isalpha():
        return False
    # Tickers that are purely numeric or contain no letters
    if not any(c.isalpha() for c in t):
        return False
    return True


def get_ticker_universe() -> list[str]:
    """
    Return a deduplicated list of tickers to scan.

    Primary source: yahoo_fin.stock_info for S&P 500 and Nasdaq tickers.
    Falls back to a curated hardcoded list if both are unreachable.
    """
    tickers = []

    # S&P 500 — try yahoo_fin first, fall back to GitHub-hosted CSV
    try:
        from yahoo_fin import stock_info as si
        sp500 = si.tickers_sp500()
        sp500 = [t.replace(".", "-") for t in sp500]
        tickers.extend(sp500)
        logger.info(f"Loaded {len(sp500)} S&P 500 tickers from yahoo_fin")
    except Exception as e:
        logger.warning(f"yahoo_fin S&P 500 failed ({e}), trying GitHub CSV fallback…")
        try:
            import requests
            from io import StringIO
            resp = requests.get(
                "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
                timeout=15,
            )
            resp.raise_for_status()
            sp500_df = pd.read_csv(StringIO(resp.text))
            sp500 = [t.replace(".", "-") for t in sp500_df["Symbol"].tolist()]
            tickers.extend(sp500)
            logger.info(f"Loaded {len(sp500)} S&P 500 tickers from GitHub CSV fallback")
        except Exception as e2:
            logger.warning(f"GitHub CSV S&P 500 fallback also failed: {e2}")

    # Nasdaq
    try:
        from yahoo_fin import stock_info as si
        nasdaq = si.tickers_nasdaq()
        nasdaq = [t.replace(".", "-") for t in nasdaq]
        tickers.extend(nasdaq)
        logger.info(f"Loaded {len(nasdaq)} Nasdaq tickers from yahoo_fin")
    except Exception as e:
        logger.warning(f"Could not fetch Nasdaq tickers from yahoo_fin: {e}")

    # Deduplicate + filter out warrants, rights, units, blank/bad symbols
    tickers = sorted(set(t for t in tickers if _is_valid_ticker(t)))

    if not tickers:
        logger.warning("Falling back to hardcoded starter universe (500 tickers)")
        tickers = [
            # Mega-cap / S&P 500 core
            "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AVGO","BRK-B",
            "LLY","JPM","V","UNH","XOM","MA","COST","HD","PG","JNJ",
            "ABBV","BAC","NFLX","CRM","WMT","MRK","CVX","KO","AMD","ACN",
            "PEP","LIN","MCD","TMO","ADBE","ABT","CSCO","ORCL","QCOM","INTU",
            "GE","DIS","CAT","NOW","TXN","IBM","AMAT","SPGI","GS","ISRG",
            "BKNG","LRCX","PANW","KLAC","SNPS","CDNS","AXP","ADI","REGN","PLD",
            # High-growth / momentum names
            "CRWD","DDOG","NET","ZS","SNOW","MDB","TEAM","HUBS","VEEV","GTLB",
            "CELH","ENPH","AXON","SMCI","PLTR","UBER","DASH","ABNB","SQ","COIN",
            "MELI","SE","SPOT","RBLX","U","PATH","BILL","ZM","DOCU","TWLO",
            "TTD","ROKU","OPEN","IONQ","RGTI","QUBT","ACHR","JOBY","LUNR","RKLB",
            # Mid/small cap momentum
            "APP","HIMS","DUOL","IBKR","LPLA","TOST","FRPT","ELF","XPOF","ONON",
            "PODD","IRTC","TMDX","STVN","HRMY","RXST","PTCT","SWTX","AMSC","POWL",
            "KTOS","CACI","SAIC","DRS","LDOS","BAH","BWXT","HII","TDL","CDRE",
            # Energy / commodities
            "OXY","DVN","FANG","MPC","VLO","PSX","SLB","HAL","BKR","NOV",
            # Financials
            "SOFI","AFRM","UPST","HOOD","NU","PYPL","FIS","FI","GPN","AMP",
        ]

    return tickers


# ─── Historical Data ───────────────────────────────────────────────────────────

def bulk_fetch_history(tickers: list[str], days: int = 365) -> dict[str, pd.DataFrame]:
    """
    Batch-download daily OHLCV history for a large list of tickers via yfinance.

    Downloads in chunks of BULK_BATCH_SIZE (default 200) so that one HTTP
    request covers hundreds of tickers.  Much faster than calling
    fetch_history() individually for large universes.

    Returns dict of {ticker: DataFrame} for tickers with sufficient data (≥20 rows).
    Tickers with no data or errors are silently skipped.
    """
    end       = datetime.today()
    start     = end - timedelta(days=days + 30)   # buffer for indicator warm-up
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    results = {}
    batches = [tickers[i : i + BULK_BATCH_SIZE] for i in range(0, len(tickers), BULK_BATCH_SIZE)]

    for batch_num, batch in enumerate(batches, 1):
        logger.info(f"Downloading batch {batch_num}/{len(batches)} ({len(batch)} tickers)…")
        try:
            raw = yf.download(
                batch,
                start=start_str,
                end=end_str,
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            if raw is None or raw.empty:
                continue

            for ticker in batch:
                try:
                    # Single-ticker download returns a flat DataFrame; multi-ticker
                    # uses a (ticker, field) MultiIndex — access with raw[ticker].
                    df = raw.copy() if len(batch) == 1 else raw[ticker].copy()
                    df = df[["Open", "High", "Low", "Close", "Volume"]]
                    df = df.dropna(subset=["Close"])
                    df.index = pd.to_datetime(df.index).tz_localize(None)
                    if len(df) >= 20:
                        results[ticker] = df
                except (KeyError, Exception):
                    pass   # ticker had no data in this batch

        except Exception as e:
            logger.warning(f"Batch {batch_num} download failed: {e}")

    logger.info(f"bulk_fetch_history: got data for {len(results)}/{len(tickers)} tickers")
    return results


def fetch_history(ticker: str, days: int = 365) -> pd.DataFrame | None:
    """
    Fetch daily OHLCV history for a ticker via yfinance.

    Returns a DataFrame with columns: Open, High, Low, Close, Volume
    Index is a DatetimeIndex. Returns None on failure.
    """
    try:
        end   = datetime.today()
        start = end - timedelta(days=days + 30)  # buffer for indicator warm-up
        tk = yf.Ticker(ticker)
        df = tk.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        if df.empty or len(df) < 20:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)
        return df
    except Exception as e:
        logger.debug(f"fetch_history({ticker}): {e}")
        return None


def fetch_intraday(ticker: str) -> dict | None:
    """
    Fetch today's intraday data for a ticker.

    Returns a dict with:
        current_price   — latest trade price
        intraday_high   — session high so far
        intraday_low    — session low so far
        cum_volume      — cumulative shares traded today
        candle_close_pct — how close current price is to session high (%)

    Returns None on failure or if market is not open.
    """
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="1d", interval="1m")
        if df is None or df.empty:
            return None

        df.index = pd.to_datetime(df.index).tz_localize(None)
        current_price = float(df["Close"].iloc[-1])
        intraday_high = float(df["High"].max())
        intraday_low  = float(df["Low"].min())
        cum_volume    = int(df["Volume"].sum())

        # How close is current price to session high? (for R25 check)
        if intraday_high > 0:
            candle_close_pct = ((intraday_high - current_price) / intraday_high) * 100
        else:
            candle_close_pct = 999.0

        return {
            "current_price":   current_price,
            "intraday_high":   intraday_high,
            "intraday_low":    intraday_low,
            "cum_volume":      cum_volume,
            "candle_close_pct": candle_close_pct,
        }
    except Exception as e:
        logger.debug(f"fetch_intraday({ticker}): {e}")
        return None


# ─── Technical Indicators ─────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicator columns to a daily OHLCV DataFrame.

    Adds:
        ma10, ma20, ma50          — simple moving averages of Close
        avg_vol_20d, avg_vol_50d  — rolling average volume
        atr_14                    — 14-day Average True Range
        adr_pct                   — Average Daily Range % (20-day avg of (H-L)/L*100)
    """
    df = df.copy()

    # Moving averages
    df["ma10"] = df["Close"].rolling(10).mean()
    df["ma20"] = df["Close"].rolling(20).mean()
    df["ma50"] = df["Close"].rolling(50).mean()

    # Volume averages
    df["avg_vol_20d"] = df["Volume"].rolling(20).mean()
    df["avg_vol_50d"] = df["Volume"].rolling(50).mean()

    # ATR-14 (Average True Range)
    high_low   = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close  = (df["Low"]  - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = true_range.rolling(14).mean()

    # ADR% — average daily range as a percentage of prior close
    df["daily_range_pct"] = ((df["High"] - df["Low"]) / df["Close"].shift()) * 100
    df["adr_pct"]         = df["daily_range_pct"].rolling(20).mean()

    return df


# ─── Market Hours ─────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    """
    Return True if the US stock market is currently open.
    Market hours: Monday–Friday, 9:30 AM – 4:00 PM Eastern Time.
    Does not account for market holidays (add pandas_market_calendars for that).
    """
    try:
        if HAS_PYTZ:
            eastern = pytz.timezone("America/New_York")
            now_est = datetime.now(eastern)
        else:
            # Rough UTC-4/UTC-5 offset fallback
            utc_offset = -4  # EDT (adjust to -5 for EST in winter)
            now_est = datetime.utcnow() + timedelta(hours=utc_offset)

        # Must be a weekday (Mon=0 … Fri=4)
        if now_est.weekday() >= 5:
            return False

        open_time  = now_est.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_time = now_est.replace(hour=16, minute=0,  second=0, microsecond=0)

        return open_time <= now_est <= close_time

    except Exception:
        return False


def trading_days_between(start: date, end: date) -> int:
    """Approximate number of trading days between two dates (excludes weekends)."""
    bdays = pd.bdate_range(start=start, end=end)
    return len(bdays)
