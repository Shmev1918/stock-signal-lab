from dataclasses import asdict
from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException
from sqlmodel import Session

from app.scoring.strategy_profiles import get_strategy_profile, list_strategy_profiles
from app.db.session import get_session
from app.services.score_evaluation_service import get_score_evaluation, get_score_strategy_evaluation
from app.services.analysis_service import build_strategy_rankings
from app.services.scoring_service import score_ticker
from app.services.stock_service import get_latest_scores, get_watchlist

router = APIRouter()


def _score_payload(score):
    payload = score.model_dump()
    payload["scored_at"] = score.created_at
    payload["model_versions"] = {
        "scoring": score.scoring_model_version,
        "signals": score.signal_model_version,
    }
    return payload


@router.post("/score/{ticker}")
def score_one(
    ticker: str,
    strategy: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy).name if strategy is not None else None
        return _score_payload(score_ticker(session, ticker.upper(), strategy_name=selected_strategy))
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/score/watchlist")
def score_watchlist(strategy: str | None = Query(default=None), session: Session = Depends(get_session)):
    try:
        selected_strategy = get_strategy_profile(strategy).name if strategy is not None else None
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    watchlist = get_watchlist(session)
    results = []
    for item in watchlist:
        results.append(_score_payload(score_ticker(session, item.ticker, strategy_name=selected_strategy)))
    return results


@router.get("/rankings")
def rankings(session: Session = Depends(get_session)):
    return get_latest_scores(session)


@router.get("/rankings/strategies")
def rankings_by_strategy(
    strategies: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    include_signals: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    try:
        selected_strategies = None
        if strategies is not None:
            parsed = [item.strip() for item in strategies.split(",") if item.strip()]
            selected_strategies = [get_strategy_profile(name).name for name in parsed] if parsed else None
        rankings = build_strategy_rankings(
            session,
            strategy_names=selected_strategies,
            limit=limit,
            include_signals=include_signals,
        )
        return {"rankings": rankings}
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/strategies")
def strategies():
    return [asdict(profile) for profile in list_strategy_profiles()]


@router.get("/scores/evaluation")
def scores_evaluation(
    horizon: int = Query(default=90, ge=1),
    strategy_name: str | None = Query(default=None),
    recommendation: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy_name).name if strategy_name is not None else None
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_score_evaluation(
        session,
        horizon_days=horizon,
        strategy_name=selected_strategy,
        recommendation=recommendation,
    )


@router.get("/scores/evaluation/details")
def scores_evaluation_details(
    horizon: int = Query(default=90, ge=1),
    strategy_name: str | None = Query(default=None),
    recommendation: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy_name).name if strategy_name is not None else None
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = get_score_evaluation(
        session,
        horizon_days=horizon,
        strategy_name=selected_strategy,
        recommendation=recommendation,
    )
    return result["details"]


@router.get("/scores/evaluation/strategies")
def scores_evaluation_strategies(
    horizon: int = Query(default=90, ge=1),
    recommendation: str | None = Query(default=None),
    min_opportunity_score: float | None = Query(default=None),
    risk_category: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    return get_score_strategy_evaluation(
        session,
        horizon_days=horizon,
        recommendation=recommendation,
        min_opportunity_score=min_opportunity_score,
        risk_category=risk_category,
    )
