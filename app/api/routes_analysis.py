from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.scoring.strategy_profiles import get_strategy_profile
from app.services.analysis_service import build_analysis, build_analysis_history, build_strategy_comparison

router = APIRouter()


@router.get("/analysis/{ticker}")
def read_analysis(
    ticker: str,
    compact: bool = Query(default=False),
    strategy: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy).name if strategy is not None else None
        return build_analysis(session, ticker.upper(), compact=compact, strategy_name=selected_strategy)
    except LookupError as exc:
        status_code = 400 if "Unknown strategy" in str(exc) else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/analysis/{ticker}/history")
def read_analysis_history(
    ticker: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=500),
    strategy: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy).name if strategy is not None else None
        history = build_analysis_history(
            session,
            ticker.upper(),
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            strategy_name=selected_strategy,
        )
    except LookupError as exc:
        status_code = 400 if "Unknown strategy" in str(exc) else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if not history:
        raise HTTPException(status_code=404, detail="Analysis history not found")
    return history


@router.get("/analysis/{ticker}/compare-strategies")
def compare_strategies(
    ticker: str,
    strategies: str | None = Query(default=None, description="Comma-separated strategy names"),
    session: Session = Depends(get_session),
):
    try:
        if strategies is None:
            selected = None
        else:
            parsed = [item.strip() for item in strategies.split(",") if item.strip()]
            selected = [get_strategy_profile(name).name for name in parsed] if parsed else None
        return build_strategy_comparison(session, ticker.upper(), strategy_names=selected)
    except LookupError as exc:
        status_code = 400 if "Unknown strategy" in str(exc) else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
