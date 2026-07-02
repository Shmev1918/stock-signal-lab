from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlmodel import Session

from app.db.models import RawProviderPayload


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def store_raw_payload(
    session: Session,
    *,
    provider: str,
    endpoint: str,
    request_key: str,
    ticker: str | None,
    payload: Any,
) -> RawProviderPayload:
    row = RawProviderPayload(
        provider=provider,
        endpoint=endpoint,
        request_key=request_key,
        ticker=ticker,
        payload_json=sanitize_json(payload),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def mark_payload_normalized(session: Session, raw_payload: RawProviderPayload) -> RawProviderPayload:
    raw_payload.normalized = True
    raw_payload.normalized_at = datetime.now()
    session.add(raw_payload)
    session.commit()
    session.refresh(raw_payload)
    return raw_payload
