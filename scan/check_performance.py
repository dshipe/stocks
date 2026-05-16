#!/usr/bin/env python3
"""
check_performance.py — Quick performance report for watchlist and runner entries.

Run from the scan/ directory:
    python check_performance.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pyodbc
import config as cfg

conn = pyodbc.connect(cfg.DB_CONNECTION_STRING, timeout=15)
cur  = conn.cursor()


# ── Watchlist: coverage ────────────────────────────────────────────────────────
cur.execute("""
SELECT COUNT(*) AS total,
       SUM(CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END)           AS has_perf,
       SUM(CASE WHEN p.pct_change_5d  IS NOT NULL THEN 1 ELSE 0 END) AS has_5d,
       SUM(CASE WHEN p.pct_change_10d IS NOT NULL THEN 1 ELSE 0 END) AS has_10d,
       SUM(CASE WHEN p.pct_change_20d IS NOT NULL THEN 1 ELSE 0 END) AS has_20d,
       MIN(e.scan_date) AS earliest, MAX(e.scan_date) AS latest
FROM watchlist_entries e
LEFT JOIN watchlist_performance p ON p.watchlist_id = e.id
""")
r = cur.fetchone()
print("\n=== WATCHLIST ===")
print(f"  Entries          : {r[0]}  ({r[5]} → {r[6]})")
print(f"  Has perf row     : {r[1]}  |  5d: {r[2]}  10d: {r[3]}  20d: {r[4]}")

# ── By grade ───────────────────────────────────────────────────────────────────
cur.execute("""
SELECT e.pattern_grade, COUNT(*) AS n,
       AVG(p.pct_change_5d)  AS a5,
       AVG(p.pct_change_10d) AS a10,
       AVG(p.pct_change_20d) AS a20,
       AVG(p.max_gain_pct)   AS amg,
       SUM(CASE WHEN p.did_break_out=1 THEN 1 ELSE 0 END)*100.0/COUNT(*) AS bo_pct
FROM watchlist_entries e
JOIN watchlist_performance p ON p.watchlist_id = e.id
WHERE p.pct_change_5d IS NOT NULL
GROUP BY e.pattern_grade ORDER BY e.pattern_grade
""")
rows = cur.fetchall()
fmt = lambda v: f"{v:>+.1f}%" if v is not None else "    —  "
print(f"\n  {'Grade':<5} {'N':>4}  {'Avg5d':>7}  {'Avg10d':>7}  {'Avg20d':>7}  {'MaxGain':>8}  {'BO%':>5}")
print("  " + "─" * 56)
for g, n, a5, a10, a20, amg, bo in rows:
    bo = f"{bo:.0f}%" if bo is not None else "—"
    print(f"  {g:<5} {n:>4}  {fmt(a5):>8}  {fmt(a10):>8}  {fmt(a20):>8}  {fmt(amg):>9}  {bo:>5}")

# ── By pattern ─────────────────────────────────────────────────────────────────
cur.execute("""
SELECT e.pattern_type, COUNT(*) AS n,
       AVG(p.pct_change_5d)  AS a5,
       AVG(p.pct_change_10d) AS a10,
       AVG(p.pct_change_20d) AS a20,
       SUM(CASE WHEN p.did_break_out=1 THEN 1 ELSE 0 END)*100.0/COUNT(*) AS bo_pct
FROM watchlist_entries e
JOIN watchlist_performance p ON p.watchlist_id = e.id
WHERE p.pct_change_5d IS NOT NULL
GROUP BY e.pattern_type ORDER BY AVG(p.pct_change_10d) DESC
""")
rows = cur.fetchall()
print(f"\n  {'Pattern':<12} {'N':>4}  {'Avg5d':>7}  {'Avg10d':>7}  {'Avg20d':>7}  {'BO%':>5}")
print("  " + "─" * 52)
for pt, n, a5, a10, a20, bo in rows:
    bo = f"{bo:.0f}%" if bo is not None else "—"
    print(f"  {pt:<12} {n:>4}  {fmt(a5):>8}  {fmt(a10):>8}  {fmt(a20):>8}  {bo:>5}")

# ── All watchlist stocks with 5d+ data, sorted by best return ─────────────────
cur.execute("""
SELECT e.scan_date, e.ticker, e.pattern_grade, e.pattern_type,
       p.pct_change_5d, p.pct_change_10d, p.pct_change_20d,
       p.max_gain_pct, p.did_break_out
FROM watchlist_entries e
JOIN watchlist_performance p ON p.watchlist_id = e.id
WHERE p.pct_change_5d IS NOT NULL
ORDER BY COALESCE(p.pct_change_10d, p.pct_change_5d) DESC
""")
rows = cur.fetchall()
print(f"\n  All watchlist stocks with return data ({len(rows)} entries, sorted by best return)")
print(f"  {'Date':<11} {'Ticker':<7} {'Gr':<3} {'Pattern':<10} {'5d':>7} {'10d':>7} {'20d':>7} {'Max':>7}  BO")
print("  " + "─" * 72)
for sd, tk, gr, pt, d5, d10, d20, mg, bo in rows:
    print(
        f"  {str(sd)[:10]:<10} {tk:<6} {gr:<3} {pt:<10} "
        f"{fmt(d5):>8} {fmt(d10):>8} {fmt(d20):>8} {fmt(mg):>8}  {'✓' if bo else '✗'}"
    )

# ── Runner summary ─────────────────────────────────────────────────────────────
cur.execute("""
SELECT COUNT(*) AS total,
       SUM(CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END)             AS has_perf,
       SUM(CASE WHEN p.pct_change_5d  IS NOT NULL THEN 1 ELSE 0 END) AS has_5d,
       SUM(CASE WHEN p.pct_change_20d IS NOT NULL THEN 1 ELSE 0 END) AS has_20d,
       MIN(e.scan_date) AS earliest, MAX(e.scan_date) AS latest
FROM runner_entries e
LEFT JOIN runner_performance p ON p.runner_id = e.id
""")
r = cur.fetchone()
print(f"\n=== RUNNERS ===")
print(f"  Entries          : {r[0]}  ({r[4]} → {r[5]})")
print(f"  Has perf row     : {r[1]}  |  5d: {r[2]}  20d: {r[3]}")

cur.execute("""
SELECT COUNT(*) AS n,
       AVG(p.pct_change_5d)  AS a5,
       AVG(p.pct_change_10d) AS a10,
       AVG(p.pct_change_20d) AS a20,
       AVG(p.max_gain_pct)   AS amg,
       SUM(CASE WHEN p.did_set_up=1    THEN 1 ELSE 0 END)*100.0/COUNT(*) AS setup_pct,
       SUM(CASE WHEN p.did_break_out=1 THEN 1 ELSE 0 END)*100.0/COUNT(*) AS bo_pct,
       AVG(CAST(p.days_to_setup AS FLOAT)) AS avg_dts
FROM runner_entries e
JOIN runner_performance p ON p.runner_id = e.id
WHERE p.pct_change_5d IS NOT NULL
""")
r = cur.fetchone()
if r and r[0]:
    n, a5, a10, a20, amg, sp, bp, dts = r
    print(f"\n  Entries w/ 5d data : {n}")
    print(f"  Avg 5d return      : {fmt(a5)}")
    print(f"  Avg 10d return     : {fmt(a10)}")
    print(f"  Avg 20d return     : {fmt(a20)}")
    print(f"  Avg max gain (20d) : {fmt(amg)}")
    print(f"  % eventually set up: {sp:.0f}%" if sp is not None else "  % eventually set up: —")
    print(f"  % broke out        : {bp:.0f}%" if bp is not None else "  % broke out        : —")
    if dts:
        print(f"  Avg days to setup  : {dts:.0f}d")
else:
    print("  No runner performance data with 5d returns yet.")

# ── All runner stocks with 5d data, sorted by best return ─────────────────────
cur.execute("""
SELECT e.scan_date, e.ticker, e.pct_3m,
       p.pct_change_5d, p.pct_change_10d, p.pct_change_20d,
       p.max_gain_pct, p.did_set_up, p.did_break_out
FROM runner_entries e
JOIN runner_performance p ON p.runner_id = e.id
WHERE p.pct_change_5d IS NOT NULL
ORDER BY COALESCE(p.pct_change_10d, p.pct_change_5d) DESC
""")
rows = cur.fetchall()
if rows:
    print(f"\n  All runners with return data ({len(rows)} entries, sorted by best return)")
    print(f"  {'Date':<11} {'Ticker':<7} {'3M%':>6}  {'5d':>7} {'10d':>7} {'20d':>7} {'Max':>7}  Setup  BO")
    print("  " + "─" * 74)
    for sd, tk, m3, d5, d10, d20, mg, su, bo in rows:
        print(
            f"  {str(sd)[:10]:<10} {tk:<6} {fmt(m3):>7}  "
            f"{fmt(d5):>8} {fmt(d10):>8} {fmt(d20):>8} {fmt(mg):>8}  "
            f"{'✓' if su else '✗'}      {'✓' if bo else '✗'}"
        )

# ── Outlier investigation (returns beyond ±50% — likely data artifacts) ───────
cur.execute("""
SELECT 'watchlist' AS src, e.scan_date, e.ticker, e.pattern_grade,
       p.pct_change_5d, p.pct_change_10d,
       e.price_at_scan,
       p.price_1d, p.price_5d, p.price_10d
FROM watchlist_entries e
JOIN watchlist_performance p ON p.watchlist_id = e.id
WHERE ABS(COALESCE(p.pct_change_10d, p.pct_change_5d)) >= 50
UNION ALL
SELECT 'runner' AS src, e.scan_date, e.ticker, NULL,
       p.pct_change_5d, p.pct_change_10d,
       e.price_at_scan,
       p.price_1d, p.price_5d, p.price_10d
FROM runner_entries e
JOIN runner_performance p ON p.runner_id = e.id
WHERE ABS(COALESCE(p.pct_change_10d, p.pct_change_5d)) >= 50
ORDER BY ABS(COALESCE(pct_change_10d, pct_change_5d)) DESC
""")
rows = cur.fetchall()
if rows:
    print(f"\n=== OUTLIERS (returns >= +/-50% -- verify these are not data errors) ===")
    print(f"  {'Src':<10} {'Date':<11} {'Ticker':<7} {'Gr':<3} {'Entry':>8} {'1d':>8} {'5d':>8} {'5d%':>7} {'10d':>8} {'10d%':>7}")
    print("  " + "-" * 80)
    seen = set()
    for src, sd, tk, gr, d5, d10, entry, p1, p5, p10 in rows:
        key = (src, str(sd), tk)
        if key in seen:
            continue
        seen.add(key)
        gr   = gr or "-"
        print(
            f"  {src:<10} {str(sd)[:10]:<10} {tk:<6} {gr:<3} "
            f"{fmt(entry):>9} {fmt(p1):>9} {fmt(p5):>9} {fmt(d5):>8} "
            f"{fmt(p10):>9} {fmt(d10):>8}"
        )
    print(f"\n  Action: for each ticker above, verify the price data is correct.")
    print(f"  Common causes: reverse splits, spinoffs, special dividends, ticker reuse.")

conn.close()
print()
