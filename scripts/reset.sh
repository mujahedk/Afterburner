#!/usr/bin/env bash
# Clear all jobs from the database.
# Pass --seed to immediately re-seed after clearing.
#
# Usage:
#   bash scripts/reset.sh          # clear only
#   bash scripts/reset.sh --seed   # clear then re-seed

set -e

API_URL="${API_URL:-http://localhost:8000}"

# ── Health check ──────────────────────────────────────────────────────────────
if ! curl -sf "$API_URL/health" > /dev/null 2>&1; then
  echo "Error: API not reachable at $API_URL"
  echo "Start the stack first:  make up"
  exit 1
fi

curl -s -X POST "$API_URL/admin/clear-jobs" > /dev/null
echo "All jobs cleared."

if [[ "$1" == "--seed" ]]; then
  echo ""
  bash "$(dirname "$0")/seed.sh"
fi
