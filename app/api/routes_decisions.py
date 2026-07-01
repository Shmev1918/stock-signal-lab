from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.scoring.strategy_profiles import get_strategy_profile
from app.services.decision_service import (
    create_investment_decision,
    get_decision_evaluation,
    get_decision_performance_horizons,
    get_decision_performance,
    list_investment_decisions,
    summarize_decision_performance,
)

router = APIRouter()


class DecisionCreate(BaseModel):
    action: str = Field(pattern="^(WATCH|BUY|SELL|HOLD|AVOID)$")
    strategy_name: str | None = None
    decision_date: date | None = None
    quantity: float | None = None
    conviction: int = Field(default=3, ge=1, le=5)
    thesis: str = ""
    risks: str = ""


@router.post("/decisions/{ticker}")
def create_decision(ticker: str, payload: DecisionCreate, session: Session = Depends(get_session)):
    try:
        selected_strategy = get_strategy_profile(payload.strategy_name).name if payload.strategy_name is not None else None
        decision, warnings = create_investment_decision(
            session,
            ticker.upper(),
            action=payload.action,
            strategy_name=selected_strategy,
            decision_date=payload.decision_date,
            quantity=payload.quantity,
            conviction=payload.conviction,
            thesis=payload.thesis,
            risks=payload.risks,
        )
        payload = decision.model_dump()
        payload["warnings"] = warnings
        return payload
    except LookupError as exc:
        status_code = 400 if "Unknown strategy" in str(exc) else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/decisions")
def read_decisions(session: Session = Depends(get_session)):
    return list_investment_decisions(session)


def _parse_horizons(value: str) -> list[int]:
    horizons: list[int] = []
    for raw_value in value.split(","):
        item = raw_value.strip()
        if not item:
            continue
        horizon = int(item)
        if horizon <= 0:
            raise ValueError("Horizons must be positive integers")
        horizons.append(horizon)
    return horizons


@router.get("/decisions/performance")
def decision_performance(
    action: str | None = Query(default=None),
    strategy_name: str | None = Query(default=None),
    min_conviction: int | None = Query(default=None, ge=1, le=5),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy_name).name if strategy_name is not None else None
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = get_decision_performance(
        session,
        action=action,
        strategy_name=selected_strategy,
        min_conviction=min_conviction,
    )
    return {**summarize_decision_performance(rows), "decisions": rows}


@router.get("/decisions/performance-horizons")
def decision_performance_horizons(
    horizons: str = Query(default="30,90,180,365"),
    action: str | None = Query(default=None),
    strategy_name: str | None = Query(default=None),
    min_conviction: int | None = Query(default=None, ge=1, le=5),
    session: Session = Depends(get_session),
):
    try:
        selected_horizons = _parse_horizons(horizons)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        selected_strategy = get_strategy_profile(strategy_name).name if strategy_name is not None else None
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_decision_performance_horizons(
        session,
        horizons=selected_horizons,
        action=action,
        strategy_name=selected_strategy,
        min_conviction=min_conviction,
    )


@router.get("/decisions/evaluation")
def decision_evaluation(
    horizon: int = Query(default=90, ge=1),
    strategy_name: str | None = Query(default=None),
    min_conviction: int | None = Query(default=None, ge=1, le=5),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy_name).name if strategy_name is not None else None
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_decision_evaluation(
        session,
        horizon_days=horizon,
        strategy_name=selected_strategy,
        min_conviction=min_conviction,
    )


@router.get("/decisions/{ticker}/performance")
def decision_performance_for_ticker(ticker: str, session: Session = Depends(get_session)):
    rows = get_decision_performance(session, ticker=ticker.upper())
    if not rows:
        raise HTTPException(status_code=404, detail="Decisions not found")
    return {**summarize_decision_performance(rows), "decisions": rows}


@router.get("/decisions/{ticker}")
def read_decisions_for_ticker(ticker: str, session: Session = Depends(get_session)):
    rows = list_investment_decisions(session, ticker.upper())
    if not rows:
        raise HTTPException(status_code=404, detail="Decisions not found")
    return rows
