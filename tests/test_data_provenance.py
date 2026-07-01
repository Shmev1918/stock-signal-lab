from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import DailyPrice, Fundamental, StockScore, StockSignal
from app.db.session import engine


def test_persisted_rows_include_sources(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")

    with Session(engine) as session:
        price = session.exec(select(DailyPrice).where(DailyPrice.ticker == "AAPL")).first()
        fundamental = session.exec(select(Fundamental).where(Fundamental.ticker == "AAPL")).first()
        score = session.exec(select(StockScore).where(StockScore.ticker == "AAPL")).first()
        signal = session.exec(select(StockSignal).where(StockSignal.signal_name == "volatility")).first()

    assert price is not None and price.source in {"mock", "yfinance"}
    assert fundamental is not None and fundamental.source in {"mock", "yfinance", "yfinance_partial"}
    assert score is not None and score.source == "internal"
    assert signal is not None and signal.source == "internal"
