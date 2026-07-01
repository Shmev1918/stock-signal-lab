from __future__ import annotations

from datetime import date
from typing import Any
from typing import Protocol


class MarketDataProvider(Protocol):
    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]: ...

    def get_latest_quote(self, ticker: str) -> dict[str, Any]: ...

    def get_company_profile(self, ticker: str) -> dict[str, Any]: ...

    def get_fundamentals(self, ticker: str) -> dict[str, Any]: ...

    def get_dividends(self, ticker: str) -> list[dict[str, Any]]: ...

    def get_news(self, ticker: str) -> list[dict[str, Any]]: ...


class MarketDataError(Exception):
    """Base class for provider failures."""


class MarketDataNotFound(MarketDataError, LookupError):
    """Raised when a provider cannot find a ticker or any usable data."""


class MarketDataTimeout(MarketDataError, TimeoutError):
    """Raised when a provider call times out."""


def coerce_warnings(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings = payload.pop("_warnings", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    return payload, [str(item) for item in warnings]
