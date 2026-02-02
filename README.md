# Afterburner 🔥

Mini Job Queue + Worker System (FastAPI + Postgres)

Afterburner is a stripped-down background task processor that demonstrates the core building blocks used in production async systems: durable job storage, atomic job claiming, lease-based locking, retries with backoff, dead-lettering, and an ops-style dashboard for visibility.

This project is designed to be small enough to understand end-to-end, but “real” enough to talk about in interviews.

---

## Features

- **Enqueue jobs** via API or UI
- **Worker processes jobs** in the background
- **Atomic claiming** using `SELECT … FOR UPDATE SKIP LOCKED`
- **Lease-based locking** (`locked_until`) to recover from worker crashes
- **Retries with backoff** using `run_at` scheduling
- **Dead-lettering** when `max_attempts` is exceeded
- **Dashboard UI** (HTMX) with live refresh + job drill-down

---

## Architecture

**Services**

- **API**: FastAPI server for job submission + dashboard
- **Worker**: background loop that claims and executes jobs
- **DB**: Postgres (durable queue + job state)

**Job state model**

- `queued` → `running` → `succeeded`
- `queued` → `running` → `queued` (retry scheduled via `run_at`)
- `queued` → `running` → `dead` (exceeded `max_attempts`)

**At-least-once delivery**
Jobs are claimed with row locking and a lease. If a worker crashes mid-job, the lease expires and the job becomes claimable again.

---

## Getting Started (Full Stack)

### 1) Run everything

```bash
docker compose up --build
```
