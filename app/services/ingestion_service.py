from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session

from app.ingestion.ingest_fundamentals import ingest_fundamentals
from app.ingestion.ingest_prices import ingest_prices
from app.providers.base import MarketDataNotFound, MarketDataProvider, MarketDataTimeout
from app.providers.factory import get_market_data_provider


def ingest_ticker(session: Session, ticker: str, provider: MarketDataProvider | None = None) -> dict[str, object]:
    provider = provider or get_market_data_provider()
    end_date = date.today()
    start_date = end_date - timedelta(days=365 * 3)
    warnings: list[str] = []
    price_rows = 0
    try:
        price_rows = ingest_prices(session, provider, ticker, start_date, end_date)
    except MarketDataTimeout as exc:
        return {"ticker": ticker, "error": "timeout", "detail": str(exc), "warnings": [str(exc)]}
    except MarketDataNotFound as exc:
        return {"ticker": ticker, "error": "not_found", "detail": str(exc), "warnings": [str(exc)]}

    try:
        counts = ingest_fundamentals(session, provider, ticker)
    except MarketDataTimeout as exc:
        warnings.append(str(exc))
        counts = {"stocks": 0, "fundamentals": 0, "dividends": 0, "news_items": 0, "warnings": []}
    except MarketDataNotFound as exc:
        warnings.append(str(exc))
        counts = {"stocks": 0, "fundamentals": 0, "dividends": 0, "news_items": 0, "warnings": []}

    warnings.extend([str(item) for item in counts.pop("warnings", [])])
    try:
        counts["prices"] = price_rows
    except Exception:  # pragma: no cover - defensive guard
        counts["prices"] = price_rows

    if counts.get("prices", 0) == 0:
        warnings.append(f"empty price history for {ticker}")

    counts["ticker"] = ticker
    counts["warnings"] = warnings
    counts["status"] = "partial_success" if warnings else "success"
    return counts
