from fastapi import FastAPI, Depends, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from uuid import UUID

from .db import get_db
from .schemas import JobCreate, JobOut
from .queue import enqueue_job, list_jobs, get_job

import json

app = FastAPI(title="Afterburner", version="0.1.0")

templates = Jinja2Templates(directory="app/ui/templates")


@app.get("/health")
def health():
    return {"status": "ok"}

# ---- API ----


@app.post("/api/jobs", response_model=JobOut)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = enqueue_job(db, payload.type, payload.payload, payload.max_attempts)
    return job


@app.get("/api/jobs", response_model=list[JobOut])
def api_list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = None,
    type: str | None = None,
):
    return list_jobs(db, limit=limit, status=status, job_type=type)


@app.get("/api/jobs/{job_id}", response_model=JobOut)
def api_get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

# ---- UI (minimal Day 1) ----

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
    type: str | None = None,
):
    # KPI counts
    all_jobs = list_jobs(db, limit=500)
    counts = {"queued": 0, "running": 0, "succeeded": 0, "dead": 0}
    for j in all_jobs:
        if j.status in counts:
            counts[j.status] += 1

    # initial table load
    jobs = list_jobs(db, limit=25, status=status, job_type=type)

    # type options for filter dropdown
    types = sorted({j.type for j in all_jobs})

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "jobs": jobs,
            "counts": counts,
            "status": status or "",
            "type": type or "",
            "types": types,
        },
    )

@app.get("/partials/jobs-table", response_class=HTMLResponse)
def jobs_table_partial(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
    type: str | None = None,
):
    jobs = list_jobs(db, limit=25, status=status, job_type=type)
    return templates.TemplateResponse(
        "jobs_table.html",
        {"request": request, "jobs": jobs},
    )

@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail_page(job_id: UUID, request: Request, db: Session = Depends(get_db)):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    def pretty(obj):
        if obj is None:
            return ""
        return json.dumps(obj, indent=2, sort_keys=True)

    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "job": job,
            "payload_pretty": pretty(job.payload),
            "result_pretty": pretty(job.result),
        },
    )

@app.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request):
    # prefill examples
    examples = {
        "sleep": json.dumps({"duration_ms": 1500}, indent=2),
        "fail_n_times": json.dumps({"failures_before_success": 2}, indent=2),
    }
    return templates.TemplateResponse(
        "submit.html",
        {"request": request, "examples": examples},
    )

@app.post("/submit")
def submit_job_from_form(
    job_type: str = Form(...),
    payload_json: str = Form("{}"),
    max_attempts: int = Form(5),
    db: Session = Depends(get_db),
):
    try:
        payload = json.loads(payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except Exception:
        payload = {}

    job = enqueue_job(db, job_type, payload, max_attempts=max_attempts)
    # redirect to job detail
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)