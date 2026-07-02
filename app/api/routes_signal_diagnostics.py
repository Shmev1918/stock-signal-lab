from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.services.signal_diagnostics_service import get_signal_diagnostics

router = APIRouter(prefix="/diagnostics")


@router.get("/signals/{ticker}")
def read_signal_diagnostics(
    ticker: str,
    as_of_date: date | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        return get_signal_diagnostics(session, ticker, as_of_date=as_of_date)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
