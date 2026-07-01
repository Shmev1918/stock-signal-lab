from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.services.health_service import get_health_details

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stock-signal-lab"}


@router.get("/health/details")
def health_details(session: Session = Depends(get_session)) -> dict[str, object]:
    return get_health_details(session)
