#!/usr/bin/env bash
# cron_setup.sh — Install all cron jobs for the stock scanning system.
#
# Jobs installed:
#   1. watchlist_scanner.py    — 8:00 AM EST (13:00 UTC), Mon-Fri
#   2. breakout_scanner.py     — every 30 min during market hours, Mon-Fri
#   3. performance_tracker.py  — 4:30 PM EST (21:30 UTC), Mon-Fri
#
# Usage:
#   chmod +x cron_setup.sh
#   ./cron_setup.sh

set -e

echo ""
echo "========================================"
echo "  Stock Scanner — Cron Job Installer"
echo "========================================"
echo ""

# ─── Determine script directory ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Script directory detected: $SCRIPT_DIR"
echo ""

read -p "Use this directory? [Y/n]: " confirm
if [[ "$confirm" =~ ^[Nn] ]]; then
    read -p "Enter the full path to the scan/ directory: " SCRIPT_DIR
    if [ ! -d "$SCRIPT_DIR" ]; then
        echo "ERROR: Directory not found: $SCRIPT_DIR"
        exit 1
    fi
fi

# ─── Python interpreter ────────────────────────────────────────────────────────
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Please install Python 3.9+."
    exit 1
fi
echo "Python interpreter: $PYTHON"

# ─── Make scripts executable ──────────────────────────────────────────────────
chmod +x "$SCRIPT_DIR/watchlist_scanner.py"
chmod +x "$SCRIPT_DIR/breakout_scanner.py"
chmod +x "$SCRIPT_DIR/performance_tracker.py"
echo "Made scripts executable."

# ─── Log directory ────────────────────────────────────────────────────────────
LOG_DIR="/var/log/stock-scanner"
if [ -d "$LOG_DIR" ]; then
    echo "Log directory: $LOG_DIR"
else
    echo ""
    echo "Log directory $LOG_DIR does not exist."
    read -p "Create it? (requires sudo) [Y/n]: " mklog
    if [[ ! "$mklog" =~ ^[Nn] ]]; then
        sudo mkdir -p "$LOG_DIR"
        sudo chmod 777 "$LOG_DIR"
        echo "Created $LOG_DIR"
    else
        LOG_DIR="$SCRIPT_DIR/logs"
        mkdir -p "$LOG_DIR"
        echo "Using local log dir: $LOG_DIR"
    fi
fi

# ─── Build cron entries ────────────────────────────────────────────────────────
# All times in UTC. Market hours EST = UTC-4 (EDT) / UTC-5 (EST).
# Using EDT (UTC-4) as base — adjust to UTC-5 in winter if needed.

WATCHLIST_CRON="0 13 * * 1-5 cd $SCRIPT_DIR && $PYTHON $SCRIPT_DIR/watchlist_scanner.py >> $LOG_DIR/watchlist.log 2>&1"

# Breakout scanner: every 30 min from 14:30 to 21:00 UTC (9:30 AM - 4:00 PM ET)
# Two cron rules: :00 and :30 past each hour, 14-20, plus final at 21:00
BREAKOUT_CRON_1="0,30 14-20 * * 1-5 cd $SCRIPT_DIR && $PYTHON $SCRIPT_DIR/breakout_scanner.py >> $LOG_DIR/breakout.log 2>&1"
BREAKOUT_CRON_2="0 21 * * 1-5 cd $SCRIPT_DIR && $PYTHON $SCRIPT_DIR/breakout_scanner.py >> $LOG_DIR/breakout.log 2>&1"

PERF_CRON="30 21 * * 1-5 cd $SCRIPT_DIR && $PYTHON $SCRIPT_DIR/performance_tracker.py >> $LOG_DIR/performance.log 2>&1"

# ─── Install cron jobs ────────────────────────────────────────────────────────
echo ""
echo "Installing the following cron jobs:"
echo ""
echo "  [1] Watchlist scanner (8:00 AM EST / 13:00 UTC, Mon-Fri):"
echo "      $WATCHLIST_CRON"
echo ""
echo "  [2] Breakout scanner (every 30 min, 9:30 AM-4:00 PM EST, Mon-Fri):"
echo "      $BREAKOUT_CRON_1"
echo "      $BREAKOUT_CRON_2"
echo ""
echo "  [3] Performance tracker (4:30 PM EST / 21:30 UTC, Mon-Fri):"
echo "      $PERF_CRON"
echo ""
read -p "Confirm installation? [Y/n]: " install_confirm
if [[ "$install_confirm" =~ ^[Nn] ]]; then
    echo "Aborted."
    exit 0
fi

# Preserve existing crontab and append new jobs
(
    crontab -l 2>/dev/null | grep -v "watchlist_scanner\|breakout_scanner\|performance_tracker"
    echo ""
    echo "# ── Stock Scanner (installed by cron_setup.sh) ──────────────────────"
    echo "# Watchlist: 8:00 AM EST (13:00 UTC) weekdays"
    echo "$WATCHLIST_CRON"
    echo ""
    echo "# Breakout scanner: every 30 min during market hours (9:30 AM-4:00 PM EST)"
    echo "$BREAKOUT_CRON_1"
    echo "$BREAKOUT_CRON_2"
    echo ""
    echo "# Performance tracker: 4:30 PM EST (21:30 UTC) weekdays"
    echo "$PERF_CRON"
    echo "# ────────────────────────────────────────────────────────────────────"
) | crontab -

echo ""
echo "✅ Cron jobs installed. Current crontab:"
echo ""
crontab -l
echo ""
echo "Done. Logs will appear in: $LOG_DIR"
echo ""
echo "To test manually:"
echo "  cd $SCRIPT_DIR"
echo "  python watchlist_scanner.py --dry-run"
echo "  python breakout_scanner.py --force --dry-run"
echo "  python performance_tracker.py --dry-run"
echo ""
