# -*- coding: utf-8 -*-
"""
Larry Williams EMA Setup 9.1 & 9.2 Backtest -- SNDK
Data source: maximum-pain.com/candlestick/sndk
Period: 2026-03-30 to 2026-06-25
Exit rules: stop-loss at trigger candle low, OR 9-EMA direction flip (whichever first).
"""

import json

# SNDK OHLC data (Date, Open, High, Low, Close)
raw = [
    ("2026-03-30", 642.12, 651.00, 558.58, 572.50),
    ("2026-03-31", 588.01, 636.32, 578.42, 635.34),
    ("2026-04-01", 652.29, 710.85, 645.10, 692.73),
    ("2026-04-02", 642.09, 707.31, 641.00, 701.59),
    ("2026-04-06", 720.34, 736.00, 711.00, 724.63),
    ("2026-04-07", 715.70, 738.01, 687.68, 710.80),
    ("2026-04-08", 784.00, 807.99, 758.19, 780.90),
    ("2026-04-09", 817.08, 855.00, 805.00, 851.57),
    ("2026-04-10", 873.95, 873.95, 835.28, 851.77),
    ("2026-04-13", 867.09, 953.41, 866.95, 952.50),
    ("2026-04-14", 964.02, 965.00, 902.00, 944.46),
    ("2026-04-15", 929.86, 937.99, 873.93, 891.72),
    ("2026-04-16", 896.62, 929.50, 892.51, 919.47),
    ("2026-04-17", 920.84, 930.50, 886.00, 920.99),
    ("2026-04-20", 930.97, 951.47, 900.37, 913.02),
    ("2026-04-21", 927.85, 938.78, 899.20, 903.49),
    ("2026-04-22", 922.01, 981.06, 895.74, 979.07),
    ("2026-04-23", 948.54, 978.88, 926.11, 932.43),
    ("2026-04-24", 954.56, 1002.09, 947.00, 989.90),
    ("2026-04-27", 1019.65, 1070.66, 1008.88, 1070.20),
    ("2026-04-28", 1027.60, 1054.22, 980.28, 1002.35),
    ("2026-04-29", 1070.60, 1103.00, 1060.00, 1064.21),
    ("2026-04-30", 1112.43, 1115.00, 1076.05, 1096.51),
    ("2026-05-01", 1059.02, 1189.24, 1048.00, 1187.00),
    ("2026-05-04", 1222.18, 1275.11, 1205.00, 1255.86),
    ("2026-05-05", 1289.01, 1418.88, 1286.13, 1406.32),
    ("2026-05-06", 1437.40, 1439.70, 1337.56, 1409.98),
    ("2026-05-07", 1379.42, 1400.99, 1292.57, 1339.96),
    ("2026-05-08", 1394.37, 1564.00, 1391.12, 1562.34),
    ("2026-05-11", 1586.25, 1600.00, 1514.47, 1547.56),
    ("2026-05-12", 1492.00, 1508.32, 1367.00, 1452.02),
    ("2026-05-13", 1512.48, 1513.57, 1404.86, 1447.23),
    ("2026-05-14", 1394.40, 1453.77, 1362.00, 1382.72),
    ("2026-05-15", 1321.00, 1426.38, 1315.75, 1407.61),
    ("2026-05-18", 1431.67, 1440.00, 1277.33, 1333.01),
    ("2026-05-19", 1289.75, 1392.86, 1278.11, 1383.29),
    ("2026-05-20", 1437.98, 1444.00, 1366.98, 1392.56),
    ("2026-05-21", 1377.47, 1546.09, 1377.47, 1542.24),
    ("2026-05-22", 1520.71, 1528.00, 1473.52, 1478.69),
    ("2026-05-26", 1535.21, 1641.74, 1520.00, 1589.55),
    ("2026-05-27", 1645.99, 1658.77, 1528.28, 1589.94),
    ("2026-05-28", 1596.31, 1697.96, 1560.18, 1641.64),
    ("2026-05-29", 1682.00, 1708.82, 1641.08, 1694.98),
    ("2026-06-01", 1731.15, 1804.00, 1686.16, 1761.43),
    ("2026-06-02", 1750.06, 1772.40, 1708.80, 1716.36),
    ("2026-06-03", 1736.00, 1861.00, 1708.88, 1831.50),
    ("2026-06-04", 1741.31, 1825.90, 1725.08, 1759.68),
    ("2026-06-05", 1678.88, 1682.00, 1514.36, 1559.32),
    ("2026-06-08", 1634.00, 1694.99, 1602.00, 1642.00),
    ("2026-06-09", 1700.50, 1803.00, 1536.00, 1646.54),
    ("2026-06-10", 1624.38, 1764.65, 1590.00, 1643.23),
    ("2026-06-11", 1672.26, 1895.00, 1665.00, 1881.51),
    ("2026-06-12", 1890.98, 2021.65, 1865.11, 1980.10),
    ("2026-06-15", 2101.12, 2119.90, 2021.11, 2107.86),
    ("2026-06-16", 2134.20, 2167.33, 1980.18, 1991.55),
    ("2026-06-17", 2074.59, 2074.59, 1938.00, 1958.80),
    ("2026-06-18", 2044.74, 2191.69, 2029.00, 2184.75),
    ("2026-06-22", 2293.31, 2354.39, 2251.28, 2273.73),
    ("2026-06-23", 2007.70, 2060.00, 1949.96, 1963.60),
    ("2026-06-24", 1987.53, 2021.50, 1861.01, 1914.46),
    ("2026-06-25", 2238.30, 2348.00, 2092.08, 2335.00),
]

dates  = [r[0] for r in raw]
opens  = [r[1] for r in raw]
highs  = [r[2] for r in raw]
lows   = [r[3] for r in raw]
closes = [r[4] for r in raw]
n = len(raw)

# ── 9-period EMA ─────────────────────────────────────────────────────────────
k = 2 / (9 + 1)
ema9 = [0.0] * n
ema9[0] = closes[0]
for i in range(1, n):
    ema9[i] = closes[i] * k + ema9[i-1] * (1 - k)

# EMA direction per bar: +1 rising, -1 falling
ema_dir = [0] * n
for i in range(1, n):
    ema_dir[i] = 1 if ema9[i] > ema9[i-1] else -1

# Print EMA table for inspection
print("EMA9 direction summary:")
prev = None
for i in range(n):
    d = ema_dir[i]
    if d != prev:
        print(f"  {dates[i]}  EMA9={ema9[i]:.2f}  dir={'UP' if d==1 else 'DOWN'}")
        prev = d
print()

# ── Trade exit simulator ──────────────────────────────────────────────────────
def exit_trade(entry_idx, entry_price, stop, direction):
    """Walk forward from entry_idx+1, exit on stop or EMA flip."""
    risk = abs(entry_price - stop)
    if risk == 0:
        return None, None, None, None, None

    for j in range(entry_idx + 1, n):
        if direction == "LONG":
            if lows[j] <= stop:
                return dates[j], stop, "STOP", j - entry_idx, j
            if ema_dir[j] == -1 and ema_dir[j-1] == 1:
                return dates[j], closes[j], "EMA_FLIP", j - entry_idx, j
        else:
            if highs[j] >= stop:
                return dates[j], stop, "STOP", j - entry_idx, j
            if ema_dir[j] == 1 and ema_dir[j-1] == -1:
                return dates[j], closes[j], "EMA_FLIP", j - entry_idx, j

    # Still open
    return dates[-1], closes[-1], "OPEN", n - 1 - entry_idx, n - 1


def make_trade(setup, direction, signal_i, entry_i, entry_price, stop):
    risk = abs(entry_price - stop)
    exit_date, exit_price, result, hold, exit_i = exit_trade(entry_i, entry_price, stop, direction)
    if exit_date is None:
        return None, None
    pnl = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
    return {
        "setup":      setup,
        "direction":  direction,
        "signal_date":dates[signal_i],
        "entry_date": dates[entry_i],
        "entry_price":round(entry_price, 2),
        "stop":       round(stop, 2),
        "risk":       round(risk, 2),
        "exit_date":  exit_date,
        "exit_price": round(exit_price, 2),
        "pnl":        round(pnl, 2),
        "r_multiple": round(pnl / risk, 2) if risk else 0,
        "result":     result,
        "hold_days":  hold,
    }, exit_i


# ── Setup 9.1: EMA Reversal ──────────────────────────────────────────────────
trades_91 = []
exit_bar = -1  # bar index when last trade exited

for i in range(2, n - 1):
    if i <= exit_bar:
        continue  # still in a trade

    # Bullish flip: EMA was falling, now rising
    if ema_dir[i] == 1 and ema_dir[i-1] == -1:
        trigger_high = highs[i]
        stop_price   = lows[i]
        for j in range(i + 1, min(i + 4, n)):
            if closes[j] > trigger_high:
                t, ei = make_trade("9.1", "LONG", i, j, closes[j], stop_price)
                if t:
                    trades_91.append(t)
                    exit_bar = ei
                break

    # Bearish flip: EMA was rising, now falling
    elif ema_dir[i] == -1 and ema_dir[i-1] == 1:
        trigger_low = lows[i]
        stop_price  = highs[i]
        for j in range(i + 1, min(i + 4, n)):
            if closes[j] < trigger_low:
                t, ei = make_trade("9.1", "SHORT", i, j, closes[j], stop_price)
                if t:
                    trades_91.append(t)
                    exit_bar = ei
                break

# ── Setup 9.2: Pullback in Uptrend ───────────────────────────────────────────
trades_92 = []
exit_bar = -1

for i in range(2, n - 1):
    if i <= exit_bar:
        continue

    # EMA trending up for at least 2 bars
    if ema_dir[i] == 1 and ema_dir[i-1] == 1:
        # Dip: close below prior candle's low
        if closes[i] < lows[i-1]:
            dip_high   = highs[i]
            stop_price = lows[i]
            for j in range(i + 1, min(i + 4, n)):
                if highs[j] > dip_high:
                    t, ei = make_trade("9.2", "LONG", i, j, dip_high, stop_price)
                    if t:
                        trades_92.append(t)
                        exit_bar = ei
                    break

# ── Combined ─────────────────────────────────────────────────────────────────
all_trades = sorted(trades_91 + trades_92, key=lambda x: x["entry_date"])

def print_results(label, trades):
    print(f"\n{'='*78}")
    print(f"  {label}")
    print(f"{'='*78}")
    if not trades:
        print("  No trades generated.")
        return

    print(f"{'#':<3} {'Setup':<6} {'Dir':<6} {'Signal':<12} {'Entry':<12} {'Exit':<12} "
          f"{'Entry$':>8} {'Stop$':>8} {'Exit$':>8} {'P&L':>8} {'R':>6} {'Days':>5} {'Result'}")
    print("-" * 112)

    for idx, t in enumerate(trades, 1):
        print(f"{idx:<3} {t['setup']:<6} {t['direction']:<6} {t['signal_date']:<12} "
              f"{t['entry_date']:<12} {t['exit_date']:<12} "
              f"{t['entry_price']:>8.2f} {t['stop']:>8.2f} {t['exit_price']:>8.2f} "
              f"{t['pnl']:>+8.2f} {t['r_multiple']:>+6.2f} {t['hold_days']:>5} {t['result']}")

    closed = [t for t in trades if t["result"] != "OPEN"]
    wins   = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    open_t = [t for t in trades if t["result"] == "OPEN"]

    if not closed:
        print("\n  No closed trades to summarize.")
        return

    win_rate   = len(wins) / len(closed) * 100
    total_pnl  = sum(t["pnl"] for t in closed)
    avg_win    = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss   = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    avg_r      = sum(t["r_multiple"] for t in closed) / len(closed)
    avg_hold   = sum(t["hold_days"] for t in closed) / len(closed)
    gross_win  = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf         = gross_win / gross_loss if gross_loss > 0 else float("inf")

    print(f"\n  Closed trades:  {len(closed)}   |   Open: {len(open_t)}")
    print(f"  Win rate:       {len(wins)}/{len(closed)} = {win_rate:.1f}%")
    print(f"  Total P&L:     ${total_pnl:>+,.2f}  per share")
    print(f"  Avg win:       ${avg_win:>+,.2f}   Avg loss: ${avg_loss:>+,.2f}")
    print(f"  Avg R-multiple: {avg_r:>+.2f}R   Profit factor: {pf:.2f}")
    print(f"  Avg hold:       {avg_hold:.1f} days")


print_results("SNDK -- Setup 9.1 (EMA Reversal Trades)", trades_91)
print_results("SNDK -- Setup 9.2 (Pullback Trades)", trades_92)
print_results("SNDK -- All Trades Combined", all_trades)

# ── Save JSON ────────────────────────────────────────────────────────────────
all_closed = [t for t in all_trades if t["result"] != "OPEN"]
all_wins   = [t for t in all_closed if t["pnl"] > 0]
all_losses = [t for t in all_closed if t["pnl"] <= 0]
gross_w    = sum(t["pnl"] for t in all_wins)
gross_l    = abs(sum(t["pnl"] for t in all_losses))

output = {
    "ticker": "SNDK",
    "period": f"{dates[0]} to {dates[-1]}",
    "trading_days": n,
    "ema_period": 9,
    "exit_rules": ["stop-loss at trigger candle low", "9-EMA direction flip"],
    "trades_91": trades_91,
    "trades_92": trades_92,
    "all_trades": all_trades,
    "summary": {
        "total_closed": len(all_closed),
        "open_positions": len([t for t in all_trades if t["result"] == "OPEN"]),
        "wins": len(all_wins),
        "losses": len(all_losses),
        "win_rate_pct": round(len(all_wins)/len(all_closed)*100, 1) if all_closed else 0,
        "total_pnl_per_share": round(sum(t["pnl"] for t in all_closed), 2),
        "avg_win": round(sum(t["pnl"] for t in all_wins)/len(all_wins), 2) if all_wins else 0,
        "avg_loss": round(sum(t["pnl"] for t in all_losses)/len(all_losses), 2) if all_losses else 0,
        "avg_r_multiple": round(sum(t["r_multiple"] for t in all_closed)/len(all_closed), 2) if all_closed else 0,
        "profit_factor": round(gross_w/gross_l, 2) if gross_l > 0 else None,
        "avg_hold_days": round(sum(t["hold_days"] for t in all_closed)/len(all_closed), 1) if all_closed else 0,
    }
}

out_path = "C:/workspaces/dshipe/stocks/LarryWilliams/sndk_backtest_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print(f"\n  Results saved to sndk_backtest_results.json")
