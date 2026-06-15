#!/usr/bin/env bash
# Daily paper-trading mark-to-market — updates equity curve without
# changing positions. Run after market close on weekdays.
#
# Cron entry (runs at 6:00 PM IST, Mon-Fri):
#   0 18 * * 1-5 /Users/jeevandeepsamanta/Documents/Claude/Projects/Trading/scripts/daily_mark.sh

set -euo pipefail

PROJECT_DIR="/Users/jeevandeepsamanta/Documents/Claude/Projects/Trading"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/logs/daily_mark_$(date +%Y%m%d).log"

# Ensure logs directory exists
mkdir -p "$PROJECT_DIR/logs"

# Set PATH so git and other tools are available in cron
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$PROJECT_DIR"

echo "=== Daily mark started at $(date) ===" >> "$LOG_FILE"

# Paper trading mark-to-market
"$PYTHON" scripts/daily_mark.py >> "$LOG_FILE" 2>&1 || echo "WARN: paper mark failed" >> "$LOG_FILE"

# Live trading mark-to-market
"$PYTHON" scripts/daily_live_mark.py >> "$LOG_FILE" 2>&1 || echo "WARN: live mark failed" >> "$LOG_FILE"

# Refresh Bedrock (V+Q) scores for dashboard
echo "Refreshing V+Q scores..." >> "$LOG_FILE"
"$PYTHON" scripts/refresh_vq_scores.py >> "$LOG_FILE" 2>&1 || echo "WARN: V+Q refresh failed" >> "$LOG_FILE"

# Push updated data to GitHub so jdquant.in stays fresh
echo "Pushing to GitHub..." >> "$LOG_FILE"
git add data/paper/ data/live/ data/vq_scores_latest.json >> "$LOG_FILE" 2>&1 || true
if git diff --cached --quiet; then
    echo "No data changes to push." >> "$LOG_FILE"
else
    git commit -m "Daily mark-to-market $(date +%Y-%m-%d)" >> "$LOG_FILE" 2>&1
    git push >> "$LOG_FILE" 2>&1
    echo "Pushed to GitHub." >> "$LOG_FILE"
fi

echo "=== Daily mark finished at $(date) ===" >> "$LOG_FILE"
