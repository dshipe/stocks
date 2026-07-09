# -*- coding: utf-8 -*-
"""
Larry Williams EMA Setup 9.1 & 9.2 Backtest -- NVDA
Data source: maximum-pain.com/candlestick/nvda
Period: 2026-03-30 to 2026-06-25
Exit rules: stop-loss at trigger candle low/high, OR 9-EMA direction flip (whichever first).
"""

import json

# NVDA OHLC data (Date, Open, High, Low, Close)
raw = [
    ("2026-03-30", 168.78, 169.45, 164.27, 165.17),
    ("2026-03-31", 166.97, 174.62, 166.96, 174.40),
    ("2026-04-01", 176.00, 177.37, 174.75, 175.75),
    ("2026-04-02", 172.18, 177.49, 171.37, 177.39),
    ("2026-04-06", 177.16, 177.79, 175.76, 177.64),
    ("2026-04-07", 175.73, 178.23, 173.66, 178.10),
    ("2026-04-08", 184.50, 185.26, 180.30, 182.08),
    ("2026-04-09", 181.84, 184.08, 180.62, 183.91),
    ("2026-04-10", 184.31, 190.00, 184.30, 188.63),
    ("2026-04-13", 186.03, 189.66, 185.74, 189.31),
    ("2026-04-14", 190.84, 196.51, 190.77, 196.51),
    ("2026-04-15", 196.54, 200.40, 195.74, 198.87),
    ("2026-04-16", 197.43, 199.85, 195.81, 198.35),
    ("2026-04-17", 199.90, 201.70, 199.27, 201.68),
    ("2026-04-20", 199.98, 202.17, 197.84, 202.06),
    ("2026-04-21", 202.13, 202.75, 199.00, 199.88),
    ("2026-04-22", 200.99, 202.50, 199.00, 202.50),
    ("2026-04-23", 202.46, 203.83, 197.22, 199.64),
    ("2026-04-24", 199.96, 210.95, 199.81, 208.27),
    ("2026-04-27", 209.65, 216.83, 207.38, 216.61),
    ("2026-04-28", 209.49, 214.73, 208.20, 213.17),
    ("2026-04-29", 212.70, 212.72, 207.58, 209.25),
    ("2026-04-30", 209.93, 210.30, 198.70, 199.57),
    ("2026-05-01", 201.28, 203.00, 197.12, 198.45),
    ("2026-05-04", 199.50, 201.73, 194.74, 198.48),
    ("2026-05-05", 199.30, 200.24, 196.03, 196.50),
    ("2026-05-06", 199.89, 208.27, 198.61, 207.83),
    ("2026-05-07", 208.34, 214.20, 206.50, 211.50),
    ("2026-05-08", 213.03, 217.80, 212.89, 215.20),
    ("2026-05-11", 214.04, 222.30, 213.89, 219.44),
    ("2026-05-12", 218.55, 223.75, 214.92, 220.78),
    ("2026-05-13", 224.93, 227.84, 221.57, 225.83),
    ("2026-05-14", 229.85, 236.54, 229.30, 235.74),
    ("2026-05-15", 229.76, 231.50, 224.24, 225.32),
    ("2026-05-18", 229.87, 230.00, 218.37, 222.32),
    ("2026-05-19", 219.62, 224.48, 217.91, 220.61),
    ("2026-05-20", 223.18, 226.13, 220.50, 223.47),
    ("2026-05-21", 222.29, 227.40, 217.93, 219.51),
    ("2026-05-22", 220.90, 221.01, 214.80, 215.33),
    ("2026-05-26", 216.54, 218.18, 212.00, 214.86),
    ("2026-05-27", 214.12, 214.15, 208.78, 212.60),
    ("2026-05-28", 211.28, 215.52, 211.22, 214.25),
    ("2026-05-29", 214.58, 217.86, 211.13, 211.14),
    ("2026-06-01", 215.73, 224.87, 215.70, 224.36),
    ("2026-06-02", 227.18, 232.28, 221.35, 222.82),
    ("2026-06-03", 221.72, 222.82, 214.51, 214.75),
    ("2026-06-04", 213.91, 221.60, 210.97, 218.66),
    ("2026-06-05", 214.53, 214.87, 204.33, 205.10),
    ("2026-06-08", 210.18, 210.47, 206.00, 208.64),
    ("2026-06-09", 210.62, 211.40, 199.34, 208.19),
    ("2026-06-10", 204.43, 207.22, 199.92, 200.42),
    ("2026-06-11", 201.49, 205.66, 199.54, 204.87),
    ("2026-06-12", 204.86, 207.07, 203.44, 205.19),
    ("2026-06-15", 208.92, 212.71, 208.34, 212.45),
    ("2026-06-16", 211.18, 211.49, 207.29, 207.41),
    ("2026-06-17", 208.53, 209.21, 203.08, 204.65),
    ("2026-06-18", 207.33, 211.39, 206.50, 210.69),
    ("2026-06-22", 211.44, 213.99, 207.72, 208.65),
    ("2026-06-23", 202.17, 203.77, 200.00, 200.04),
    ("2026-06-24", 200.12, 201.67, 196.58, 199.00),
    ("2026-06-25", 200.08, 200.80, 192.13, 195.74),
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

ema_dir = [0] * n
for i in range(1, n):
    ema_dir[i] = 1 if ema9[i] > ema9[i-1] else -1

# ── Print EMA direction changes ──────────────────────────────────────────────
print("EMA9 direction changes:")
prev = None
for i in range(n):
    d = ema_dir[i]
    if d != prev:
        print(f"  {dates[i]}  EMA9={ema9[i]:.2f}  dir={'UP' if d==1 else 'DOWN'}")
        prev = d
print()

# ── Exit simulator ────────────────────────────────────────────────────────────
def exit_trade(entry_idx, entry_price, stop, direction):
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
    return dates[-1], closes[-1], "OPEN", n - 1 - entry_idx, n - 1


def make_trade(setup, direction, signal_i, entry_i, entry_price, stop):
    risk = abs(entry_price - stop)
    exit_date, exit_price, result, hold, exit_i = exit_trade(entry_i, entry_price, stop, direction)
    if exit_date is None:
        return None, None
    pnl = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
    return {
        "setup":       setup,
        "direction":   direction,
        "signal_date": dates[signal_i],
        "entry_date":  dates[entry_i],
        "entry_price": round(entry_price, 2),
        "stop":        round(stop, 2),
        "risk":        round(risk, 2),
        "exit_date":   exit_date,
        "exit_price":  round(exit_price, 2),
        "pnl":         round(pnl, 2),
        "r_multiple":  round(pnl / risk, 2) if risk else 0,
        "result":      result,
        "hold_days":   hold,
    }, exit_i


# ── Setup 9.1: EMA Reversal ──────────────────────────────────────────────────
trades_91, exit_bar = [], -1
for i in range(2, n - 1):
    if i <= exit_bar:
        continue
    # Bullish flip
    if ema_dir[i] == 1 and ema_dir[i-1] == -1:
        for j in range(i + 1, min(i + 4, n)):
            if closes[j] > highs[i]:
                t, ei = make_trade("9.1", "LONG", i, j, closes[j], lows[i])
                if t:
                    trades_91.append(t)
                    exit_bar = ei
                break
    # Bearish flip
    elif ema_dir[i] == -1 and ema_dir[i-1] == 1:
        for j in range(i + 1, min(i + 4, n)):
            if closes[j] < lows[i]:
                t, ei = make_trade("9.1", "SHORT", i, j, closes[j], highs[i])
                if t:
                    trades_91.append(t)
                    exit_bar = ei
                break

# ── Setup 9.2: Pullback in Uptrend ───────────────────────────────────────────
trades_92, exit_bar = [], -1
for i in range(2, n - 1):
    if i <= exit_bar:
        continue
    if ema_dir[i] == 1 and ema_dir[i-1] == 1:
        if closes[i] < lows[i-1]:
            dip_high, stop_price = highs[i], lows[i]
            for j in range(i + 1, min(i + 4, n)):
                if highs[j] > dip_high:
                    t, ei = make_trade("9.2", "LONG", i, j, dip_high, stop_price)
                    if t:
                        trades_92.append(t)
                        exit_bar = ei
                    break

# ── Also run with 50 MA filter (longs only when close > SMA20 from site) ─────
# Site shows SMA20 starting from row 20 (4/27/26). We'll use the site's SMA20 values.
sma20_raw = {
    "2026-04-27": 190.837, "2026-04-28": 193.238, "2026-04-29": 194.980,
    "2026-04-30": 196.171, "2026-05-01": 197.224, "2026-05-04": 198.266,
    "2026-05-05": 199.186, "2026-05-06": 200.474, "2026-05-07": 201.853,
    "2026-05-08": 203.181, "2026-05-11": 204.688, "2026-05-12": 205.902,
    "2026-05-13": 207.249, "2026-05-14": 209.119, "2026-05-15": 210.301,
    "2026-05-18": 211.314, "2026-05-19": 212.351, "2026-05-20": 213.399,
    "2026-05-21": 214.393, "2026-05-22": 214.746, "2026-05-26": 214.658,
    "2026-05-27": 214.630, "2026-05-28": 214.880, "2026-05-29": 215.458,
    "2026-06-01": 216.753, "2026-06-02": 217.971, "2026-06-03": 218.883,
    "2026-06-04": 219.425, "2026-06-05": 219.105, "2026-06-08": 218.777,
    "2026-06-09": 218.214, "2026-06-10": 217.196, "2026-06-11": 216.148,
    "2026-06-12": 214.621, "2026-06-15": 213.977, "2026-06-16": 213.232,
    "2026-06-17": 212.433, "2026-06-18": 211.794, "2026-06-22": 211.252,
    "2026-06-23": 210.487, "2026-06-24": 209.694, "2026-06-25": 208.851,
}

trades_92_filtered, exit_bar = [], -1
for i in range(2, n - 1):
    if i <= exit_bar:
        continue
    sma20 = sma20_raw.get(dates[i])
    if ema_dir[i] == 1 and ema_dir[i-1] == 1:
        if closes[i] < lows[i-1]:
            dip_high, stop_price = highs[i], lows[i]
            # 50/20 MA filter: only enter if close > SMA20
            if sma20 and closes[i] > sma20:
                for j in range(i + 1, min(i + 4, n)):
                    if highs[j] > dip_high:
                        t, ei = make_trade("9.2+SMA20", "LONG", i, j, dip_high, stop_price)
                        if t:
                            trades_92_filtered.append(t)
                            exit_bar = ei
                        break

# ── Print results ─────────────────────────────────────────────────────────────
def summarize(label, trades):
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"{'='*80}")
    if not trades:
        print("  No trades generated.")
        return {}

    print(f"{'#':<3} {'Setup':<10} {'Dir':<6} {'Signal':<12} {'Entry':<12} {'Exit':<12}"
          f" {'Entry$':>7} {'Stop$':>7} {'Exit$':>7} {'P&L':>7} {'R':>6} {'Days':>5}  Result")
    print("-" * 110)
    for idx, t in enumerate(trades, 1):
        print(f"{idx:<3} {t['setup']:<10} {t['direction']:<6} {t['signal_date']:<12} "
              f"{t['entry_date']:<12} {t['exit_date']:<12}"
              f" {t['entry_price']:>7.2f} {t['stop']:>7.2f} {t['exit_price']:>7.2f} "
              f"{t['pnl']:>+7.2f} {t['r_multiple']:>+6.2f} {t['hold_days']:>5}  {t['result']}")

    closed = [t for t in trades if t["result"] != "OPEN"]
    open_t = [t for t in trades if t["result"] == "OPEN"]
    wins   = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]

    if not closed:
        print("\n  No closed trades.")
        return {}

    wr     = len(wins) / len(closed) * 100
    tpnl   = sum(t["pnl"] for t in closed)
    aw     = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    al     = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    ar     = sum(t["r_multiple"] for t in closed) / len(closed)
    ah     = sum(t["hold_days"] for t in closed) / len(closed)
    gw     = sum(t["pnl"] for t in wins)
    gl     = abs(sum(t["pnl"] for t in losses))
    pf     = gw / gl if gl > 0 else float("inf")

    print(f"\n  Closed: {len(closed)}  |  Open: {len(open_t)}  |  Winners: {len(wins)} ({wr:.1f}%)  |  Losers: {len(losses)}")
    print(f"  Total P&L:      ${tpnl:>+,.2f}/share")
    print(f"  Avg win:        ${aw:>+,.2f}   |  Avg loss: ${al:>+,.2f}")
    print(f"  Avg R:          {ar:>+.2f}R     |  Profit factor: {pf:.2f}")
    print(f"  Avg hold:       {ah:.1f} days")
    return {
        "closed": len(closed), "open": len(open_t), "wins": len(wins),
        "losses": len(losses), "win_rate_pct": round(wr, 1),
        "total_pnl": round(tpnl, 2), "avg_win": round(aw, 2),
        "avg_loss": round(al, 2), "avg_r": round(ar, 2),
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "avg_hold_days": round(ah, 1)
    }

s91  = summarize("NVDA -- Setup 9.1 (EMA Reversal)", trades_91)
s92  = summarize("NVDA -- Setup 9.2 (Pullback, no filter)", trades_92)
s92f = summarize("NVDA -- Setup 9.2 + SMA20 Filter (longs above SMA20 only)", trades_92_filtered)

# ── Save JSON ─────────────────────────────────────────────────────────────────
output = {
    "ticker": "NVDA",
    "period": f"{dates[0]} to {dates[-1]}",
    "trading_days": n,
    "ema_period": 9,
    "exit_rules": ["stop-loss at trigger candle low/high", "9-EMA direction flip"],
    "trades_91": trades_91,
    "trades_92": trades_92,
    "trades_92_sma20_filter": trades_92_filtered,
    "summary": {
        "setup_91": s91,
        "setup_92_no_filter": s92,
        "setup_92_sma20_filter": s92f,
    }
}
with open("C:/workspaces/dshipe/stocks/LarryWilliams/nvda_backtest_results.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("\n  Results saved to nvda_backtest_results.json")
