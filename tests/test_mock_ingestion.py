from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import DailyPrice, Stock
from app.db.session import engine


def test_mock_ingestion_stores_prices(client) -> None:
    response = client.post("/ingest/AAPL")
    assert response.status_code == 200

    with Session(engine) as session:
        prices = list(session.exec(select(DailyPrice).where(DailyPrice.ticker == "AAPL")))
        stock = session.exec(select(Stock).where(Stock.ticker == "AAPL")).first()
        assert prices
        assert stock is not None

