from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import StockScore
from app.db.session import engine


def _prepare_watchlist(client) -> None:
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        client.post(f"/watchlist/{ticker}")
        client.post(f"/ingest/{ticker}")
        client.post(f"/score/{ticker}")


def test_strategy_rankings_returns_all_strategies(client) -> None:
    _prepare_watchlist(client)

    response = client.get("/rankings/strategies")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["rankings"]) == {
        "balanced",
        "conservative_quality",
        "growth_momentum",
        "value_recovery",
    }
    assert all(payload["rankings"][name] for name in payload["rankings"])
    assert all(row["rank"] >= 1 for rows in payload["rankings"].values() for row in rows)


def test_strategy_rankings_returns_selected_strategies_and_limit(client) -> None:
    _prepare_watchlist(client)

    response = client.get("/rankings/strategies?strategies=balanced,value_recovery&limit=1")
    assert response.status_code == 200
    payload = response.json()["rankings"]

    assert set(payload) == {"balanced", "value_recovery"}
    assert all(len(rows) == 1 for rows in payload.values())
    assert all(rows[0]["rank"] == 1 for rows in payload.values())


def test_strategy_rankings_include_signals(client) -> None:
    _prepare_watchlist(client)

    response = client.get("/rankings/strategies?strategies=balanced&include_signals=true")
    assert response.status_code == 200
    rows = response.json()["rankings"]["balanced"]

    assert rows
    assert "positive_signals" in rows[0]
    assert "negative_signals" in rows[0]
    assert len(rows[0]["positive_signals"]) <= 3
    assert len(rows[0]["negative_signals"]) <= 3


def test_strategy_rankings_persists_strategy_name(client) -> None:
    _prepare_watchlist(client)

    client.get("/rankings/strategies?strategies=conservative_quality")

    with Session(engine) as session:
        scores = list(session.exec(select(StockScore).where(StockScore.strategy_name == "conservative_quality")))
        assert scores
        assert all(score.strategy_name == "conservative_quality" for score in scores)


def test_strategy_rankings_reuses_existing_signals(client, monkeypatch) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/signals/AAPL/generate")

    import app.services.signal_service as signal_service_module

    def _fail(*args, **kwargs):  # pragma: no cover - regression guard
        raise AssertionError("rankings/strategies should not regenerate signals when they already exist")

    monkeypatch.setattr(signal_service_module, "generate_signals", _fail)

    response = client.get("/rankings/strategies?strategies=balanced")
    assert response.status_code == 200
    assert response.json()["rankings"]["balanced"]


def test_strategy_rankings_scores_on_demand(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")

    response = client.get("/rankings/strategies?strategies=value_recovery")
    assert response.status_code == 200
    rows = response.json()["rankings"]["value_recovery"]
    assert rows
    assert rows[0]["strategy_name"] == "value_recovery"
