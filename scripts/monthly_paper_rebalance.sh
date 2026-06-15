#!/usr/bin/env bash
# Monthly paper-trading rebalance — intended to be called by cron on the
# last trading day of each month (we approximate with the 28th).
#
# Cron entry (runs at 6:30 PM IST, after market close):
#   30 18 28 * * /Users/jeevandeepsamanta/Documents/Claude/Projects/Trading/scripts/monthly_paper_rebalance.sh

set -euo pipefail

PROJECT_DIR="/Users/jeevandeepsamanta/Documents/Claude/Projects/Trading"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/logs/paper_rebalance_$(date +%Y%m%d_%H%M%S).log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$PROJECT_DIR/logs"

cd "$PROJECT_DIR"

echo "=== Paper rebalance started at $(date) ===" | tee -a "$LOG_FILE"

# Run the paper rebalance
"$PYTHON" main.py paper -c configs/smallcap_momentum_v2.yaml 2>&1 | tee -a "$LOG_FILE"

# Push updated state to GitHub
git add data/paper/ >> "$LOG_FILE" 2>&1 || true
if git diff --cached --quiet; then
    echo "No data changes to push." >> "$LOG_FILE"
else
    git commit -m "Ascent monthly paper rebalance $(date +%Y-%m-%d)" >> "$LOG_FILE" 2>&1
    git push >> "$LOG_FILE" 2>&1
fi

echo "=== Paper rebalance finished at $(date) ===" | tee -a "$LOG_FILE"
