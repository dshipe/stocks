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
print(f"\n  {'Grade':<5} {'N':>4}  {'Avg5d':>7}  {'Avg10d':>7}  {'Avg20d':>7}  {'MaxGain':>8}  {'BO%':>5}")
print("  " + "─" * 56)
for g, n, a5, a10, a20, amg, bo in rows:
    a5  = f"{a5:>+.1f}%"  if a5  is not None else "    —  "
    a10 = f"{a10:>+.1f}%" if a10 is not None else "    —  "
    a20 = f"{a20:>+.1f}%" if a20 is not None else "    —  "
    amg = f"{amg:>+.1f}%" if amg is not None else "    —  "
    bo  = f"{bo:.0f}%"    if bo  is not None else " —"
    print(f"  {g:<5} {n:>4}  {a5:>8}  {a10:>8}  {a20:>8}  {amg:>9}  {bo:>5}")

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
    a5  = f"{a5:>+.1f}%"  if a5  is not None else "    —  "
    a10 = f"{a10:>+.1f}%" if a10 is not None else "    —  "
    a20 = f"{a20:>+.1f}%" if a20 is not None else "    —  "
    bo  = f"{bo:.0f}%"    if bo  is not None else " —"
    print(f"  {pt:<12} {n:>4}  {a5:>8}  {a10:>8}  {a20:>8}  {bo:>5}")

# ── Top 10 by 20d return ───────────────────────────────────────────────────────
cur.execute("""
SELECT TOP 10 e.scan_date, e.ticker, e.pattern_grade, e.pattern_type,
       p.pct_change_5d, p.pct_change_10d, p.pct_change_20d, p.max_gain_pct, p.did_break_out
FROM watchlist_entries e
JOIN watchlist_performance p ON p.watchlist_id = e.id
WHERE p.pct_change_20d IS NOT NULL
ORDER BY p.pct_change_20d DESC
""")
rows = cur.fetchall()
print(f"\n  Top 10 by 20d return")
print(f"  {'Date':<11} {'Ticker':<7} {'Gr':<3} {'Pattern':<10} {'5d':>7} {'10d':>7} {'20d':>7} {'Max':>7}  BO")
print("  " + "─" * 70)
for sd, tk, gr, pt, d5, d10, d20, mg, bo in rows:
    d5  = f"{d5:>+.1f}%"  if d5  is not None else "    —  "
    d10 = f"{d10:>+.1f}%" if d10 is not None else "    —  "
    d20 = f"{d20:>+.1f}%" if d20 is not None else "    —  "
    mg  = f"{mg:>+.1f}%"  if mg  is not None else "    —  "
    print(f"  {str(sd)[:10]:<10} {tk:<6} {gr:<3} {pt:<10} {d5:>8} {d10:>8} {d20:>8} {mg:>8}  {'✓' if bo else '✗'}")

# ── Bottom 5 ───────────────────────────────────────────────────────────────────
cur.execute("""
SELECT TOP 5 e.scan_date, e.ticker, e.pattern_grade,
       p.pct_change_5d, p.pct_change_10d, p.pct_change_20d, p.did_break_out
FROM watchlist_entries e
JOIN watchlist_performance p ON p.watchlist_id = e.id
WHERE p.pct_change_20d IS NOT NULL
ORDER BY p.pct_change_20d ASC
""")
rows = cur.fetchall()
print(f"\n  Bottom 5 by 20d return")
print("  " + "─" * 60)
for sd, tk, gr, d5, d10, d20, bo in rows:
    d5  = f"{d5:>+.1f}%"  if d5  is not None else "  —"
    d10 = f"{d10:>+.1f}%" if d10 is not None else "  —"
    d20 = f"{d20:>+.1f}%" if d20 is not None else "  —"
    print(f"  {str(sd)[:10]} {tk:<6} [{gr}]  5d:{d5}  10d:{d10}  20d:{d20}  {'✓' if bo else '✗'}")

# ── Runners ────────────────────────────────────────────────────────────────────
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
    fmt = lambda v: f"{v:>+.1f}%" if v is not None else "  —"
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

# ── Top 10 runners by 20d ─────────────────────────────────────────────────────
cur.execute("""
SELECT TOP 10 e.scan_date, e.ticker, e.pct_3m,
       p.pct_change_5d, p.pct_change_10d, p.pct_change_20d,
       p.max_gain_pct, p.did_set_up, p.did_break_out
FROM runner_entries e
JOIN runner_performance p ON p.runner_id = e.id
WHERE p.pct_change_20d IS NOT NULL
ORDER BY p.pct_change_20d DESC
""")
rows = cur.fetchall()
if rows:
    print(f"\n  Top 10 runners by 20d return")
    print(f"  {'Date':<11} {'Ticker':<7} {'3M%':>6}  {'5d':>7} {'10d':>7} {'20d':>7} {'Max':>7}  Setup  BO")
    print("  " + "─" * 72)
    for sd, tk, m3, d5, d10, d20, mg, su, bo in rows:
        m3  = f"{m3:>+.1f}%"  if m3  is not None else "   —  "
        d5  = f"{d5:>+.1f}%"  if d5  is not None else "   —  "
        d10 = f"{d10:>+.1f}%" if d10 is not None else "   —  "
        d20 = f"{d20:>+.1f}%" if d20 is not None else "   —  "
        mg  = f"{mg:>+.1f}%"  if mg  is not None else "   —  "
        print(f"  {str(sd)[:10]:<10} {tk:<6} {m3:>7}  {d5:>8} {d10:>8} {d20:>8} {mg:>8}  {'✓' if su else '✗'}      {'✓' if bo else '✗'}")

conn.close()
print()
