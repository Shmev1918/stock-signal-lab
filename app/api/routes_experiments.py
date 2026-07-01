from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.experiments.runner import ExperimentRequest, get_experiment_by_id, get_experiment_summary, list_experiments, run_experiment

router = APIRouter()


class ExperimentRunPayload(BaseModel):
    name: str
    description: str | None = None
    experiment_type: str = Field(pattern="^(strategy_score_threshold|recommendation_outcome|risk_category_outcome|signal_threshold)$")
    strategy_name: str | None = None
    horizon_days: int = Field(default=90, ge=1, le=3650)
    benchmark_ticker: str = Field(default="SPY")
    start_date: date
    end_date: date
    filters: dict = Field(default_factory=dict)


@router.post("/experiments/run")
def run_experiment_endpoint(payload: ExperimentRunPayload, session: Session = Depends(get_session)):
    try:
        request = ExperimentRequest(
            name=payload.name,
            description=payload.description,
            experiment_type=payload.experiment_type,
            strategy_name=payload.strategy_name,
            horizon_days=payload.horizon_days,
            benchmark_ticker=payload.benchmark_ticker,
            start_date=payload.start_date,
            end_date=payload.end_date,
            filters=payload.filters,
        )
        return run_experiment(session, request)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/experiments")
def list_experiments_endpoint(session: Session = Depends(get_session)):
    return list_experiments(session)


@router.get("/experiments/{experiment_id}")
def get_experiment_endpoint(experiment_id: int, session: Session = Depends(get_session)):
    try:
        return get_experiment_by_id(session, experiment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/experiments/{experiment_id}/summary")
def get_experiment_summary_endpoint(experiment_id: int, session: Session = Depends(get_session)):
    try:
        return get_experiment_summary(session, experiment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
