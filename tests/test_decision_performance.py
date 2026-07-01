from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.db.models import InvestmentDecision
from app.db.session import engine


def _prepare_decision(client, ticker: str, action: str, strategy_name: str = "balanced", conviction: int = 3) -> None:
    client.post(f"/watchlist/{ticker}")
    client.post(f"/ingest/{ticker}")
    client.post(f"/score/{ticker}?strategy={strategy_name}")
    client.post(
        f"/decisions/{ticker}",
        json={
            "action": action,
            "strategy_name": strategy_name,
            "conviction": conviction,
            "thesis": f"{action} thesis",
            "risks": f"{action} risks",
        },
    )


def test_single_ticker_performance(client) -> None:
    _prepare_decision(client, "AAPL", "BUY", "balanced", conviction=4)

    response = client.get("/decisions/AAPL/performance")
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == 1
    assert payload["average_return"] is not None
    assert payload["win_rate"] in {0.0, 1.0}
    assert payload["best_decision"]["ticker"] == "AAPL"
    assert payload["worst_decision"]["ticker"] == "AAPL"
    row = payload["decisions"][0]
    assert row["decision_date"]
    assert row["engine_recommendation"]
    assert row["latest_price"] is not None
    assert row["return_since_decision_percent"] is not None


def test_all_decision_performance_and_filters(client) -> None:
    _prepare_decision(client, "AAPL", "BUY", "balanced", conviction=4)
    _prepare_decision(client, "MSFT", "HOLD", "growth_momentum", conviction=2)
    _prepare_decision(client, "NVDA", "AVOID", "value_recovery", conviction=5)

    response = client.get("/decisions/performance")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 3
    assert payload["decisions"]

    filtered = client.get("/decisions/performance?action=BUY&strategy_name=balanced&min_conviction=4")
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["count"] == 1
    assert all(row["action"] == "BUY" for row in filtered_payload["decisions"])
    assert all(row["strategy_name"] == "balanced" for row in filtered_payload["decisions"])
    assert all(row["conviction"] >= 4 for row in filtered_payload["decisions"])


def test_missing_price_data_handling(client) -> None:
    with Session(engine) as session:
        session.add(
            InvestmentDecision(
                ticker="NOPE",
                decision_date=date(2026, 1, 1),
                action="WATCH",
                strategy_name="balanced",
                price_at_decision=100.0,
                quantity=None,
                conviction=3,
                thesis="No price yet",
                risks="Missing data",
                engine_recommendation="WATCH",
                engine_opportunity_score=50.0,
                engine_risk_category="MEDIUM_RISK",
            )
        )
        session.commit()

    response = client.get("/decisions/NOPE/performance")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    row = payload["decisions"][0]
    assert row["latest_price"] is None
    assert row["latest_price_date"] is None
    assert row["return_since_decision_percent"] is None
    assert row["days_held"] is None
