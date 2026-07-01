from fastapi import APIRouter, Depends
from fastapi import HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.services.ingestion_service import ingest_ticker
from app.services.scoring_service import score_ticker
from app.services.signal_service import generate_signals as generate_signals_for_ticker
from app.services.stock_service import get_watchlist, remove_watchlist_item, upsert_watchlist_item
from app.services.watchlist_service import active_watchlist, parse_strategies, refresh_watchlist_workflow, watchlist_status_payload

router = APIRouter()


@router.get("/watchlist")
def read_watchlist(session: Session = Depends(get_session)):
    items = get_watchlist(session)
    if items:
        return items
    return active_watchlist(session)


@router.post("/watchlist/refresh")
def refresh_watchlist(
    strategies: str | None = Query(default=None),
    generate_signals: bool = Query(default=True, alias="generate_signals"),
    score: bool = Query(default=True),
    force_reingest: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    try:
        parse_strategies(strategies)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return refresh_watchlist_workflow(
        session,
        strategies=strategies,
        generate_signals=generate_signals,
        score=score,
        force_reingest=force_reingest,
        ingest_fn=ingest_ticker,
        generate_signals_fn=generate_signals_for_ticker,
        score_fn=score_ticker,
    )


@router.get("/watchlist/status")
def watchlist_status(session: Session = Depends(get_session)):
    return watchlist_status_payload(session)


@router.post("/watchlist/{ticker}")
def add_watchlist_item(ticker: str, session: Session = Depends(get_session)):
    return upsert_watchlist_item(session, ticker.upper())


@router.delete("/watchlist/{ticker}")
def delete_watchlist_item(ticker: str, session: Session = Depends(get_session)):
    remove_watchlist_item(session, ticker.upper())
    return {"status": "removed", "ticker": ticker.upper()}
