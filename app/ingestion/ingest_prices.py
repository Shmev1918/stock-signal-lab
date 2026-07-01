from __future__ import annotations

from datetime import date

from sqlmodel import Session
from sqlmodel import select

from app.db.models import DailyPrice
from app.providers.base import MarketDataProvider


def ingest_prices(session: Session, provider: MarketDataProvider, ticker: str, start_date: date, end_date: date) -> int:
    rows = provider.get_daily_prices(ticker, start_date, end_date)
    existing_dates = set(
        session.exec(
            select(DailyPrice.price_date).where(
                DailyPrice.ticker == ticker,
                DailyPrice.price_date >= start_date,
                DailyPrice.price_date <= end_date,
            )
        )
    )
    count = 0
    for row in rows:
        if row["price_date"] in existing_dates:
            continue
        session.add(DailyPrice(**row))
        count += 1
    session.commit()
    return count
