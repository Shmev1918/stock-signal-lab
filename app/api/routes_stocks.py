from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from sqlmodel import Session

from app.config import get_settings
from app.db.models import WatchlistItem
from app.db.session import get_session
from app.scoring.strategy_profiles import get_strategy_profile
from app.services.ingestion_service import ingest_ticker
from app.services.stock_service import get_latest_score, get_prices, get_score_history, get_stock, get_watchlist, score_history_dicts

router = APIRouter(prefix="")


@router.get("/stocks/{ticker}")
def read_stock(ticker: str, session: Session = Depends(get_session)):
    stock = get_stock(session, ticker.upper())
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    return stock


@router.get("/stocks/{ticker}/prices")
def read_prices(
    ticker: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=365, ge=1, le=5000),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    session: Session = Depends(get_session),
):
    return get_prices(session, ticker.upper(), start_date=start_date, end_date=end_date, limit=limit, order=order)


@router.get("/stocks/{ticker}/score")
def read_score(ticker: str, session: Session = Depends(get_session)):
    score = get_latest_score(session, ticker.upper())
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    return score


@router.get("/stocks/{ticker}/scores")
def read_score_history(
    ticker: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=500),
    strategy: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy).name if strategy is not None else get_settings().scoring_strategy
    except LookupError as exc:
        status_code = 400 if "Unknown strategy" in str(exc) else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return score_history_dicts(
        get_score_history(
            session,
            ticker.upper(),
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            strategy_name=selected_strategy,
        )
    )


@router.post("/ingest/{ticker}")
def ingest_one(ticker: str, session: Session = Depends(get_session)):
    return ingest_ticker(session, ticker.upper())


@router.post("/ingest/watchlist")
def ingest_watchlist(session: Session = Depends(get_session)):
    watchlist = get_watchlist(session)
    if not watchlist:
        settings = get_settings()
        watchlist = [WatchlistItem(ticker=t) for t in settings.default_watchlist]
    results = {}
    for item in watchlist:
        results[item.ticker] = ingest_ticker(session, item.ticker)
    return results
