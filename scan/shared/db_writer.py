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
import pytz

import config as cfg

logger = logging.getLogger(__name__)

_EASTERN = pytz.timezone("America/New_York")


def _today_est() -> date:
    """
    EST/EDT 'today', not the DB server's own clock. The server runs on UTC,
    so CAST(GETDATE() AS DATE) silently rolls over to the next calendar day
    during the ~8pm-midnight EST window while scan_date values (and the
    actual US trading day) are still "today" -- get_todays_watchlist(),
    get_todays_runners(), and breakout_already_logged_today() used to hit
    this directly via GETDATE() and would return nothing (or fail to see an
    already-logged breakout) during that window.
    """
    return datetime.now(_EASTERN).date()


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
    Silently skips if the same (scan_date, ticker) already exists.
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
        SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM watchlist_entries
            WHERE scan_date = ? AND ticker = ?
        );
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        sd = data.get("scan_date", date.today())
        tk = data.get("ticker", "")
        cursor.execute(sql, (
            sd,
            tk,
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
            # WHERE NOT EXISTS parameters
            sd, tk,
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
    Return watchlist entries for today that pass grade filters.

    Two grade floors apply:
      - MIN_BREAKOUT_GRADE (default B): global floor — C excluded for all patterns
      - MIN_HTF_BREAKOUT_GRADE (default A): HTF-specific floor — HTF/B also excluded
        Rationale: backtest shows HTF/B averages -0.40% at 5d with 36% BO rate.

    Returns list of dicts with: id, ticker, pivot_price, pattern_type, pattern_grade
    """
    allowed     = list(cfg.BREAKOUT_ALLOWED_GRADES)
    htf_allowed = list(cfg.HTF_ALLOWED_GRADES)
    ph          = ",".join("?" * len(allowed))
    htf_ph      = ",".join("?" * len(htf_allowed))
    sql = f"""
        SELECT id, ticker, pivot_price, pattern_type, pattern_grade
        FROM   watchlist_entries
        WHERE  scan_date = ?
          AND  pattern_grade IN ({ph})
          AND  (pattern_type != 'HTF' OR pattern_grade IN ({htf_ph}))
        ORDER  BY pattern_grade ASC, pct_from_pivot ASC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, [_today_est()] + allowed + htf_allowed)
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
        WHERE  ticker = ? AND scan_date = ?
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (ticker, _today_est()))
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


# ─── Trade Selection (R33/R34 — position sizing / concentration, for select_trades.py) ─

def get_breakout_candidates_for_date(target_date) -> list[dict]:
    """
    Breakout alerts for target_date, ranked grade-first then by R/R descending —
    the actual Stage-5-confirmed signals a trader would act on that day.
    """
    sql = """
        SELECT ticker, pattern_type, pattern_grade, breakout_price, stop_price,
               risk_per_share, suggested_rr_ratio, avg_daily_volume
        FROM   breakout_entries
        WHERE  scan_date = ?
        ORDER  BY pattern_grade ASC, suggested_rr_ratio DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (target_date,))
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"get_breakout_candidates_for_date({target_date}): {e}")
        return []


def get_breakout_entries_full(target_date) -> list[dict]:
    """
    Like get_breakout_candidates_for_date, but with the extra fields
    paper_trading_bot.py needs to open a position and explain why: the row id
    (for the paper_trades -> breakout_entries FK) and qualification_reasons,
    volume_ratio, pivot_price for a human-readable entry_reason.
    """
    sql = """
        SELECT id, ticker, pattern_type, pattern_grade, breakout_price, pivot_price,
               stop_price, risk_per_share, suggested_rr_ratio, avg_daily_volume,
               volume_ratio, qualification_reasons
        FROM   breakout_entries
        WHERE  scan_date = ?
        ORDER  BY pattern_grade ASC, suggested_rr_ratio DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (target_date,))
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"get_breakout_entries_full({target_date}): {e}")
        return []


def get_watchlist_candidates_for_date(target_date) -> list[dict]:
    """
    Watchlist entries for target_date that pass the grade filters (same rule as
    get_todays_watchlist), for use as a preview/fallback when no breakout_entries
    exist yet for the day (candidates only — not a confirmed Stage 5 trigger).
    """
    allowed     = list(cfg.BREAKOUT_ALLOWED_GRADES)
    htf_allowed = list(cfg.HTF_ALLOWED_GRADES)
    ph          = ",".join("?" * len(allowed))
    htf_ph      = ",".join("?" * len(htf_allowed))
    sql = f"""
        SELECT ticker, pattern_type, pattern_grade, price_at_scan AS breakout_price,
               NULL AS stop_price, NULL AS risk_per_share, NULL AS suggested_rr_ratio,
               avg_daily_volume
        FROM   watchlist_entries
        WHERE  scan_date = ?
          AND  pattern_grade IN ({ph})
          AND  (pattern_type != 'HTF' OR pattern_grade IN ({htf_ph}))
        ORDER  BY pattern_grade ASC, pct_from_pivot ASC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (target_date, *allowed, *htf_allowed))
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"get_watchlist_candidates_for_date({target_date}): {e}")
        return []


# ─── Profit Target Alerts (R36/R38 — alert-only, no live orders) ──────────────

def get_latest_breakout_entry(ticker: str, lookback_days: int = 90) -> dict | None:
    """
    Most recent breakout_entries row for a ticker within lookback_days, used as
    the entry/stop/risk reference for check_profit_targets.py's R-multiple math.

    Returns None if the ticker has no tracked breakout entry (e.g. the position
    predates this system, or wasn't sourced from an alert) — the caller should
    skip the position rather than guess at a risk level.
    """
    sql = """
        SELECT TOP 1 id, ticker, scan_date, breakout_price, stop_price, risk_per_share
        FROM breakout_entries
        WHERE ticker = ?
          AND scan_date >= DATEADD(day, -?, CAST(GETDATE() AS DATE))
          AND stop_price IS NOT NULL
          AND risk_per_share IS NOT NULL
        ORDER BY scan_date DESC, id DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (ticker, lookback_days))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id":              row[0],
            "ticker":          row[1],
            "scan_date":       row[2],
            "breakout_price":  float(row[3]) if row[3] is not None else None,
            "stop_price":      float(row[4]) if row[4] is not None else None,
            "risk_per_share":  float(row[5]) if row[5] is not None else None,
        }
    except Exception as e:
        logger.error(f"get_latest_breakout_entry({ticker}): {e}")
        return None


def profit_target_already_alerted(breakout_id: int, r_level: float) -> bool:
    """Return True if this breakout_id has already been alerted at this R-level."""
    sql = "SELECT COUNT(*) FROM profit_target_alerts WHERE breakout_id = ? AND r_level = ?"
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (breakout_id, r_level))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        logger.error(f"profit_target_already_alerted({breakout_id}, {r_level}): {e}")
        return False


def mark_profit_target_alerted(breakout_id: int, ticker: str, r_level: float, r_multiple: float) -> None:
    """Record that a profit-target alert was sent, so it isn't repeated on the next run."""
    sql = """
        INSERT INTO profit_target_alerts (breakout_id, ticker, r_level, r_multiple)
        VALUES (?, ?, ?, ?)
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (breakout_id, ticker, r_level, r_multiple))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"mark_profit_target_alerted({ticker}, {r_level}): {e}")


def get_todays_runners() -> list[dict]:
    """Return all runner entries for today, ordered by 3M momentum descending."""
    sql = """
        SELECT id, ticker, price_at_scan, pct_1m, pct_3m, pct_6m,
               prior_move_pct, prior_move_days
        FROM   runner_entries
        WHERE  scan_date = ?
        ORDER  BY pct_3m DESC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (_today_est(),))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "runner_entry_id": r[0],
                "ticker":          r[1],
                "price_at_scan":   float(r[2]) if r[2] else None,
                "pct_1m":          float(r[3]) if r[3] else None,
                "pct_3m":          float(r[4]) if r[4] else None,
                "pct_6m":          float(r[5]) if r[5] else None,
                "prior_move_pct":  float(r[6]) if r[6] else None,
                "prior_move_days": int(r[7])   if r[7] else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"get_todays_runners: {e}")
        return []


def get_pending_runner_performance(force_ticker: str | None = None) -> list[dict]:
    """
    Return runner entries missing at least some performance data (last 90 days).
    If `force_ticker` is given, returns ALL entries for that ticker instead —
    see get_pending_watchlist_performance's docstring for why.
    """
    if force_ticker:
        sql = """
            SELECT e.id, e.ticker, e.scan_date, e.price_at_scan
            FROM   runner_entries e
            WHERE  e.ticker = ?
            ORDER  BY e.scan_date DESC
        """
        params = (force_ticker,)
    else:
        sql = """
            SELECT e.id, e.ticker, e.scan_date, e.price_at_scan
            FROM   runner_entries e
            LEFT JOIN runner_performance p ON p.runner_id = e.id
            WHERE  e.scan_date >= DATEADD(day, -90, CAST(GETDATE() AS DATE))
              AND  (p.id IS NULL OR p.price_60d IS NULL)
            ORDER  BY e.scan_date DESC
        """
        params = ()
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "runner_id":   r[0],
                "ticker":      r[1],
                "scan_date":   r[2],
                "entry_price": float(r[3]) if r[3] else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"get_pending_runner_performance: {e}")
        return []


def upsert_runner_performance(runner_id: int, perf: dict) -> bool:
    """Insert or update a runner_performance row."""
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM runner_performance WHERE runner_id = ?",
            (runner_id,)
        )
        existing = cursor.fetchone()

        if existing:
            sql = """
                UPDATE runner_performance SET
                    price_1d       = COALESCE(?, price_1d),
                    price_5d       = COALESCE(?, price_5d),
                    price_10d      = COALESCE(?, price_10d),
                    price_20d      = COALESCE(?, price_20d),
                    price_60d      = COALESCE(?, price_60d),
                    pct_change_1d  = COALESCE(?, pct_change_1d),
                    pct_change_5d  = COALESCE(?, pct_change_5d),
                    pct_change_10d = COALESCE(?, pct_change_10d),
                    pct_change_20d = COALESCE(?, pct_change_20d),
                    pct_change_60d = COALESCE(?, pct_change_60d),
                    did_set_up     = COALESCE(?, did_set_up),
                    days_to_setup  = COALESCE(?, days_to_setup),
                    did_break_out  = COALESCE(?, did_break_out),
                    max_gain_pct   = COALESCE(?, max_gain_pct),
                    max_gain_date  = COALESCE(?, max_gain_date),
                    max_drawdown_pct  = COALESCE(?, max_drawdown_pct),
                    max_drawdown_date = COALESCE(?, max_drawdown_date),
                    updated_at     = GETDATE()
                WHERE runner_id = ?
            """
            cursor.execute(sql, (
                perf.get("price_1d"),  perf.get("price_5d"),
                perf.get("price_10d"), perf.get("price_20d"), perf.get("price_60d"),
                perf.get("pct_change_1d"),  perf.get("pct_change_5d"),
                perf.get("pct_change_10d"), perf.get("pct_change_20d"),
                perf.get("pct_change_60d"),
                1 if perf.get("did_set_up")    else None,
                perf.get("days_to_setup"),
                1 if perf.get("did_break_out") else None,
                perf.get("max_gain_pct"),
                perf.get("max_gain_date"),
                perf.get("max_drawdown_pct"),
                perf.get("max_drawdown_date"),
                runner_id,
            ))
        else:
            sql = """
                INSERT INTO runner_performance (
                    runner_id, ticker, scan_date,
                    price_1d, price_5d, price_10d, price_20d, price_60d,
                    pct_change_1d, pct_change_5d, pct_change_10d, pct_change_20d, pct_change_60d,
                    did_set_up, days_to_setup, did_break_out, max_gain_pct, max_gain_date,
                    max_drawdown_pct, max_drawdown_date
                ) VALUES (?,?,?,  ?,?,?,?,?,  ?,?,?,?,?,  ?,?,?,?,?,  ?,?)
            """
            cursor.execute(sql, (
                runner_id, perf.get("ticker"), perf.get("scan_date"),
                perf.get("price_1d"),  perf.get("price_5d"),
                perf.get("price_10d"), perf.get("price_20d"), perf.get("price_60d"),
                perf.get("pct_change_1d"),  perf.get("pct_change_5d"),
                perf.get("pct_change_10d"), perf.get("pct_change_20d"),
                perf.get("pct_change_60d"),
                1 if perf.get("did_set_up")    else 0,
                perf.get("days_to_setup"),
                1 if perf.get("did_break_out") else 0,
                perf.get("max_gain_pct"),
                perf.get("max_gain_date"),
                perf.get("max_drawdown_pct"),
                perf.get("max_drawdown_date"),
            ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"upsert_runner_performance({runner_id}): {e}")
        return False

# ─── Paper Trading (paper_trading_bot.py — simulated portfolio, no real orders) ─

def insert_paper_trade(data: dict) -> int | None:
    """
    Insert a new paper_trades lot (a simulated BUY). Returns the new row's id.

    Expected keys: ticker, shares, entry_price, entry_date, entry_reason,
    pattern_type, pattern_grade, stop_price, risk_per_share, breakout_entry_id.
    remaining_shares and initial_stop_price default to shares/stop_price.
    """
    sql = """
        INSERT INTO paper_trades (
            ticker, shares, remaining_shares, entry_price, entry_date,
            entry_reason, pattern_type, pattern_grade, stop_price,
            initial_stop_price, risk_per_share, breakout_entry_id
        )
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (
            data["ticker"], data["shares"], data["shares"],
            data["entry_price"], data["entry_date"], data.get("entry_reason"),
            data.get("pattern_type"), data.get("pattern_grade"),
            data["stop_price"], data["stop_price"], data["risk_per_share"],
            data.get("breakout_entry_id"),
        ))
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"insert_paper_trade({data.get('ticker')}): {e}")
        return None


def get_open_paper_trades() -> list[dict]:
    """Return all currently open paper_trades rows."""
    sql = """
        SELECT id, ticker, shares, remaining_shares, entry_price, entry_date,
               entry_reason, pattern_type, pattern_grade, stop_price,
               initial_stop_price, risk_per_share, hit_2r, hit_3r, breakout_entry_id
        FROM paper_trades
        WHERE status = 'open'
        ORDER BY entry_date ASC, id ASC
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"get_open_paper_trades: {e}")
        return []


def update_paper_trade_stop(paper_trade_id: int, new_stop: float) -> bool:
    """Raise (never the caller's job to lower) a paper_trades row's current stop."""
    sql = "UPDATE paper_trades SET stop_price = ? WHERE id = ?"
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (new_stop, paper_trade_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"update_paper_trade_stop({paper_trade_id}): {e}")
        return False


def record_paper_sale(paper_trade_id: int, ticker: str, shares_sold: int,
                       sale_price: float, sale_date, sale_reason: str,
                       r_multiple: float | None, realized_pnl: float | None,
                       mark_2r: bool = False, mark_3r: bool = False) -> bool:
    """
    Record a SELL against a paper_trades lot, decrement remaining_shares, and
    close the lot (status='closed') if nothing is left. Optionally flips the
    hit_2r/hit_3r flags so a level isn't re-triggered on a later run.
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO paper_trade_sales (
                paper_trade_id, ticker, shares_sold, sale_price, sale_date,
                sale_reason, r_multiple, realized_pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (paper_trade_id, ticker, shares_sold, sale_price, sale_date,
             sale_reason, r_multiple, realized_pnl),
        )

        set_clauses = ["remaining_shares = remaining_shares - ?"]
        params = [shares_sold]
        if mark_2r:
            set_clauses.append("hit_2r = 1")
        if mark_3r:
            set_clauses.append("hit_3r = 1")
        cursor.execute(
            f"UPDATE paper_trades SET {', '.join(set_clauses)} WHERE id = ?",
            (*params, paper_trade_id),
        )
        cursor.execute(
            "UPDATE paper_trades SET status = 'closed' WHERE id = ? AND remaining_shares <= 0",
            (paper_trade_id,),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"record_paper_sale({ticker}, trade_id={paper_trade_id}): {e}")
        return False


def get_paper_trade_history(status: str | None = None) -> list[dict]:
    """All paper_trades rows (optionally filtered by status), most recent first."""
    sql = """
        SELECT id, ticker, shares, remaining_shares, entry_price, entry_date,
               entry_reason, pattern_type, pattern_grade, stop_price,
               initial_stop_price, risk_per_share, hit_2r, hit_3r, status
        FROM paper_trades
    """
    params = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY entry_date DESC, id DESC"
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"get_paper_trade_history: {e}")
        return []


def get_paper_trade_sales(paper_trade_id: int | None = None) -> list[dict]:
    """All paper_trade_sales rows, optionally filtered to one lot, most recent first."""
    sql = """
        SELECT id, paper_trade_id, ticker, shares_sold, sale_price, sale_date,
               sale_reason, r_multiple, realized_pnl
        FROM paper_trade_sales
    """
    params = ()
    if paper_trade_id is not None:
        sql += " WHERE paper_trade_id = ?"
        params = (paper_trade_id,)
    sql += " ORDER BY sale_date DESC, id DESC"
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"get_paper_trade_sales: {e}")
        return []


# ─── Performance Tracking ──────────────────────────────────────────────────────

def get_pending_watchlist_performance(force_ticker: str | None = None) -> list[dict]:
    """
    Return watchlist entries that are missing at least some performance data.
    Looks back up to 90 days.

    If `force_ticker` is given, instead returns ALL entries for that ticker
    (any date, regardless of whether performance data already looks complete)
    — used to force a reprocess, e.g. to repair rows computed before the
    2026-07-08 split-rebase fix. Otherwise-complete rows never re-enter the
    normal "pending" set, so this is the only way to correct them.
    """
    if force_ticker:
        sql = """
            SELECT e.id, e.ticker, e.scan_date, e.pivot_price, e.price_at_scan,
                   NULL, NULL, NULL, NULL, NULL
            FROM watchlist_entries e
            WHERE e.ticker = ?
            ORDER BY e.scan_date DESC
        """
        params = (force_ticker,)
    else:
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
        params = ()
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
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


def get_pending_breakout_performance(force_ticker: str | None = None) -> list[dict]:
    """
    Return breakout entries missing at least some performance data.
    If `force_ticker` is given, returns ALL entries for that ticker instead —
    see get_pending_watchlist_performance's docstring for why.
    """
    if force_ticker:
        sql = """
            SELECT e.id, e.ticker, e.scan_date, e.breakout_price, e.stop_price,
                   e.pivot_price, NULL, NULL, NULL, NULL, NULL
            FROM breakout_entries e
            WHERE e.ticker = ?
            ORDER BY e.scan_date DESC
        """
        params = (force_ticker,)
    else:
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
        params = ()
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
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
                    max_drawdown_pct  = COALESCE(?, max_drawdown_pct),
                    max_drawdown_date = COALESCE(?, max_drawdown_date),
                    updated_at      = GETDATE()
                WHERE watchlist_id = ?
            """
        else:
            sql = """
                INSERT INTO watchlist_performance (
                    watchlist_id, ticker, scan_date,
                    price_1d, price_3d, price_5d, price_10d, price_20d, price_60d,
                    pct_change_1d, pct_change_5d, pct_change_10d, pct_change_20d, pct_change_60d,
                    did_break_out, max_gain_pct, max_gain_date,
                    max_drawdown_pct, max_drawdown_date
                ) VALUES (?, ?, ?,  ?,?,?,?,?,?,  ?,?,?,?,?,  ?,?,?,  ?,?)
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
                perf.get("max_drawdown_pct"), perf.get("max_drawdown_date"),
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
                perf.get("max_drawdown_pct"), perf.get("max_drawdown_date"),
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
                    max_drawdown_pct  = COALESCE(?, max_drawdown_pct),
                    max_drawdown_date = COALESCE(?, max_drawdown_date),
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
                perf.get("max_drawdown_pct"),
                perf.get("max_drawdown_date"),
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
                    max_drawdown_pct, max_drawdown_date, was_failed_breakout
                ) VALUES (?,?,?,?,?,  ?,?,?,?,?,?,  ?,?,?,?,?,  ?,?,?,?,?,  ?,?,?)
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
                perf.get("max_drawdown_pct"),
                perf.get("max_drawdown_date"),
                1 if perf.get("was_failed_breakout") else 0,
            ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"upsert_breakout_performance({breakout_id}): {e}")
        return False
