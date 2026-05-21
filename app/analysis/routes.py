from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from typing import Any, Dict

from fastapi import Body

from app.analysis import service
from app.queue import service as _qsvc
from app.analysis.schemas import (
    AnalysisImportResponse,
    AnalysisJobResponse,
    AnalysisJobSummary,
    AnalysisRunRequest,
    AnalysisRunResponse,
    AnalysisTaskResponse,
)
from app.core.auth import verify_api_key

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/jobs", response_model=List[AnalysisJobSummary])
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _api_key: str = Depends(verify_api_key),
):
    jobs = await service.list_jobs(limit=limit, offset=offset)
    buckets = await service.task_buckets_for(j.id for j in jobs)
    return [
        AnalysisJobSummary(
            id=j.id,
            status=j.status,
            task_count=j.task_count,
            submitted_at=j.submitted_at,
            finished_at=j.finished_at,
            done=buckets.get(j.id, {}).get("done", 0),
            ineligible=buckets.get(j.id, {}).get("ineligible", 0),
            error=buckets.get(j.id, {}).get("error", 0),
            running=buckets.get(j.id, {}).get("running", 0),
            pending=buckets.get(j.id, {}).get("pending", 0),
        )
        for j in jobs
    ]


@router.post("/run", response_model=AnalysisRunResponse, status_code=202)
async def submit_run(
    body: AnalysisRunRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Enqueue an analysis run. Returns 202 with queue_id; worker drains FIFO.

    Pre-validates inputs so bad tickers/intervals return 400 immediately.
    Frontend polls ``GET /v1/analysis/queue/{queue_id}`` for lifecycle, then
    jumps to ``/v1/analysis/jobs/{job_id}`` once status='done'.
    """
    try:
        service.validate_inputs(
            tickers=body.tickers,
            intervals=body.intervals,
            model_ids=body.model_ids,
        )
    except service.AnalysisInputError as e:
        raise HTTPException(status_code=400, detail=str(e))

    item = await _qsvc.enqueue(inputs=body.model_dump(), source="manual")
    return AnalysisRunResponse(
        queue_id=item["id"],
        status="queued",
        job_id=None,
        task_count=None,
    )


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
async def get_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job '{job_id}' not found")
    return AnalysisJobResponse(
        id=job.id,
        status=job.status,
        task_count=job.task_count,
        submitted_at=job.submitted_at,
        finished_at=job.finished_at,
        origin=job.origin,
        tasks=[AnalysisTaskResponse.model_validate(t) for t in job.tasks],
    )


@router.post("/jobs/{job_id}/abort", response_model=AnalysisJobResponse)
async def abort_job(job_id: str, _api_key: str = Depends(verify_api_key)):
    """Force a stuck job to terminal state. See :func:`service.abort_job`."""
    job = await service.abort_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job '{job_id}' not found")
    return AnalysisJobResponse(
        id=job.id,
        status=job.status,
        task_count=job.task_count,
        submitted_at=job.submitted_at,
        finished_at=job.finished_at,
        origin=job.origin,
        tasks=[AnalysisTaskResponse.model_validate(t) for t in job.tasks],
    )


@router.post("/import", response_model=AnalysisImportResponse)
async def import_job(
    payload: Dict[str, Any] = Body(...),
    _api_key: str = Depends(verify_api_key),
):
    """Idempotent receiver for peer-replicated jobs.

    Accepts a snapshot produced by ``_serialize_job_snapshot`` on the
    sending backend. Inserts the job + tasks tagged ``origin='peer'``;
    duplicates (same ``job.id``) return without error so the sender can
    safely retry. NEVER triggers downstream sync (origin != 'self').
    """
    try:
        job_id, status = await service.import_job(payload)
    except service.ImportConflictError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AnalysisImportResponse(job_id=job_id, status=status)
