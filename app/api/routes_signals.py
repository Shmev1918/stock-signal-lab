from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from sqlmodel import Session

from app.db.session import get_session
from app.services.signal_service import generate_signals
from app.services.signal_service import signal_dicts
from app.services.stock_service import get_latest_signals, get_signal_history, get_signals

router = APIRouter()


@router.post("/signals/{ticker}/generate")
def generate_ticker_signals(ticker: str, session: Session = Depends(get_session)):
    try:
        return signal_dicts(generate_signals(session, ticker.upper(), as_of_date=date.today()))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/signals/{ticker}")
def read_ticker_signals(ticker: str, session: Session = Depends(get_session)):
    signals = get_signals(session, ticker.upper())
    if not signals:
        raise HTTPException(status_code=404, detail="Signals not found")
    return signal_dicts(signals)


@router.get("/signals/{ticker}/latest")
def read_latest_ticker_signals(ticker: str, session: Session = Depends(get_session)):
    signals = get_latest_signals(session, ticker.upper())
    if not signals:
        raise HTTPException(status_code=404, detail="Signals not found")
    return signal_dicts(signals)


@router.get("/signals/{ticker}/history")
def read_signal_history(
    ticker: str,
    signal_name: str | None = Query(default=None),
    signal_category: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    signals = get_signal_history(
        session,
        ticker.upper(),
        signal_name=signal_name,
        signal_category=signal_category,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if not signals:
        raise HTTPException(status_code=404, detail="Signals not found")
    return signal_dicts(signals)
