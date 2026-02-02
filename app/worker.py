import os
import time
import uuid
from datetime import datetime, timezone

from .db import SessionLocal
from .queue import claim_job, mark_succeeded, mark_failed


def utcnow():
    return datetime.now(timezone.utc)


def handle_sleep(payload: dict) -> dict:
    duration_ms = int(payload.get("duration_ms", 1000))
    time.sleep(duration_ms / 1000.0)
    return {"slept_ms": duration_ms, "finished_at": utcnow().isoformat()}

def handle_fail_n_times(payload: dict, attempts: int) -> dict:
    failures_before_success = int(payload.get("failures_before_success", 0))
    if attempts < failures_before_success:
        raise RuntimeError(f"Intentional failure (attempt={attempts}, need<{failures_before_success})")
    return {"ok": True, "attempts": attempts, "finished_at": utcnow().isoformat()}

HANDLERS = {
    "sleep": handle_sleep,
    "fail_n_times": handle_fail_n_times,
}



def run_worker(poll_interval: float = 0.75, lease_seconds: int = 30):
    worker_id = os.getenv("WORKER_ID") or f"worker-{uuid.uuid4()}"
    print(f"[Afterburner Worker] starting worker_id={worker_id}")

    while True:
        db = SessionLocal()
        try:
            job = claim_job(db, worker_id=worker_id,
                            lease_seconds=lease_seconds)

            if not job:
                time.sleep(poll_interval)
                continue

            print(
                f"[Afterburner Worker] claimed job id={job.id} type={job.type}")

            handler = HANDLERS.get(job.type)
            if not handler:
                # For Day 2: mark succeeded with a placeholder result.
                # Day 3 we’ll mark failed + retry.
                mark_succeeded(
                    db, job.id, {"warning": f"no handler for type={job.type}"})
                continue

            # job.attempts is current attempts count BEFORE this run
            if job.type == "fail_n_times":
                result = handler(job.payload, job.attempts)
            else:
                result = handler(job.payload)

            mark_succeeded(db, job.id, result)

            print(f"[Afterburner Worker] succeeded job id={job.id}")

        except KeyboardInterrupt:
            print("[Afterburner Worker] shutting down")
            return
        except Exception as e:
            try:
                if 'job' in locals() and job is not None:
                    mark_failed(db, job.id, str(e))
                    print(f"[Afterburner Worker] failed job id={job.id} attempts={job.attempts+1}/{job.max_attempts} err={e}")
            except Exception as inner:
                print(f"[Afterburner Worker] error while marking failed: {inner}")
            time.sleep(0.5)

        finally:
            db.close()


if __name__ == "__main__":
    run_worker()
