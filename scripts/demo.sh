#!/usr/bin/env bash
set -e

echo "Submitting sleep job..."
curl -s -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"type":"sleep","payload":{"duration_ms":1200},"max_attempts":5}' | jq .

echo ""
echo "Submitting retry job (fail twice then succeed)..."
curl -s -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"type":"fail_n_times","payload":{"failures_before_success":2},"max_attempts":5}' | jq .

echo ""
echo "Submitting dead-letter job (will die after 3 attempts)..."
curl -s -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"type":"fail_n_times","payload":{"failures_before_success":999},"max_attempts":3}' | jq .

echo ""
echo "Open dashboard: http://127.0.0.1:8000/"
