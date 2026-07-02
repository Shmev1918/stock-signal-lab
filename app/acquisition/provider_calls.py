from __future__ import annotations

from datetime import datetime
import time
from typing import Any, Callable, TypeVar

from sqlmodel import Session

from app.acquisition.rate_limit import ProviderRateLimiter
from app.db.models import ProviderAPICall
from app.providers.base import MarketDataError, MarketDataNotFound

T = TypeVar("T")


class ProviderCallResult:
    def __init__(self, value: Any, call: ProviderAPICall) -> None:
        self.value = value
        self.call = call


def start_provider_call(
    session: Session,
    *,
    provider: str,
    endpoint: str,
    request_key: str,
    ticker: str | None,
    retries: int = 0,
) -> ProviderAPICall:
    row = ProviderAPICall(
        provider=provider,
        endpoint=endpoint,
        request_key=request_key,
        ticker=ticker,
        started_at=datetime.now(),
        retries=retries,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def finish_provider_call(
    session: Session,
    row: ProviderAPICall,
    *,
    success: bool,
    http_status: int | None = None,
    error_message: str | None = None,
    started_monotonic: float | None = None,
) -> ProviderAPICall:
    row.completed_at = datetime.now()
    if started_monotonic is not None:
        row.duration_ms = int(max((time.monotonic() - started_monotonic) * 1000.0, 0.0))
    row.success = success
    row.http_status = http_status
    row.error_message = error_message
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def call_provider(
    session: Session,
    *,
    provider: str,
    endpoint: str,
    request_key: str,
    ticker: str | None,
    func: Callable[[], T],
    rate_limiter: ProviderRateLimiter | None = None,
    max_retries: int = 2,
) -> ProviderCallResult:
    attempt = 0
    last_exc: Exception | None = None
    while True:
        if rate_limiter is not None:
            rate_limiter.acquire(provider)
        row = start_provider_call(
            session,
            provider=provider,
            endpoint=endpoint,
            request_key=request_key,
            ticker=ticker,
            retries=attempt,
        )
        started_monotonic = time.monotonic()
        try:
            value = func()
        except MarketDataError as exc:
            last_exc = exc
            status_code = getattr(exc, "status_code", None)
            finish_provider_call(
                session,
                row,
                success=False,
                http_status=status_code,
                error_message=str(exc),
                started_monotonic=started_monotonic,
            )
            should_retry = attempt < max_retries and not isinstance(exc, MarketDataNotFound) and (
                status_code is None or status_code >= 500 or status_code == 429
            )
            if should_retry:
                retry_after = getattr(exc, "retry_after", None)
                sleep_seconds = float(retry_after or min(2 ** attempt, 30))
                time.sleep(sleep_seconds)
                attempt += 1
                continue
            raise
        except Exception as exc:  # pragma: no cover - defensive acquisition guard
            last_exc = exc
            finish_provider_call(
                session,
                row,
                success=False,
                error_message=str(exc),
                started_monotonic=started_monotonic,
            )
            raise
        finish_provider_call(
            session,
            row,
            success=True,
            http_status=200,
            started_monotonic=started_monotonic,
        )
        return ProviderCallResult(value=value, call=row)
    if last_exc is not None:  # pragma: no cover - safety net
        raise last_exc
