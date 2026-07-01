from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import Stock, StockSignal
from app.db.session import engine


def test_signal_generation_and_latest_snapshot(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")

    response = client.post("/signals/AAPL/generate")
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert any(item["signal_name"] == "volatility" for item in payload)
    assert any(item["signal_name"] == "pe_ratio" for item in payload)
    assert all("severity" in item for item in payload)

    latest = client.get("/signals/AAPL/latest")
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload
    assert {item["signal_category"] for item in latest_payload} >= {"RISK", "QUALITY", "VALUATION", "MOMENTUM"}
    assert all(item["severity"] in {"STRONG_POSITIVE", "POSITIVE", "NEUTRAL", "NEGATIVE", "STRONG_NEGATIVE"} for item in latest_payload)

    with Session(engine) as session:
        stock = session.exec(select(Stock).where(Stock.ticker == "AAPL")).first()
        assert stock is not None
        rows = list(session.exec(select(StockSignal).where(StockSignal.stock_id == stock.id)))
        assert rows
        assert any(row.signal_name == "free_cash_flow_positive" for row in rows)
