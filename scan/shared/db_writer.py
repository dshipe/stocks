"""
db_writer.py — SQL Server database operations.

Uses pyodbc with parameterized queries throughout.
All writes use explicit INSERT/UPDATE — no ORM.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from datetime import date, datetime

import pyodbc

import config as cfg

logger = logging.getLogger(__name__)


# ─── Connection ────────────────────────────────────────────────────────────────

def get_connection() -> pyodbc.Connection:
    """Return a pyodbc connection to the configured SQL Server database."""
    return pyodbc.connect(cfg.DB_CONNECTION_STRING, timeout=10)


def test_connection() -> bool:
    """Return True if DB connection succeeds, False otherwise."""
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        return False


# ─── Watchlist ─────────────────────────────────────────────────────────────────

def insert_watchlist_entry(data: dict) -> int | None:
    """
    Insert a row into watchlist_entries.

    Expected keys in data:
        scan_date, ticker, company_name, price_at_scan, pivot_price,
        pct_from_pivot, prior_move_pct, prior_move_days, base_depth_pct,
        base_duration_days, volume_contraction_ratio, adr_pct, avg_daily_volume,
        distance_to_pivot_pct, ma10_above_ma20, above_50d_ma,
        volume_contraction_days, qualification_reasons, pattern_type, pattern_grade

    Returns the new row's id or None on failure.
    """
    sql = """
        INSERT INTO watchlist_entries (
            scan_date, ticker, company_name, price_at_scan, pivot_price,
            pct_from_pivot, prior_move_pct, prior_move_days, base_depth_pct,
            base_duration_days, volume_contraction_ratio, adr_pct, avg_daily_volume,
            distance_to_pivot_pct, ma10_above_ma20, above_50d_ma,
            volume_contraction_days, qualification_reasons, pattern_type, pattern_grade
        )
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (
            data.get("scan_date",               date.today()),
            data.get("ticker",                  ""),
            data.get("company_name",            None),
            data.get("price_at_scan",           None),
            data.get("pivot_price",             None),
            data.get("pct_from_pivot",          None),
            data.get("prior_move_pct",          None),
            data.get("prior_move_days",         None),
            data.get("base_depth_pct",          None),
            data.get("base_duration_days",      None),
            data.get("volume_contraction_ratio",None),
            data.get("adr_pct",                 None),
            data.get("avg_daily_volume",        None),
            data.get("distance_to_pivot_pct",   None),
            1 if data.get("ma10_above_ma20") else 0,
            1 if data.get("above_50d_ma")    else 0,
            data.get("volume_contraction_days", None),
            data.get("qualification_reasons",   None),
            data.get("pattern_type",            None),
            data.get("pattern_grade",           None),
        ))
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"insert_watchlist_entry({data.get('ticker')}): {e}")
        return None


# ─── Runners ────────────────────────────────────────────────────────────────────────────

def insert_runner_entry(data: dict) -> int | None:
    """
    Insert a row into runner_entries.

    Expected keys in data:
        scan_date, ticker, price_at_scan, pct_1m, pct_3m, pct_6m,
        pct_from_52w_high, pct_from_20d_high, prior_move_pct,
        prior_move_days, adr_pct, avg_daily_volume

    Returns the new row's id or None on failure.
    Silently skips if the same (scan_date, ticker) already exists.
    """
    sql = """
        INSERT INTO runner_entries (
            scan_date, ticker, price_at_scan, pct_1m, pct_3m, pct_6m,
            pct_from_52w_high, pct_from_20d_high, prior_move_pct,
            prior_move_days, adr_pct, avg_daily_volume
        )
        OUTPUT INSERTED.id
        SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM runner_entries
            WHERE scan_date = ? AND ticker = ?
        );
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        sd     = data["scan_date"]
        tk     = data["ticker"]
        cursor.execute(sql,
            sd, tk,
            data.get("price_at_scan"),
            data.get("pct_1m"),
            data.get("pct_3m"),
            data.get("pct_6m"),
            data.get("pct_from_52w_high"),
            data.get("pct_from_20d_high"),
            data.get("prior_move_pct", 0),
            data.get("prior_move_days", 0),
            data.get("adr_pct"),
            data.get("avg_daily_volume"),
            sd, tk,
        )
        row    = cursor.fetchone()
        conn.commit()
        conn.close()
        return int(row[0]) if row and row[0] else None
    except Exception as e:
        logger.error(f"insert_runner_entry({data.get('ticker')}): {e}")
        return None


def get_todays_watchlist() -> list[dict]:
    """
    Return all watchlist entries for today.

    Returns list of dicts with: id, ticker, pivot_price, pattern_type, pattern_grade
    """
    sql = """
        SELECT id, ticker, pivot_price, pattern_type, pattern_grade
        FROM   watchlist_entries
        WHERE  scan_date = CAST(GETDATE() AS DATE)
        ORDER  BY pattern_grade ASC, pct_from_pivot ASC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "watchlist_entry_id": r[0],
                "ticker":             r[1],
                "pivot_price":        float(r[2]) if r[2] else None,
                "pattern_type":       r[3],
                "pattern_grade":      r[4],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"get_todays_watchlist: {e}")
        return []


# ─── Breakout Entries ──────────────────────────────────────────────────────────

def breakout_already_logged_today(ticker: str) -> bool:
    """Return True if a breakout for this ticker has already been recorded today."""
    sql = """
        SELECT COUNT(*) FROM breakout_entries
        WHERE  ticker = ? AND scan_date = CAST(GETDATE() AS DATE)
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (ticker,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        logger.error(f"breakout_already_logged_today({ticker}): {e}")
        return False


def insert_breakout_entry(data: dict) -> int | None:
    """
    Insert a row into breakout_entries.

    Expected keys in data:
        scan_date, ticker, breakout_price, pivot_price, breakout_volume,
        avg_volume_20d, volume_ratio, candle_close_pct, prior_move_pct,
        prior_move_days, base_depth_pct, base_duration_days,
        volume_contraction_ratio, adr_pct, avg_daily_volume,
        ma10_above_ma20, above_50d_ma, stop_price, atr_14,
        risk_per_share, suggested_rr_ratio, pattern_type, pattern_grade,
        is_episodic_pivot, catalyst_notes, sp500_above_50d_ma,
        sp500_above_200d_ma, vix_level, sector_trend,
        qualification_reasons, was_on_watchlist, watchlist_entry_id

    Returns the new row's id or None on failure.
    """
    sql = """
        INSERT INTO breakout_entries (
            scan_date, ticker, breakout_price, pivot_price, breakout_volume,
            avg_volume_20d, volume_ratio, candle_close_pct,
            prior_move_pct, prior_move_days, base_depth_pct, base_duration_days,
            volume_contraction_ratio, adr_pct, avg_daily_volume,
            ma10_above_ma20, above_50d_ma, stop_price, atr_14,
            risk_per_share, suggested_rr_ratio, pattern_type, pattern_grade,
            is_episodic_pivot, catalyst_notes, sp500_above_50d_ma,
            sp500_above_200d_ma, vix_level, sector_trend,
            qualification_reasons, was_on_watchlist, watchlist_entry_id
        )
        OUTPUT INSERTED.id
        VALUES (
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?,?,?,?,?,?,
            ?,?
        )
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (
            data.get("scan_date",               date.today()),
            data.get("ticker",                  ""),
            data.get("breakout_price",          None),
            data.get("pivot_price",             None),
            data.get("breakout_volume",         None),
            data.get("avg_volume_20d",          None),
            data.get("volume_ratio",            None),
            data.get("candle_close_pct",        None),
            data.get("prior_move_pct",          None),
            data.get("prior_move_days",         None),
            data.get("base_depth_pct",          None),
            data.get("base_duration_days",      None),
            data.get("volume_contraction_ratio",None),
            data.get("adr_pct",                 None),
            data.get("avg_daily_volume",        None),
            1 if data.get("ma10_above_ma20") else 0,
            1 if data.get("above_50d_ma")    else 0,
            data.get("stop_price",              None),
            data.get("atr_14",                  None),
            data.get("risk_per_share",          None),
            data.get("suggested_rr_ratio",      None),
            data.get("pattern_type",            None),
            data.get("pattern_grade",           None),
            1 if data.get("is_episodic_pivot") else 0,
            data.get("catalyst_notes",          None),
            1 if data.get("sp500_above_50d_ma")  else 0,
            1 if data.get("sp500_above_200d_ma") else 0,
            data.get("vix_level",               None),
            data.get("sector_trend",            None),
            data.get("qualification_reasons",   None),
            1 if data.get("was_on_watchlist")  else 0,
            data.get("watchlist_entry_id",      None),
        ))
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"insert_breakout_entry({data.get('ticker')}): {e}")
        return None


# ─── Performance Tracking ──────────────────────────────────────────────────────

def get_pending_watchlist_performance() -> list[dict]:
    """
    Return watchlist entries that are missing at least some performance data.
    Looks back up to 90 days.
    """
    sql = """
        SELECT
            e.id, e.ticker, e.scan_date, e.pivot_price,
            e.price_at_scan,
            p.price_1d, p.price_5d, p.price_10d, p.price_20d, p.price_60d
        FROM watchlist_entries e
        LEFT JOIN watchlist_performance p ON p.watchlist_id = e.id
        WHERE e.scan_date >= DATEADD(day, -90, CAST(GETDATE() AS DATE))
          AND (
              p.id IS NULL
              OR p.price_60d IS NULL
          )
        ORDER BY e.scan_date DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "watchlist_id":  r[0],
                "ticker":        r[1],
                "scan_date":     r[2],
                "pivot_price":   float(r[3]) if r[3] else None,
                "entry_price":   float(r[4]) if r[4] else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"get_pending_watchlist_performance: {e}")
        return []


def get_pending_breakout_performance() -> list[dict]:
    """Return breakout entries missing at least some performance data."""
    sql = """
        SELECT
            e.id, e.ticker, e.scan_date, e.breakout_price, e.stop_price,
            e.pivot_price,
            p.price_1d, p.price_5d, p.price_10d, p.price_20d, p.price_60d
        FROM breakout_entries e
        LEFT JOIN breakout_performance p ON p.breakout_id = e.id
        WHERE e.scan_date >= DATEADD(day, -90, CAST(GETDATE() AS DATE))
          AND (
              p.id IS NULL
              OR p.price_60d IS NULL
          )
        ORDER BY e.scan_date DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "breakout_id":   r[0],
                "ticker":        r[1],
                "scan_date":     r[2],
                "entry_price":   float(r[3]) if r[3] else None,
                "stop_price":    float(r[4]) if r[4] else None,
                "pivot_price":   float(r[5]) if r[5] else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"get_pending_breakout_performance: {e}")
        return []


def upsert_watchlist_performance(watchlist_id: int, perf: dict) -> bool:
    """Insert or update a watchlist_performance row."""
    # Check if row exists
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM watchlist_performance WHERE watchlist_id = ?",
            (watchlist_id,)
        )
        existing = cursor.fetchone()

        if existing:
            sql = """
                UPDATE watchlist_performance SET
                    price_1d        = COALESCE(?, price_1d),
                    price_3d        = COALESCE(?, price_3d),
                    price_5d        = COALESCE(?, price_5d),
                    price_10d       = COALESCE(?, price_10d),
                    price_20d       = COALESCE(?, price_20d),
                    price_60d       = COALESCE(?, price_60d),
                    pct_change_1d   = COALESCE(?, pct_change_1d),
                    pct_change_5d   = COALESCE(?, pct_change_5d),
                    pct_change_10d  = COALESCE(?, pct_change_10d),
                    pct_change_20d  = COALESCE(?, pct_change_20d),
                    pct_change_60d  = COALESCE(?, pct_change_60d),
                    did_break_out   = COALESCE(?, did_break_out),
                    max_gain_pct    = COALESCE(?, max_gain_pct),
                    max_gain_date   = COALESCE(?, max_gain_date),
                    updated_at      = GETDATE()
                WHERE watchlist_id = ?
            """
        else:
            sql = """
                INSERT INTO watchlist_performance (
                    watchlist_id, ticker, scan_date,
                    price_1d, price_3d, price_5d, price_10d, price_20d, price_60d,
                    pct_change_1d, pct_change_5d, pct_change_10d, pct_change_20d, pct_change_60d,
                    did_break_out, max_gain_pct, max_gain_date
                ) VALUES (?, ?, ?,  ?,?,?,?,?,?,  ?,?,?,?,?,  ?,?,?)
            """

        if existing:
            cursor.execute(sql, (
                perf.get("price_1d"),  perf.get("price_3d"),  perf.get("price_5d"),
                perf.get("price_10d"), perf.get("price_20d"), perf.get("price_60d"),
                perf.get("pct_change_1d"),  perf.get("pct_change_5d"),
                perf.get("pct_change_10d"), perf.get("pct_change_20d"),
                perf.get("pct_change_60d"),
                1 if perf.get("did_break_out") else None,
                perf.get("max_gain_pct"), perf.get("max_gain_date"),
                watchlist_id,
            ))
        else:
            cursor.execute(sql, (
                watchlist_id, perf.get("ticker"), perf.get("scan_date"),
                perf.get("price_1d"),  perf.get("price_3d"),  perf.get("price_5d"),
                perf.get("price_10d"), perf.get("price_20d"), perf.get("price_60d"),
                perf.get("pct_change_1d"),  perf.get("pct_change_5d"),
                perf.get("pct_change_10d"), perf.get("pct_change_20d"),
                perf.get("pct_change_60d"),
                1 if perf.get("did_break_out") else 0,
                perf.get("max_gain_pct"), perf.get("max_gain_date"),
            ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"upsert_watchlist_performance({watchlist_id}): {e}")
        return False


def upsert_breakout_performance(breakout_id: int, perf: dict) -> bool:
    """Insert or update a breakout_performance row."""
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM breakout_performance WHERE breakout_id = ?",
            (breakout_id,)
        )
        existing = cursor.fetchone()

        if existing:
            sql = """
                UPDATE breakout_performance SET
                    price_1d          = COALESCE(?, price_1d),
                    price_3d          = COALESCE(?, price_3d),
                    price_5d          = COALESCE(?, price_5d),
                    price_10d         = COALESCE(?, price_10d),
                    price_20d         = COALESCE(?, price_20d),
                    price_60d         = COALESCE(?, price_60d),
                    pct_change_1d     = COALESCE(?, pct_change_1d),
                    pct_change_5d     = COALESCE(?, pct_change_5d),
                    pct_change_10d    = COALESCE(?, pct_change_10d),
                    pct_change_20d    = COALESCE(?, pct_change_20d),
                    pct_change_60d    = COALESCE(?, pct_change_60d),
                    hit_stop          = COALESCE(?, hit_stop),
                    hit_stop_date     = COALESCE(?, hit_stop_date),
                    max_r_multiple    = COALESCE(?, max_r_multiple),
                    max_gain_pct      = COALESCE(?, max_gain_pct),
                    max_gain_date     = COALESCE(?, max_gain_date),
                    was_failed_breakout = COALESCE(?, was_failed_breakout),
                    updated_at        = GETDATE()
                WHERE breakout_id = ?
            """
            cursor.execute(sql, (
                perf.get("price_1d"),  perf.get("price_3d"),  perf.get("price_5d"),
                perf.get("price_10d"), perf.get("price_20d"), perf.get("price_60d"),
                perf.get("pct_change_1d"),  perf.get("pct_change_5d"),
                perf.get("pct_change_10d"), perf.get("pct_change_20d"),
                perf.get("pct_change_60d"),
                1 if perf.get("hit_stop")            else None,
                perf.get("hit_stop_date"),
                perf.get("max_r_multiple"),
                perf.get("max_gain_pct"),
                perf.get("max_gain_date"),
                1 if perf.get("was_failed_breakout") else None,
                breakout_id,
            ))
        else:
            sql = """
                INSERT INTO breakout_performance (
                    breakout_id, ticker, breakout_date, breakout_price, stop_price,
                    price_1d, price_3d, price_5d, price_10d, price_20d, price_60d,
                    pct_change_1d, pct_change_5d, pct_change_10d, pct_change_20d, pct_change_60d,
                    hit_stop, hit_stop_date, max_r_multiple, max_gain_pct, max_gain_date,
                    was_failed_breakout
                ) VALUES (?,?,?,?,?,  ?,?,?,?,?,?,  ?,?,?,?,?,  ?,?,?,?,?,  ?)
            """
            cursor.execute(sql, (
                breakout_id,
                perf.get("ticker"),
                perf.get("breakout_date"),
                perf.get("entry_price"),
                perf.get("stop_price"),
                perf.get("price_1d"),  perf.get("price_3d"),  perf.get("price_5d"),
                perf.get("price_10d"), perf.get("price_20d"), perf.get("price_60d"),
                perf.get("pct_change_1d"),  perf.get("pct_change_5d"),
                perf.get("pct_change_10d"), perf.get("pct_change_20d"),
                perf.get("pct_change_60d"),
                1 if perf.get("hit_stop")            else 0,
                perf.get("hit_stop_date"),
                perf.get("max_r_multiple"),
                perf.get("max_gain_pct"),
                perf.get("max_gain_date"),
                1 if perf.get("was_failed_breakout") else 0,
            ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"upsert_breakout_performance({breakout_id}): {e}")
        return False
