# Afterburner — Architecture

## Overview

Afterburner is a background job queue built on PostgreSQL. Jobs are rows in a
single `jobs` table. A Python worker polls that table, atomically claims
runnable jobs, executes them, and writes outcomes back. The FastAPI server
accepts job submissions and serves the dashboard.

```
┌────────────┐   POST /api/jobs    ┌─────────────────────────┐
│   Client   │ ─────────────────▶  │   FastAPI API (app/)    │
│ (curl/UI)  │                     │   app/main.py           │
└────────────┘                     └──────────┬──────────────┘
                                              │  enqueue_job()
                                              │  (INSERT)
                                   ┌──────────▼──────────────┐
                                   │   PostgreSQL            │
                                   │   jobs table            │
                                   └──────────┬──────────────┘
                                              │  claim_job()
                                              │  (SELECT FOR UPDATE SKIP LOCKED)
                                   ┌──────────▼──────────────┐
                                   │   Worker Process        │
                                   │   app/worker.py         │
                                   └─────────────────────────┘
```

## Components

### API (`app/main.py`)

- Accepts job submissions via `POST /api/jobs`
- Lists/inspects jobs via `GET /api/jobs`, `GET /api/jobs/{id}`
- Serves the HTMX dashboard at `/`
- Submits jobs from the UI form at `/submit`

### Queue (`app/queue.py`)

Core job lifecycle functions:

| Function | What it does |
|---|---|
| `enqueue_job()` | Inserts a new row with `status=queued`, `run_at=now()` |
| `claim_job()` | Atomically claims one runnable job (see below) |
| `mark_succeeded()` | Sets `status=succeeded`, writes result JSON |
| `mark_failed()` | Increments `attempts`, schedules retry or sets `status=dead` |
| `exponential_backoff_seconds()` | Returns `min(2^attempts, 300)` seconds |

### Worker (`app/worker.py`)

Single-threaded polling loop:

1. Call `claim_job()` — if nothing available, sleep and retry
2. Look up the handler function by `job.type`
3. Execute the handler
4. On success → `mark_succeeded()`
5. On exception → `mark_failed()` (retry or dead-letter)

The worker is stateless. Multiple workers can run concurrently without
coordination — Postgres row locks handle all contention.

### Database (`app/models.py`, `alembic/`)

Single table: `jobs`

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID PK | Job identity |
| `type` | VARCHAR(64) | Handler name (e.g. `sleep`, `fail_n_times`) |
| `status` | VARCHAR(16) | `queued` / `running` / `succeeded` / `dead` |
| `payload` | JSONB | Input data for the handler |
| `result` | JSONB | Output written on success |
| `attempts` | INT | How many times this job has been attempted |
| `max_attempts` | INT | Attempt ceiling before dead-lettering |
| `run_at` | TIMESTAMPTZ | Earliest time the job is eligible to be claimed |
| `locked_by` | VARCHAR | Worker ID that holds the current lease |
| `locked_until` | TIMESTAMPTZ | Lease expiry; NULL means not locked |
| `last_error` | TEXT | Error string from the most recent failure |
| `created_at` | TIMESTAMPTZ | Insertion time |
| `updated_at` | TIMESTAMPTZ | Last state-change time |

Index: `ix_jobs_status_run_at` on `(status, run_at)` — supports the claim query.

---

## Job Lifecycle

```
                   ┌─────────┐
  enqueue_job() ──▶│ queued  │
                   └────┬────┘
                        │ claim_job()
                   ┌────▼────┐
                   │ running │
                   └────┬────┘
           ┌────────────┼──────────────┐
           │            │              │
    success │    error, retries left   │ error, no retries left
           │            │              │
    ┌──────▼──────┐ ┌───▼──────┐  ┌───▼──┐
    │ succeeded   │ │  queued  │  │ dead │
    │             │ │ (retry)  │  │      │
    └─────────────┘ └──────────┘  └──────┘
```

**States:**

- `queued` — waiting to be picked up; `run_at` controls when it becomes eligible
- `running` — held by a worker under a lease (expires at `locked_until`)
- `succeeded` — completed successfully; `result` is populated
- `dead` — exhausted all attempts; `last_error` holds the final failure

---

## Atomic Job Claiming

The core concurrency primitive is a single SQL statement:

```sql
SELECT id
FROM jobs
WHERE status = 'queued'
  AND run_at <= now()
  AND (locked_until IS NULL OR locked_until < now())
ORDER BY created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

**Why this works:**

- `FOR UPDATE` — acquires a row-level lock on the selected row
- `SKIP LOCKED` — any other worker hitting this query simultaneously skips
  rows that are already locked, so they get a *different* row
- The immediate `UPDATE` sets `status=running` and writes a `locked_until`
  timestamp before the transaction commits

Result: N concurrent workers each get a different job. No job is processed
twice, and no worker blocks another.

---

## At-Least-Once Execution

Afterburner provides **at-least-once** delivery, not exactly-once. This means:

- Every job that enters the queue will eventually be executed (assuming
  `max_attempts > 0`)
- A job *may* be executed more than once in edge cases

**When can a job run more than once?**

The lease (`locked_until`) expires after 30 seconds. If a worker crashes or
hangs after claiming a job but before calling `mark_succeeded()` or
`mark_failed()`, the lease expires and the job becomes claimable again. A
different worker will then pick it up and re-execute it.

This is intentional and mirrors how production systems like SQS and Sidekiq
work. The tradeoff is that handlers must be **idempotent** — safe to run
multiple times with the same payload.

---

## Retry and Backoff

`mark_failed()` in `app/queue.py`:

1. Increments `attempts`
2. If `attempts >= max_attempts` → set `status=dead`
3. Otherwise → set `status=queued`, set `run_at = now() + backoff`

Backoff is exponential: `min(2^attempts, 300)` seconds

| After attempt | Backoff |
|---|---|
| 1 | 2 s |
| 2 | 4 s |
| 3 | 8 s |
| 4 | 16 s |
| 5+ | 32, 64, 128, 256, 300 s (capped) |

---

## Dead-Letter Handling

When `attempts >= max_attempts`, the job is moved to `status=dead`. Dead jobs:

- Are visible in the dashboard (red `dead` pill)
- Retain their `last_error` and `attempts` count
- Are **not** automatically retried
- Can be inspected at `/jobs/{id}`

---

## Docker Compose Services

```yaml
db:     postgres:16
api:    FastAPI + uvicorn  (port 8000)
worker: Python polling loop
```

Both `api` and `worker` run `alembic upgrade head` on startup, which is
idempotent. In practice the first service to reach Postgres runs the
migration; the second sees no pending revisions and exits immediately.

---

## Scaling

The worker is designed to scale horizontally. Running multiple worker
containers (or increasing `--replicas`) requires zero changes:

```bash
docker compose up --scale worker=3
```

Each worker independently polls and claims jobs. Postgres row locking ensures
no two workers process the same job simultaneously.
