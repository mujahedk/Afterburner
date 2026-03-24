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

| Command | What it does |
|---|---|
| `make up` | Start Postgres + API + worker via Docker Compose |
| `make down` | Stop and remove containers |
| `make seed` | Submit 5 demo jobs (sleep, retry, dead-letter) |
| `make demo` | Guided scenario — submits 3 jobs with narration prompts |
| `make sim` | Run 110-job failure simulation with pass/fail assertions |
| `make reset` | Clear all jobs from the database |

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

**Say:** "This is a live view of the job queue. Both the counts and the table auto-refresh every 2 seconds — it's HTMX polling server-side rendered partials, no JavaScript framework."

---

### Step 2 — Submit and watch a successful job (30 seconds)

1. Click **Submit job** in the top-right
2. Type `sleep`, payload `{"duration_ms": 1500}`, click **Submit**
3. You land on the job detail page — watch `status` change from `queued → running → succeeded`
4. Point to `locked_by` and `locked_until` while it is running

**Say:** "The worker claims this job with `SELECT FOR UPDATE SKIP LOCKED`. It sets `status=running` and writes a `locked_until` timestamp — that's the lease. If the worker crashed before finishing, the lease would expire and any other worker could reclaim it. That's the at-least-once guarantee."

---

### Step 3 — Show retries with exponential backoff (40 seconds)

1. Go to **Submit job**, select `fail_n_times`
2. Payload: `{"failures_before_success": 2}`, max attempts: 5
3. Click **Submit** — land on the job detail page
4. Watch: `queued → running → queued (retry in 2s) → running → queued (retry in 4s) → running → succeeded`
5. Point to `last_error` — shows the intentional failure message

**Say:** "Each failure calls `mark_failed()`, which increments `attempts` and sets `run_at = now() + 2^attempts seconds`. That's the exponential backoff — 2s, then 4s, then 8s. The worker enforces the delay by checking `run_at <= now()` on every poll. No timers, no scheduler — just a timestamp in Postgres."

---

### Step 4 — Show dead-lettering (30 seconds)

1. Submit `fail_n_times` with `{"failures_before_success": 999}`, max_attempts: 3
2. Watch the job cycle and then turn **dead** (red pill)
3. On the dashboard, the Dead counter increments

**Say:** "When `attempts >= max_attempts`, the job moves to `dead` permanently. It stays visible in the dashboard with its full error history. Dead jobs are never auto-retried — in production you'd build an alert or a manual retry button on top of this."

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

**Say:** "I wrote a simulation harness that submits 110 jobs across four failure scenarios and asserts each one reaches the correct terminal state. This validates the retry logic, the backoff scheduling, and the dead-letter transition end-to-end."

---

## Interview Questions and Answers

### "What does at-least-once execution mean and how do you guarantee it?"

> "At-least-once means every job that enters the queue will be executed at least once, but it *might* run more than once in edge cases.
>
> The guarantee comes from the lease. When a worker claims a job, it writes `locked_until = now() + 30 seconds`. If the worker crashes before finishing, the lease expires. The claim query's WHERE clause includes `locked_until < now()`, so the job becomes visible again and another worker picks it up.
>
> The edge case: a worker finishes executing the handler but then crashes *before* writing `mark_succeeded()`. The lease expires, another worker re-executes the job. That's why handlers should be idempotent — safe to run twice with the same payload."

---

### "How does the atomic claiming work?"

> "A single SQL statement: `SELECT FOR UPDATE SKIP LOCKED`. `FOR UPDATE` locks the selected row. `SKIP LOCKED` means any concurrent worker hitting this query simultaneously gets a *different* row — no blocking, no double-processing. I then immediately update that row to `status=running` with a `locked_until` timestamp before committing the transaction. The lock and the update happen atomically within the same transaction."

---

### "Why use Postgres as a queue instead of a message broker like RabbitMQ or SQS?"

> "For this use case, it keeps the operational surface small — one service instead of two. The transactional guarantees you get from Postgres are exactly what you need: you can atomically claim a job and update its state in a single transaction, with no possibility of message loss between the broker and your database. The tradeoff is throughput — at very high job volumes, a dedicated broker will outperform a polling loop. But for most workloads under a few thousand jobs per second, Postgres is more than fast enough and much simpler to operate."

---

### "How would you scale the workers?"

> "Because workers are stateless and job claiming is handled entirely by Postgres row locks, you can run as many workers as you want without any coordination. It's just `docker compose up --scale worker=3`. Each worker independently polls and claims a different job. The only limit is Postgres connection count and the throughput of the claim query, which benefits from the composite index on `(status, run_at)`."

---

### "What's the difference between `run_at` and `locked_until`?"

> "`run_at` is the *eligibility* timestamp — it controls when a job becomes available to be claimed. For immediate jobs it's `now()`. For retries it's `now() + backoff`. The worker's claim query filters `run_at <= now()`, which is how the backoff delay is enforced without any timers.
>
> `locked_until` is the *lease* timestamp — it marks how long the current worker has exclusive ownership. It's set when a job is claimed and cleared when it finishes. If it expires without clearing, the job is considered abandoned and becomes claimable again."

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
