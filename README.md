# Afterburner 🔥

**Mini Job Queue + Worker System**

Afterburner is a lightweight background job queue and worker system built to demonstrate real-world asynchronous processing patterns. It implements durable job storage, atomic job claiming, retries with backoff, dead-letter handling, and an ops-style dashboard for monitoring job execution.

The goal of this project is not to compete with tools like Celery or Sidekiq, but to clearly show how these systems work under the hood.

---

## Why Afterburner?

Modern applications rely heavily on background processing:

- sending emails
- processing uploads
- calling third-party APIs
- running long or unreliable tasks

Afterburner demonstrates how these systems are built using:

- relational databases
- explicit locking
- retry logic
- failure recovery
- simple operational visibility

All without hidden magic.

---

## Features

- **Job submission** via API or UI
- **Background worker** that processes jobs asynchronously
- **Atomic job claiming** using `SELECT … FOR UPDATE SKIP LOCKED`
- **Lease-based locking** to recover from worker crashes
- **Retries with backoff** using scheduled `run_at` timestamps
- **Dead-letter jobs** after exceeding `max_attempts`
- **Live dashboard** with job status, filtering, and drill-down views
- **Docker Compose** for one-command startup

---

## Architecture Overview

```

┌──────────┐ ┌────────────┐
│ Client │ ───▶ │ API │
└──────────┘ │ (FastAPI) │
└─────┬──────┘
│
┌─────▼──────┐
│ Postgres │
│ (Jobs DB) │
└─────┬──────┘
│
┌─────▼──────┐
│ Worker │
│ (Python) │
└────────────┘

```

### Components

- **API**
  Accepts job submissions, exposes job status, and serves the dashboard UI.
- **Worker**
  Continuously polls for runnable jobs, executes them, and updates their state.
- **Database (Postgres)**
  Acts as the durable job queue and source of truth.

---

## Job Lifecycle

Jobs transition through the following states:

```

queued → running → succeeded
queued → running → queued (retry scheduled)
queued → running → dead

```

### Guarantees

- **At-least-once execution**
- **No double-processing** (row-level locks)
- **Crash recovery** via lock expiration

---

## Atomic Job Claiming (Core Idea)

Workers claim jobs using:

```sql
SELECT id
FROM jobs
WHERE status = 'queued'
  AND run_at <= now()
  AND (locked_until IS NULL OR locked_until < now())
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

This ensures:

- multiple workers can run safely
- no two workers process the same job
- crashed workers don’t permanently block jobs

---

## Demo Job Types

### 1. `sleep`

Simulates long-running work.

**Payload**

```json
{ "duration_ms": 1500 }
```

---

### 2. `fail_n_times`

Fails intentionally to demonstrate retries, backoff, and dead-lettering.

**Payload**

```json
{ "failures_before_success": 2 }
```

- fails twice
- retries with increasing delay
- succeeds on the third attempt

To demonstrate dead-lettering, set:

```json
{ "failures_before_success": 999 }
```

with `max_attempts = 3`.

---

## Dashboard

The dashboard provides:

- live job status counts (queued / running / succeeded / dead)
- auto-refreshing job table
- filters by status and type
- job detail pages showing payloads, results, and errors
- a UI-based job submission form

**Routes**

- `/` – dashboard
- `/submit` – submit a job
- `/jobs/{id}` – job detail view

---

## Running the Full Stack (Recommended)

### Prerequisites

- Docker
- Docker Compose

### Start everything

```bash
docker compose up --build
```

### Open the app

- Dashboard: [http://localhost:8000/](http://localhost:8000/)
- Submit jobs: [http://localhost:8000/submit](http://localhost:8000/submit)

Workers start automatically and process jobs in the background.

---

## API Usage

### Create a job

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"type":"sleep","payload":{"duration_ms":1000},"max_attempts":5}'
```

### List jobs

```bash
curl http://localhost:8000/api/jobs
```

### Get job details

```bash
curl http://localhost:8000/api/jobs/<JOB_ID>
```

---

## Local Development (Without Docker)

```bash
# Start API
uvicorn app.main:app --reload

# Start worker
python3 -m app.worker
```

Postgres must be running locally, and `DATABASE_URL` must be set.

---

## Tech Stack

- **Python 3.12**
- **FastAPI**
- **SQLAlchemy**
- **PostgreSQL**
- **Alembic**
- **HTMX**
- **Docker / Docker Compose**

---

## What This Project Demonstrates

- how background job queues actually work
- safe concurrency with relational databases
- retry and backoff strategies
- dead-letter handling
- operational visibility for async systems
- clean separation of API and worker processes

---

## Possible Extensions

- priority queues
- multiple named queues
- scheduled / cron jobs
- job cancellation
- WebSocket-based live updates
- metrics and tracing
- horizontal worker scaling

---

## License

MIT

```

```
