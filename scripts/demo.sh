#!/usr/bin/env bash
# Guided demo scenario for Afterburner.
# Submits one job of each key type with pauses so you can narrate
# while watching the dashboard update live.
#
# Usage:  bash scripts/demo.sh
#    or:  make demo

API_URL="${API_URL:-http://localhost:8000}"

# ── Helpers ───────────────────────────────────────────────────────────────────

# Pretty-print JSON if jq is available; otherwise just echo the raw response.
pretty() {
  if command -v jq > /dev/null 2>&1; then
    echo "$1" | jq .
  else
    echo "$1"
  fi
}

post_job() {
  pretty "$(curl -s -X POST "$API_URL/api/jobs" \
    -H "Content-Type: application/json" \
    -d "$1")"
}

divider() {
  echo ""
  echo "──────────────────────────────────────────"
  echo "  $1"
  echo "──────────────────────────────────────────"
  echo ""
}

pause() {
  echo ""
  echo "  [ Watch the dashboard, then press Enter to continue... ]"
  read -r
}

# ── Health check ──────────────────────────────────────────────────────────────

if ! curl -sf "$API_URL/health" > /dev/null 2>&1; then
  echo ""
  echo "Error: API not reachable at $API_URL"
  echo "Start the stack first:  make up"
  echo ""
  exit 1
fi

echo ""
echo "Afterburner — live demo"
echo "Dashboard: $API_URL"
echo ""
echo "Open the dashboard in your browser before continuing."
pause

# ── Step 1: Successful job ────────────────────────────────────────────────────

divider "Step 1 — Successful job (sleep)"
echo "  Submitting a sleep job (1.5 seconds)..."
echo "  SAY: 'A job is just a row in Postgres. The worker claims it with"
echo "        SELECT FOR UPDATE SKIP LOCKED, runs it, and writes the result back.'"
echo ""
post_job '{"type":"sleep","payload":{"duration_ms":1500},"max_attempts":5}'
pause

# ── Step 2: Retries with exponential backoff ──────────────────────────────────

divider "Step 2 — Retries with exponential backoff"
echo "  Submitting a job that fails twice, then succeeds..."
echo "  SAY: 'Each failure increments attempts and reschedules run_at"
echo "        by 2^attempts seconds — that is exponential backoff.'"
echo ""
post_job '{"type":"fail_n_times","payload":{"failures_before_success":2},"max_attempts":5}'
echo ""
echo "  Watch: queued → running → queued (retry) → running → queued (retry) → running → succeeded"
echo "  The two retries take about 2s + 4s = 6 seconds total."
pause

# ── Step 3: Dead-letter ───────────────────────────────────────────────────────

divider "Step 3 — Dead-letter (exhausted attempts)"
echo "  Submitting a job that will never succeed (max_attempts=3)..."
echo "  SAY: 'Once attempts >= max_attempts, status becomes dead."
echo "        Dead jobs stay visible, retain their last_error, and are never retried.'"
echo ""
post_job '{"type":"fail_n_times","payload":{"failures_before_success":999},"max_attempts":3}'
echo ""
echo "  Watch: the status pill turns red (dead) after 3 attempts (~6 seconds)."
pause

# ── Done ──────────────────────────────────────────────────────────────────────

divider "Demo complete"
echo "  Dashboard:  $API_URL"
echo "  Reset:      make reset"
echo "  Simulate:   make sim   (runs 110 jobs across 4 failure scenarios)"
echo ""
