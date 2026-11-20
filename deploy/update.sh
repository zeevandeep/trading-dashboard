#!/usr/bin/env bash
# Pull latest main; restart the dashboard only if something changed.
set -euo pipefail
APP_DIR="/opt/jdquant"
cd "$APP_DIR"
git fetch -q origin main
OLD=$(git rev-parse HEAD); NEW=$(git rev-parse origin/main)
[ "$OLD" = "$NEW" ] && exit 0
git reset -q --hard origin/main
if git diff --name-only "$OLD" "$NEW" | grep -q '^requirements-dashboard.txt$'; then
  .venv/bin/pip install -q -r requirements-dashboard.txt
fi
systemctl restart jdquant-dashboard
echo "updated $OLD -> $NEW"
