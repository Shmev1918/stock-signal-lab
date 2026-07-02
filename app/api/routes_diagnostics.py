from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db.session import get_session
from app.services.diagnostics_service import get_distribution_diagnostics

router = APIRouter(prefix="/diagnostics")


@router.get("/distributions")
def read_distributions(
    strategy_name: str | None = Query(default=None),
    signal_name: str | None = Query(default=None),
    signal_category: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    return get_distribution_diagnostics(
        session,
        strategy_name=strategy_name,
        signal_name=signal_name,
        signal_category=signal_category,
    )
