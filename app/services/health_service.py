from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session

from app.config import get_settings
from app.constants import SCORING_MODEL_VERSION, SIGNAL_MODEL_VERSION


def get_health_details(session: Session) -> dict[str, object]:
    settings = get_settings()
    database_reachable = False
    try:
        session.exec(text("SELECT 1")).first()
        database_reachable = True
    except Exception:
        database_reachable = False

    return {
        "status": "ok" if database_reachable else "degraded",
        "service": settings.app_name,
        "database_reachable": database_reachable,
        "active_provider": settings.market_data_provider,
        "default_scoring_strategy": settings.scoring_strategy,
        "scoring_model_version": SCORING_MODEL_VERSION,
        "signal_model_version": SIGNAL_MODEL_VERSION,
    }
