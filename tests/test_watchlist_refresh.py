from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.db.models import DailyPrice, Fundamental, StockScore, StockSignal
from app.db.session import engine
from app.providers.base import MarketDataNotFound


def _seed_watchlist(client) -> None:
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        client.post(f"/watchlist/{ticker}")


def _success_for(payload: dict, ticker: str) -> dict:
    for row in payload["successes"]:
        if row["ticker"] == ticker:
            return row
    raise AssertionError(f"Missing ticker in response: {ticker}")


def test_refresh_whole_watchlist(client) -> None:
    _seed_watchlist(client)

    response = client.post("/watchlist/refresh?strategies=balanced,conservative_quality")
    assert response.status_code == 200
    payload = response.json()

    assert payload["tickers_processed"] == 3
    assert payload["provider"] in {"mock", "yfinance"}
    assert payload["strategies"] == ["balanced", "conservative_quality"]
    assert len(payload["successes"]) == 3
    assert payload["failures"] == []
    first = _success_for(payload, "AAPL")
    assert first["ingested"] is True
    assert first["skipped_existing_data"] is False
    assert first["signals_generated"] is True
    assert first["scores_created"] is True

    with Session(engine) as session:
        rows = list(session.exec(select(StockScore).where(StockScore.strategy_name == "balanced")))
        assert rows
        rows = list(session.exec(select(StockScore).where(StockScore.strategy_name == "conservative_quality")))
        assert rows


def test_non_forced_refresh_with_existing_data_reports_skipped_existing_data(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/watchlist/refresh?strategies=balanced")

    response = client.post("/watchlist/refresh?strategies=balanced&generate_signals=false&score=false")
    assert response.status_code == 200
    payload = response.json()
    row = _success_for(payload, "AAPL")

    assert row["ingested"] is False
    assert row["skipped_existing_data"] is True
    assert row["signals_generated"] is False
    assert row["signals_skipped_existing"] is True
    assert row["scores_created"] is False
    assert row["scores_skipped_existing"] is True
    assert row["partial_warnings"] == []
    assert payload["failures"] == []

    with Session(engine) as session:
        assert session.exec(select(DailyPrice).where(DailyPrice.ticker == "AAPL")).first() is not None
        assert session.exec(select(Fundamental).where(Fundamental.ticker == "AAPL")).first() is not None
        assert session.exec(select(StockSignal)).first() is not None
        assert session.exec(select(StockScore).where(StockScore.ticker == "AAPL")).first() is not None


def test_refresh_selected_strategies(client) -> None:
    _seed_watchlist(client)

    response = client.post("/watchlist/refresh?strategies=value_recovery&score=true&generate_signals=true")
    assert response.status_code == 200
    payload = response.json()

    assert payload["strategies"] == ["value_recovery"]
    with Session(engine) as session:
        rows = list(session.exec(select(StockScore).where(StockScore.strategy_name == "value_recovery")))
        assert rows


def test_refresh_partial_failure_handling(client, monkeypatch) -> None:
    _seed_watchlist(client)

    import app.api.routes_watchlist as routes_watchlist

    original_ingest = routes_watchlist.ingest_ticker

    def _wrapped_ingest(session, ticker):  # pragma: no cover - exercised through API
        if ticker == "MSFT":
            raise RuntimeError("simulated ingest failure")
        return original_ingest(session, ticker)

    monkeypatch.setattr(routes_watchlist, "ingest_ticker", _wrapped_ingest)

    response = client.post("/watchlist/refresh?strategies=balanced")
    assert response.status_code == 200
    payload = response.json()

    assert payload["tickers_processed"] == 3
    assert len(payload["failures"]) == 1
    assert payload["failures"][0]["ticker"] == "MSFT"
    assert len(payload["successes"]) == 2


def test_refresh_returns_partial_success_when_metadata_missing(client, monkeypatch) -> None:
    client.post("/watchlist/AAPL")

    class StubProvider:
        def get_daily_prices(self, ticker: str, start_date: date, end_date: date):
            return [
                {
                    "ticker": ticker.upper(),
                    "price_date": date.today(),
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "adj_close": 10.5,
                    "volume": 1234,
                    "source": "yfinance",
                }
            ]

        def get_latest_quote(self, ticker: str):
            return {"ticker": ticker.upper(), "price": 10.5, "currency": "USD"}

        def get_company_profile(self, ticker: str):
            raise MarketDataNotFound("Unable to fetch company data for AAPL")

        def get_fundamentals(self, ticker: str):
            raise MarketDataNotFound("Unable to fetch company data for AAPL")

        def get_dividends(self, ticker: str):
            return []

        def get_news(self, ticker: str):
            return []

    monkeypatch.setattr(
        "app.services.watchlist_service.get_market_data_provider",
        lambda provider_name=None: StubProvider(),
    )

    response = client.post("/watchlist/refresh?strategies=balanced&generate_signals=false&score=false")
    assert response.status_code == 200
    payload = response.json()
    row = _success_for(payload, "AAPL")

    assert payload["failures"] == []
    assert row["ingest_status"] == "partial_success"
    assert row["partial_warnings"]
    assert row["ingested"] is True
    assert row["skipped_existing_data"] is False


def test_force_refresh_reports_existing_db_state(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/watchlist/refresh?strategies=balanced")

    response = client.post("/watchlist/refresh?strategies=balanced&force_reingest=true&generate_signals=false&score=false")
    assert response.status_code == 200
    payload = response.json()
    row = _success_for(payload, "AAPL")

    assert row["ingested"] is True
    assert row["skipped_existing_data"] is False
    assert row["scores_skipped_existing"] is True
    assert row["signals_skipped_existing"] is True
    assert payload["failures"] == []


def test_refresh_response_matches_stored_db_state(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/watchlist/refresh?strategies=balanced")

    response = client.post("/watchlist/refresh?strategies=balanced&generate_signals=false&score=false")
    payload = response.json()
    row = _success_for(payload, "AAPL")

    with Session(engine) as session:
        price_count = session.exec(select(DailyPrice).where(DailyPrice.ticker == "AAPL")).all()
        fundamental_count = session.exec(select(Fundamental).where(Fundamental.ticker == "AAPL")).all()
        signal_count = session.exec(select(StockSignal)).all()
        score_count = session.exec(select(StockScore).where(StockScore.ticker == "AAPL")).all()

    assert len(price_count) > 0
    assert len(fundamental_count) > 0
    assert len(signal_count) > 0
    assert len(score_count) > 0
    assert row["skipped_existing_data"] is True
    assert row["signals_skipped_existing"] is True
    assert row["scores_skipped_existing"] is True


def test_watchlist_status_endpoint(client) -> None:
    _seed_watchlist(client)
    client.post("/watchlist/refresh?strategies=balanced")

    response = client.get("/watchlist/status")
    assert response.status_code == 200
    rows = response.json()

    assert len(rows) == 3
    first = rows[0]
    assert {"ticker", "has_prices", "latest_price_date", "has_signals", "latest_signal_date", "has_scores", "latest_score_date", "available_strategies", "data_sources"} <= set(first)
    assert isinstance(first["available_strategies"], list)
    assert set(first["data_sources"]) == {"prices", "fundamentals", "signals", "scores"}


def test_force_reingest_behavior(client, monkeypatch) -> None:
    client.post("/watchlist/AAPL")
    client.post("/watchlist/refresh?strategies=balanced")

    import app.api.routes_watchlist as routes_watchlist

    calls: list[str] = []
    original_ingest = routes_watchlist.ingest_ticker

    def _wrapped_ingest(session, ticker):  # pragma: no cover - exercised through API
        calls.append(ticker)
        return original_ingest(session, ticker)

    monkeypatch.setattr(routes_watchlist, "ingest_ticker", _wrapped_ingest)

    response = client.post("/watchlist/refresh?strategies=balanced&force_reingest=false&generate_signals=false&score=false")
    assert response.status_code == 200
    assert calls == []

    response = client.post("/watchlist/refresh?strategies=balanced&force_reingest=true&generate_signals=false&score=false")
    assert response.status_code == 200
    assert calls == ["AAPL"]
