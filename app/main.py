import json

from fastapi import FastAPI, Depends, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID

from .db import get_db
from .schemas import JobCreate, JobOut
from .queue import enqueue_job, list_jobs, get_job

app = FastAPI(title="Afterburner", version="0.1.0")

templates = Jinja2Templates(directory="app/ui/templates")

# Template filters for cleaner display in the dashboard
templates.env.filters["short_id"] = lambda v: str(v)[:8]
templates.env.filters["fmt_dt"] = lambda v: v.strftime("%Y-%m-%d %H:%M") if v else "—"


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@app.post("/api/jobs", response_model=JobOut)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    return enqueue_job(db, payload.type, payload.payload, payload.max_attempts)


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


# ---------------------------------------------------------------------------
# Dashboard UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
    type: str | None = None,
):
    all_jobs = list_jobs(db, limit=500)
    counts = {"queued": 0, "running": 0, "succeeded": 0, "dead": 0}
    for j in all_jobs:
        if j.status in counts:
            counts[j.status] += 1

    jobs = list_jobs(db, limit=25, status=status, job_type=type)
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


@app.get("/partials/counts", response_class=HTMLResponse)
def counts_partial(request: Request, db: Session = Depends(get_db)):
    all_jobs = list_jobs(db, limit=500)
    counts = {"queued": 0, "running": 0, "succeeded": 0, "dead": 0}
    for j in all_jobs:
        if j.status in counts:
            counts[j.status] += 1
    return templates.TemplateResponse(
        "counts_partial.html",
        {"request": request, "counts": counts},
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


@app.get("/partials/job/{job_id}", response_class=HTMLResponse)
def job_detail_partial(job_id: UUID, request: Request, db: Session = Depends(get_db)):
    """Partial used by the job detail page to poll for live state updates."""
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    def pretty(obj):
        if obj is None:
            return ""
        return json.dumps(obj, indent=2, sort_keys=True)

    return templates.TemplateResponse(
        "job_detail_card.html",
        {
            "request": request,
            "job": job,
            "payload_pretty": pretty(job.payload),
            "result_pretty": pretty(job.result),
        },
    )


@app.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request):
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
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)


@app.post("/admin/clear-jobs")
def clear_jobs(db: Session = Depends(get_db)):
    db.execute(text("TRUNCATE TABLE jobs;"))
    db.commit()
    return RedirectResponse(url="/", status_code=303)
