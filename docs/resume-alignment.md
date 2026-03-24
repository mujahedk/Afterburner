# Afterburner — Resume Alignment

**Target resume bullet:**
> Afterburner — Background Job Queue & Worker System | Python, FastAPI, PostgreSQL, SQLAlchemy, Docker, HTMX
> - Built a durable job queue with concurrent workers using atomic DB claims and at-least-once execution semantics
> - Implemented retries with exponential backoff + dead-lettering; validated behavior across 100+ failure simulations
> - Deployed a containerized API + worker stack with a live dashboard showing job state transitions and errors

---

## Bullet 1 — Durable job queue with concurrent workers, atomic DB claims, at-least-once semantics

### Code proof

| Claim | File | Lines |
|---|---|---|
| Jobs durably stored in Postgres | `app/models.py` | Full file — `Job` model with `status`, `run_at`, `attempts` |
| Atomic claim via `SELECT FOR UPDATE SKIP LOCKED` | `app/queue.py` | `claim_job()` |
| Lease written atomically with claim | `app/queue.py` | `claim_job()` — `locked_until = now() + interval` |
| At-least-once: expired leases reclaimable | `app/queue.py` | `claim_job()` — `locked_until < now()` in WHERE clause |
| Multiple workers safe | `docker-compose.yml` | `worker` service — can be scaled with `--scale worker=N` |

### Demo proof

1. `docker compose up --scale worker=3` — three workers each claiming different jobs
2. Submit several jobs via dashboard → watch them picked up in parallel
3. Kill a worker mid-job with `docker kill afterburner-worker` → lease expires → another worker reclaims it

### Interview explanation

> "Jobs are rows in a Postgres table. The worker uses `SELECT FOR UPDATE SKIP LOCKED` inside a transaction. `FOR UPDATE` locks the row; `SKIP LOCKED` means concurrent workers don't block each other — they skip locked rows and each get a different job. I then immediately update that row to `status=running` with a `locked_until` timestamp before committing. If the worker crashes, the lease expires and the job re-enters the available pool. That's the at-least-once guarantee — every job will run at least once, but handlers should be idempotent because a crash and re-run is possible."

---

## Bullet 2 — Retries with exponential backoff + dead-lettering, 100+ failure simulations

### Code proof

| Claim | File | Lines |
|---|---|---|
| Retry on failure | `app/queue.py` | `mark_failed()` — sets `status=queued`, schedules `run_at` |
| Exponential backoff | `app/queue.py` | `exponential_backoff_seconds()` — `min(2^attempts, 300)` |
| Dead-letter when exhausted | `app/queue.py` | `mark_failed()` — `status=dead` when `attempts >= max_attempts` |
| Failure simulation harness | `scripts/simulate_failures.py` | 110 jobs across 4 scenarios with assertions |

### Simulation scenarios (110 total jobs)

| Scenario | Count | Expected outcome |
|---|---|---|
| `sleep` — immediate success | 30 | `succeeded` |
| `fail_n_times=1`, max=5 | 20 | `succeeded` after 1 retry |
| `fail_n_times=2`, max=5 | 30 | `succeeded` after 2 retries |
| `fail_n_times=3`, max=3 | 30 | `dead` — exhausts all attempts |

Run:
```bash
docker compose up --build -d
python scripts/simulate_failures.py
```

### Demo proof

1. Submit a `fail_n_times` job with `failures_before_success=2, max_attempts=5`
2. Watch the dashboard — status cycles `queued → running → queued → running → queued → running → succeeded`
3. Observe `attempts` count increment and `last_error` populate on each failure
4. Submit with `failures_before_success=999, max_attempts=3` → watch it go `dead`

### Interview explanation

> "When a handler throws an exception, `mark_failed()` increments the attempt count. If attempts is still below `max_attempts`, it reschedules the job by setting `run_at = now() + 2^attempts seconds` and status back to `queued`. That's exponential backoff — it gives downstream systems time to recover. Once `attempts >= max_attempts`, the job moves to `dead` and stays there for inspection. I validated this behavior by writing a simulation script that submits 110 jobs across four scenarios and asserts the correct terminal state for each one."

---

## Bullet 3 — Containerized API + worker stack, live dashboard with state transitions and errors

### Code proof

| Claim | File |
|---|---|
| Separate API container | `docker-compose.yml` — `api` service |
| Separate worker container | `docker-compose.yml` — `worker` service |
| Dashboard with state pills | `app/ui/templates/dashboard.html`, `jobs_table.html` |
| State transition counts | `app/main.py` — `dashboard()` — counts by status |
| Errors visible in table | `app/ui/templates/jobs_table.html` — `last_error` column |
| Errors visible in detail | `app/ui/templates/job_detail_card.html` — `last_error` block |
| Live auto-refresh (HTMX) | `dashboard.html` — `hx-trigger="every 2s"` |
| Job detail live refresh | `job_detail.html` — polls `/partials/job/{id}` every 2s |

### Demo proof

1. `docker compose up --build`
2. Open `http://localhost:8000/` — shows queued/running/succeeded/dead counts
3. Submit a retry job from `/submit` — watch status pill update live
4. Click a dead job — see `last_error` and attempt history in the detail view
5. Submit a sleep job → click into it → watch `running` → `succeeded` live

### Interview explanation

> "The dashboard uses HTMX to poll two endpoints. The jobs table partial at `/partials/jobs-table` refreshes every 2 seconds — it's a server-side render, no client-side JavaScript state. The job detail page polls `/partials/job/{id}` for the specific job card. The API and worker are separate Docker Compose services sharing the same Postgres. You can scale the worker independently with `--scale worker=N` and the locking just works."

---

## What Is and Isn't Claimed

| Feature | Status | Notes |
|---|---|---|
| Durable storage | Fully implemented | PostgreSQL, survives restarts |
| Atomic claiming | Fully implemented | `SELECT FOR UPDATE SKIP LOCKED` |
| At-least-once | Fully implemented | Lease expiry enables re-claim |
| Exponential backoff | Fully implemented | `min(2^n, 300)` seconds |
| Dead-lettering | Fully implemented | `status=dead` when attempts exhausted |
| 100+ failure simulations | Fully implemented | `scripts/simulate_failures.py` — 110 jobs |
| Live dashboard | Fully implemented | HTMX auto-refresh, error column |
| Horizontal scaling | Architecturally supported | `docker compose --scale worker=N` |
| Exactly-once delivery | NOT claimed | Requires distributed transactions |
| Priority queues | NOT implemented | Possible extension |
| Scheduled/cron jobs | NOT implemented | Possible extension |
