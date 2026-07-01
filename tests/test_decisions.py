from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import InvestmentDecision, StockScore
from app.db.session import engine


def _prepare_score(client, ticker: str = "AAPL") -> None:
    client.post(f"/watchlist/{ticker}")
    client.post(f"/ingest/{ticker}")
    client.post(f"/score/{ticker}")


def test_create_decision_records_engine_snapshot(client) -> None:
    _prepare_score(client)

    response = client.post(
        "/decisions/AAPL",
        json={
            "action": "BUY",
            "strategy_name": "balanced",
            "quantity": 10,
            "conviction": 4,
            "thesis": "Strong long-term cash flow",
            "risks": "Valuation is high",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["action"] == "BUY"
    assert payload["engine_recommendation"]
    assert payload["engine_opportunity_score"] is not None
    assert payload["engine_risk_category"]
    assert payload["warnings"] == []

    with Session(engine) as session:
        decision = session.exec(select(InvestmentDecision).where(InvestmentDecision.ticker == "AAPL")).first()
        assert decision is not None
        assert decision.strategy_name == "balanced"
        assert decision.quantity == 10
        assert decision.conviction == 4
        score = session.exec(select(StockScore).where(StockScore.ticker == "AAPL", StockScore.strategy_name == "balanced")).first()
        assert score is not None
        assert decision.engine_recommendation == score.recommendation
        assert decision.engine_opportunity_score == score.opportunity_score
        assert decision.engine_risk_category == score.risk_category


def test_list_decisions_and_get_ticker(client) -> None:
    _prepare_score(client, "AAPL")
    _prepare_score(client, "MSFT")

    client.post("/decisions/AAPL", json={"action": "WATCH", "strategy_name": "balanced", "thesis": "Watch it", "risks": "None"})
    client.post("/decisions/MSFT", json={"action": "HOLD", "strategy_name": "growth_momentum", "thesis": "Keep it", "risks": "Slowdown"})

    all_response = client.get("/decisions")
    assert all_response.status_code == 200
    all_rows = all_response.json()
    assert len(all_rows) >= 2

    ticker_response = client.get("/decisions/AAPL")
    assert ticker_response.status_code == 200
    ticker_rows = ticker_response.json()
    assert ticker_rows
    assert all(row["ticker"] == "AAPL" for row in ticker_rows)


def test_create_decision_uses_default_strategy_when_omitted(client) -> None:
    _prepare_score(client)

    response = client.post("/decisions/AAPL", json={"action": "AVOID", "thesis": "Too expensive", "risks": "Momentum weak"})
    assert response.status_code == 200
    assert response.json()["strategy_name"] == "balanced"


def test_create_duplicate_same_day_decision_warns(client) -> None:
    _prepare_score(client)

    first = client.post("/decisions/AAPL", json={"action": "WATCH", "thesis": "First", "risks": "None"})
    assert first.status_code == 200
    second = client.post("/decisions/AAPL", json={"action": "BUY", "thesis": "Second", "risks": "Still none"})
    assert second.status_code == 200
    payload = second.json()
    assert payload["ticker"] == "AAPL"
    assert payload["warnings"]
    assert any("duplicate decision warning" in warning for warning in payload["warnings"])


def test_create_decision_validation(client) -> None:
    _prepare_score(client)

    response = client.post("/decisions/AAPL", json={"action": "INVALID", "thesis": "x", "risks": "y"})
    assert response.status_code == 422
