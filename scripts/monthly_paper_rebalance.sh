#!/usr/bin/env bash
# Monthly paper-trading rebalance — intended to be called by cron on the
# last trading day of each month (we approximate with the 28th).
#
# Cron entry (runs at 6:30 PM IST, after market close):
#   30 18 28 * * /Users/jeevandeepsamanta/Documents/Claude/Projects/Trading/scripts/monthly_paper_rebalance.sh

set -euo pipefail

PROJECT_DIR="/Users/jeevandeepsamanta/Documents/Claude/Projects/Trading"
LOG_FILE="$PROJECT_DIR/logs/paper_rebalance_$(date +%Y%m%d_%H%M%S).log"

cd "$PROJECT_DIR"

echo "=== Paper rebalance started at $(date) ===" | tee -a "$LOG_FILE"

# Run the paper rebalance
python main.py paper -c configs/smallcap_momentum_v2.yaml 2>&1 | tee -a "$LOG_FILE"

echo "=== Paper rebalance finished at $(date) ===" | tee -a "$LOG_FILE"
