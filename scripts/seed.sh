#!/usr/bin/env bash
# Seed the dashboard with a representative mix of demo jobs.
# No dependencies beyond curl and bash.

set -e

API_URL="${API_URL:-http://localhost:8000}"

# ── Health check ──────────────────────────────────────────────────────────────
if ! curl -sf "$API_URL/health" > /dev/null 2>&1; then
  echo "Error: API not reachable at $API_URL"
  echo "Start the stack first:  make up"
  exit 1
fi

post_job() {
  curl -s -X POST "$API_URL/api/jobs" \
    -H "Content-Type: application/json" \
    -d "$1" > /dev/null
}

echo "Seeding demo jobs..."
echo ""

# ── Sleep jobs (will succeed immediately) ─────────────────────────────────────
echo "  Submitting 3 sleep jobs..."
post_job '{"type":"sleep","payload":{"duration_ms":800},"max_attempts":3}'
post_job '{"type":"sleep","payload":{"duration_ms":1200},"max_attempts":3}'
post_job '{"type":"sleep","payload":{"duration_ms":600},"max_attempts":3}'

# ── Retry job (fails twice, then succeeds) ────────────────────────────────────
echo "  Submitting 1 retry job (will succeed after 2 retries)..."
post_job '{"type":"fail_n_times","payload":{"failures_before_success":2},"max_attempts":5}'

# ── Dead-letter job (exhausts all attempts) ───────────────────────────────────
echo "  Submitting 1 dead-letter job (will fail 3 times and die)..."
post_job '{"type":"fail_n_times","payload":{"failures_before_success":999},"max_attempts":3}'

echo ""
echo "Done. 5 jobs submitted."
echo ""
echo "Open the dashboard:  $API_URL"
echo ""
echo "Wait ~15 seconds to watch all jobs reach their terminal state."
echo "  - The 3 sleep jobs will turn  succeeded  quickly."
echo "  - The retry job will cycle    queued → running  twice before succeeding."
echo "  - The dead-letter job will cycle and then turn  dead  (red pill)."
