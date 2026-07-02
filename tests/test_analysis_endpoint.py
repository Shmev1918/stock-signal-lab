from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from app.db.models import DailyPrice
from app.db.session import engine


def test_analysis_endpoint_returns_consolidated_view(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")

    response = client.get("/analysis/AAPL")
    assert response.status_code == 200
    payload = response.json()

    assert payload["ticker"] == "AAPL"
    assert payload["stock_profile"]["ticker"] == "AAPL"
    assert payload["recommendation"]
    assert payload["risk_category"]
    assert set(payload["signals"]) == {"RISK", "QUALITY", "VALUATION", "MOMENTUM"}
    assert payload["positive_signals"] or payload["negative_signals"]
    assert isinstance(payload["warnings"], list)
    assert payload["summary"]
    assert payload["latest_score"]["ticker"] == "AAPL"
    assert payload["latest_score"]["as_of_date"]
    assert payload["latest_score"]["created_at"]
    assert payload["strategy_name"] in {"balanced", "conservative_quality", "growth_momentum", "value_recovery"}
    assert payload["data_sources"]["prices"] in {"mock", "yfinance"}
    assert payload["data_sources"]["fundamentals"] in {"mock", "yfinance", "yfinance_partial"}
    assert payload["data_sources"]["signals"] == "internal"
    assert payload["data_sources"]["scores"] == "internal"
    assert payload["latest_price_source"] == payload["data_sources"]["prices"]
    assert payload["latest_fundamentals_source"] == payload["data_sources"]["fundamentals"]
    assert payload["latest_signal_source"] == "internal"
    assert payload["score_source"] == "internal"


def test_analysis_endpoint_warns_on_stale_price_data(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")

    with Session(engine) as session:
        prices = session.exec(select(DailyPrice).where(DailyPrice.ticker == "AAPL")).all()
        for price in prices:
            price.price_date = price.price_date - timedelta(days=30)
            session.add(price)
        session.commit()

    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")

    response = client.get("/analysis/AAPL")
    assert response.status_code == 200
    payload = response.json()
    assert any("stale" in warning for warning in payload["warnings"])
