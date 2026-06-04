#!/usr/bin/env bash
# Daily paper-trading mark-to-market — updates equity curve without
# changing positions. Run after market close on weekdays.
#
# Cron entry (runs at 6:00 PM IST, Mon-Fri):
#   0 18 * * 1-5 /Users/jeevandeepsamanta/Documents/Claude/Projects/Trading/scripts/daily_mark.sh

set -euo pipefail

PROJECT_DIR="/Users/jeevandeepsamanta/Documents/Claude/Projects/Trading"
LOG_FILE="$PROJECT_DIR/logs/daily_mark_$(date +%Y%m%d).log"

cd "$PROJECT_DIR"

echo "=== Daily mark started at $(date) ===" >> "$LOG_FILE"

.venv/bin/python scripts/daily_mark.py 2>&1 >> "$LOG_FILE"

echo "=== Daily mark finished at $(date) ===" >> "$LOG_FILE"
