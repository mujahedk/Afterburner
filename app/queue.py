from datetime import timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from .models import Job, utcnow


def enqueue_job(db: Session, job_type: str, payload: dict, max_attempts: int = 5) -> Job:
    job = Job(
        type=job_type,
        payload=payload or {},
        status="queued",
        attempts=0,
        max_attempts=max_attempts,
        run_at=utcnow(),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_jobs(db: Session, limit: int = 50, status: str | None = None, job_type: str | None = None):
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    if job_type:
        q = q.filter(Job.type == job_type)
    return q.order_by(Job.created_at.desc()).limit(limit).all()


def get_job(db: Session, job_id):
    return db.get(Job, job_id)


def claim_job(db: Session, worker_id: str, lease_seconds: int = 30) -> Job | None:
    """
    Atomically claim one runnable job using SELECT FOR UPDATE SKIP LOCKED.

    The SKIP LOCKED clause means concurrent workers each get a different row —
    no worker blocks another, and no job is double-processed. The lease
    (locked_until) ensures a job becomes reclaimable if a worker crashes before
    marking it succeeded or failed.
    """
    sql = text("""
        SELECT id
        FROM jobs
        WHERE status = 'queued'
          AND run_at <= now()
          AND (locked_until IS NULL OR locked_until < now())
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """)

    row = db.execute(sql).fetchone()
    if not row:
        return None

    job_id = row[0]

    db.execute(
        text("""
            UPDATE jobs
            SET status       = 'running',
                locked_by    = :locked_by,
                locked_until = now() + (:lease_seconds || ' seconds')::interval,
                updated_at   = now()
            WHERE id = :job_id
        """),
        {"locked_by": worker_id, "lease_seconds": lease_seconds, "job_id": job_id},
    )
    db.commit()

    return db.get(Job, job_id)


def mark_succeeded(db: Session, job_id, result: dict) -> None:
    job = db.get(Job, job_id)
    if not job:
        return

    job.status = "succeeded"
    job.result = result
    job.locked_by = None
    job.locked_until = None
    job.updated_at = utcnow()
    db.commit()


def exponential_backoff_seconds(attempts: int, cap: int = 300) -> int:
    # True exponential: 2s, 4s, 8s, 16s, ... capped at cap seconds.
    # `attempts` is the new attempt count after incrementing.
    return min(2 ** attempts, cap)


def mark_failed(db: Session, job_id, error: str) -> None:
    job = db.get(Job, job_id)
    if not job:
        return

    job.attempts += 1
    job.last_error = error
    job.locked_by = None
    job.locked_until = None
    job.updated_at = utcnow()

    if job.attempts >= job.max_attempts:
        job.status = "dead"
        db.commit()
        return

    delay = exponential_backoff_seconds(job.attempts)
    job.status = "queued"
    job.run_at = utcnow() + timedelta(seconds=delay)
    db.commit()
