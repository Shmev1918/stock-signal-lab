from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.acquisition.estimates import estimate_acquisition
from app.acquisition.jobs import (
    AcquisitionJobCreateRequest,
    create_acquisition_job,
    get_acquisition_job,
    list_acquisition_jobs,
    pause_acquisition_job,
    retry_failed_tasks,
    resume_acquisition_job,
    run_acquisition_job,
)
from app.db.session import get_session
from app.providers.polygon_provider import PolygonMarketDataProvider

router = APIRouter(prefix="/acquisition")


@router.get("/jobs")
def read_acquisition_jobs(session: Session = Depends(get_session)):
    return list_acquisition_jobs(session)


@router.get("/jobs/{job_id}")
def read_acquisition_job(job_id: int, session: Session = Depends(get_session)):
    try:
        return get_acquisition_job(session, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs")
def create_job(request: AcquisitionJobCreateRequest, session: Session = Depends(get_session)):
    try:
        return create_acquisition_job(session, request)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/run")
def run_job(
    job_id: int,
    force: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    try:
        return run_acquisition_job(session, job_id, force=force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: int, session: Session = Depends(get_session)):
    try:
        return pause_acquisition_job(session, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: int, session: Session = Depends(get_session)):
    try:
        return resume_acquisition_job(session, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/retry-failed")
def retry_failed(job_id: int, session: Session = Depends(get_session)):
    try:
        return retry_failed_tasks(session, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/report")
def job_report(job_id: int, session: Session = Depends(get_session)):
    try:
        return get_acquisition_job(session, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/estimate")
def estimate(
    provider: str = Query(default="polygon"),
    universe_name: str = Query(default="STOCK_RESEARCH_CORE"),
    years: int = Query(default=2, ge=1),
    include_prices: bool = Query(default=True),
    include_fundamentals: bool = Query(default=True),
    include_options: bool = Query(default=False),
    rate_limit_per_minute: int = Query(default=3, ge=1),
    config_json: str = Query(default="{}"),
):
    return estimate_acquisition(
        provider=provider,
        universe_name=universe_name,
        years=years,
        include_prices=include_prices,
        include_fundamentals=include_fundamentals,
        include_options=include_options,
        rate_limit_per_minute=rate_limit_per_minute,
        config_json=json.loads(config_json or "{}"),
    )


@router.get("/smoke-test")
def smoke_test(ticker: str = Query(default="AAPL")):
    from app.config import get_settings

    settings = get_settings()
    provider = PolygonMarketDataProvider(
        api_key=settings.polygon_api_key,
        mode=settings.polygon_mode,
    )
    try:
        checks = provider.smoke_checks(ticker)
        return {
            "provider": "polygon",
            "api_key_detected": bool(settings.polygon_api_key),
            "mode": settings.polygon_mode,
            "checks": [
                {
                    "name": check.name,
                    "endpoint": check.endpoint,
                    "ticker": check.ticker,
                    "success": check.success,
                    "status_code": check.status_code,
                    "error": check.error,
                }
                for check in checks
            ],
        }
    except Exception as exc:  # pragma: no cover - smoke test report
        raise HTTPException(status_code=400, detail=str(exc)) from exc
