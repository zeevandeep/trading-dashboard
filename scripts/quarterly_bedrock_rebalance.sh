#!/usr/bin/env bash
# Quarterly paper-trading rebalance for Bedrock (Value + Quality).
# Runs on the 28th of March, June, September, December at 7:00 PM IST.
#
# Cron entry:
#   0 19 28 3,6,9,12 * /Users/jeevandeepsamanta/Documents/Claude/Projects/Trading/scripts/quarterly_bedrock_rebalance.sh

set -euo pipefail

PROJECT_DIR="/Users/jeevandeepsamanta/Documents/Claude/Projects/Trading"
LOG_FILE="$PROJECT_DIR/logs/bedrock_rebalance_$(date +%Y%m%d_%H%M%S).log"

cd "$PROJECT_DIR"

echo "=== Bedrock (V+Q) paper rebalance started at $(date) ===" | tee -a "$LOG_FILE"

.venv/bin/python main.py paper -c configs/value_quality_v1.yaml 2>&1 | tee -a "$LOG_FILE"

# Push updated state to GitHub
echo "Pushing to GitHub..." >> "$LOG_FILE"
git add data/paper/ 2>&1 >> "$LOG_FILE"
if git diff --cached --quiet; then
    echo "No data changes to push." >> "$LOG_FILE"
else
    git commit -m "Bedrock quarterly paper rebalance $(date +%Y-%m-%d)" 2>&1 >> "$LOG_FILE"
    git push 2>&1 >> "$LOG_FILE"
    echo "Pushed to GitHub." >> "$LOG_FILE"
fi

echo "=== Bedrock paper rebalance finished at $(date) ===" | tee -a "$LOG_FILE"
