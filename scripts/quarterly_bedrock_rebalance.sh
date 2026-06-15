#!/usr/bin/env bash
# Quarterly paper-trading rebalance for Bedrock (Value + Quality).
# Runs on the 28th of March, June, September, December at 7:00 PM IST.
#
# Cron entry:
#   0 19 28 3,6,9,12 * /Users/jeevandeepsamanta/Documents/Claude/Projects/Trading/scripts/quarterly_bedrock_rebalance.sh

set -euo pipefail

PROJECT_DIR="/Users/jeevandeepsamanta/Documents/Claude/Projects/Trading"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/logs/bedrock_rebalance_$(date +%Y%m%d_%H%M%S).log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$PROJECT_DIR/logs"

cd "$PROJECT_DIR"

echo "=== Bedrock (V+Q) paper rebalance started at $(date) ===" | tee -a "$LOG_FILE"

"$PYTHON" main.py paper -c configs/value_quality_v1.yaml 2>&1 | tee -a "$LOG_FILE"

# Push updated state to GitHub
echo "Pushing to GitHub..." >> "$LOG_FILE"
git add data/paper/ >> "$LOG_FILE" 2>&1 || true
if git diff --cached --quiet; then
    echo "No data changes to push." >> "$LOG_FILE"
else
    git commit -m "Bedrock quarterly paper rebalance $(date +%Y-%m-%d)" >> "$LOG_FILE" 2>&1
    git push >> "$LOG_FILE" 2>&1
    echo "Pushed to GitHub." >> "$LOG_FILE"
fi

echo "=== Bedrock paper rebalance finished at $(date) ===" | tee -a "$LOG_FILE"
