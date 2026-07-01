from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import Stock, StockScore, StockSignal
from app.db.session import engine


def test_scoring_stores_score(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    response = client.post("/score/AAPL")
    assert response.status_code == 200

    with Session(engine) as session:
        scores = list(session.exec(select(StockScore).where(StockScore.ticker == "AAPL")))
        assert scores
        assert scores[-1].ticker == "AAPL"
        stock = session.exec(select(Stock).where(Stock.ticker == "AAPL")).first()
        assert stock is not None
        signals = list(session.exec(select(StockSignal).where(StockSignal.stock_id == stock.id)))
        assert signals
        assert {signal.signal_category for signal in signals} >= {"RISK", "QUALITY", "VALUATION", "MOMENTUM"}
        assert response.json()["explanation"]["signals"]
