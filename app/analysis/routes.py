from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analysis import concurrency, service
from app.analysis.schemas import (
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
    return [AnalysisJobSummary.model_validate(j) for j in jobs]


@router.post("/run", response_model=AnalysisRunResponse)
async def submit_run(
    body: AnalysisRunRequest,
    _api_key: str = Depends(verify_api_key),
):
    try:
        job = await service.submit_run(
            tickers=body.tickers,
            intervals=body.intervals,
            model_ids=body.model_ids,
            horizon_bars=body.horizon_bars,
        )
    except service.AnalysisInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except concurrency.AtCapacityError:
        raise HTTPException(status_code=429, detail="at_capacity")
    return AnalysisRunResponse(job_id=job.id, task_count=job.task_count, status=job.status)


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
        tasks=[AnalysisTaskResponse.model_validate(t) for t in job.tasks],
    )
