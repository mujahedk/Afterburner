# Afterburner — Demo Script

A step-by-step guide for live demos and interview walkthroughs.

---

## Quick Start (3 minutes)

```bash
# Terminal 1 — start the full stack
make up

# Terminal 2 — once you see "Application startup complete":
make seed          # populate the dashboard with demo jobs
# open http://localhost:8000/
make demo          # guided interactive demo with narration prompts

# Between demos:
make reset         # clear all jobs
make reset && make seed   # clear and re-populate
```

**All commands in one place:**

| Command      | What it does                                             |
| ------------ | -------------------------------------------------------- |
| `make up`    | Start Postgres + API + worker via Docker Compose         |
| `make down`  | Stop and remove containers                               |
| `make seed`  | Submit 5 demo jobs (sleep, retry, dead-letter)           |
| `make demo`  | Guided scenario — submits 3 jobs with narration prompts  |
| `make sim`   | Run 110-job failure simulation with pass/fail assertions |
| `make reset` | Clear all jobs from the database                         |

---

## Setup (manual, if not using Make)

```bash
docker compose up --build
```

Wait until you see:

```
afterburner-api     | INFO:     Application startup complete.
afterburner-worker  | [worker] starting id=worker-docker-1
```

Open the dashboard: **http://localhost:8000/**

---

## The 2-Minute Live Demo Flow

**Before the demo:** run `make seed` so the dashboard is not empty when you open it.

### Step 1 — Show the dashboard (20 seconds)

1. Open **http://localhost:8000/**
2. Point to the 4 KPI cards: Queued / Running / Succeeded / Dead
3. Point to the job table — show the status pills, attempts, and last error column

---

### Step 2 — Submit and watch a successful job (30 seconds)

1. Click **Submit job** in the top-right
2. Type `sleep`, payload `{"duration_ms": 1500}`, click **Submit**
3. You land on the job detail page — watch `status` change from `queued → running → succeeded`
4. Point to `locked_by` and `locked_until` while it is running

---

### Step 3 — Show retries with exponential backoff (40 seconds)

1. Go to **Submit job**, select `fail_n_times`
2. Payload: `{"failures_before_success": 2}`, max attempts: 5
3. Click **Submit** — land on the job detail page
4. Watch: `queued → running → queued (retry in 2s) → running → queued (retry in 4s) → running → succeeded`
5. Point to `last_error` — shows the intentional failure message

---

### Step 4 — Show dead-lettering (30 seconds)

1. Submit `fail_n_times` with `{"failures_before_success": 999}`, max_attempts: 3
2. Watch the job cycle and then turn **dead** (red pill)
3. On the dashboard, the Dead counter increments

---

### Reset

```bash
make reset         # clear everything
make reset && make seed   # or clear and re-populate
```

Or click **Clear dashboard** in the browser UI.

---

## Run the Failure Simulation

```bash
make sim
```

Submits 110 jobs across four failure scenarios and asserts expected outcomes:

```
[PASS]  immediate success (sleep)             30/30 succeeded
[PASS]  success after 1 retry                 20/20 succeeded
[PASS]  success after 2 retries               30/30 succeeded
[PASS]  dead-lettered (fail_n_times=3, max=3) 30/30 dead

ALL SCENARIOS PASSED
```

---

## Architecture Reference

```
Client → POST /api/jobs → enqueue_job() → INSERT INTO jobs
Worker poll → claim_job() → SELECT FOR UPDATE SKIP LOCKED → UPDATE status=running
Worker execute → handler(payload, attempts) → mark_succeeded() or mark_failed()
mark_failed() → attempts++ → if exhausted: status=dead else: status=queued, run_at=now()+backoff
```

Files:

- `app/queue.py` — `enqueue_job`, `claim_job`, `mark_succeeded`, `mark_failed`, `exponential_backoff_seconds`
- `app/worker.py` — polling loop, `handle_sleep`, `handle_fail_n_times`
- `app/main.py` — FastAPI routes, dashboard partials
- `app/models.py` — `Job` ORM model
