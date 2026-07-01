from __future__ import annotations

from datetime import date

from app.providers.mock_provider import MockMarketDataProvider


def test_ingestion_uses_selected_provider(monkeypatch, client) -> None:
    calls = {"prices": 0}

    class StubProvider(MockMarketDataProvider):
        def get_daily_prices(self, ticker: str, start_date: date, end_date: date):
            calls["prices"] += 1
            return super().get_daily_prices(ticker, start_date, end_date)

    monkeypatch.setattr(
        "app.services.ingestion_service.get_market_data_provider",
        lambda: StubProvider(),
    )

    response = client.post("/ingest/AAPL")
    assert response.status_code == 200
    assert calls["prices"] == 1
    payload = response.json()
    assert payload["ticker"] == "AAPL"
