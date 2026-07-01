from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.db.models import DailyPrice, StockScore
from app.db.session import engine


def _seed_score(
    session: Session,
    *,
    ticker: str,
    as_of_date: date,
    strategy_name: str,
    recommendation: str,
    risk_category: str,
    opportunity_score: float,
) -> None:
    session.add(
        StockScore(
            ticker=ticker,
            as_of_date=as_of_date,
            risk_score=40.0,
            quality_score=50.0,
            valuation_score=60.0,
            momentum_score=70.0,
            opportunity_score=opportunity_score,
            risk_category=risk_category,
            recommendation=recommendation,
            explanation={"summary": "seeded"},
            source="internal",
            scoring_model_version="0.1.0",
            signal_model_version="0.1.0",
            strategy_name=strategy_name,
        )
    )
    session.commit()


def _seed_price(session: Session, ticker: str, price_date: date, close: float) -> None:
    session.add(
        DailyPrice(
            ticker=ticker,
            price_date=price_date,
            open=close,
            high=close,
            low=close,
            close=close,
            adj_close=close,
            volume=1000,
            source="mock",
        )
    )
    session.commit()


def test_score_evaluation_horizon_and_grouping(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="AAA",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="ACCUMULATE",
            risk_category="MEDIUM_RISK",
            opportunity_score=80.0,
        )
        _seed_score(
            session,
            ticker="BBB",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="HIGH_RISK",
            opportunity_score=55.0,
        )
        _seed_score(
            session,
            ticker="CCC",
            as_of_date=date(2026, 1, 1),
            strategy_name="growth_momentum",
            recommendation="AVOID",
            risk_category="SPECULATIVE",
            opportunity_score=25.0,
        )
        _seed_price(session, "AAA", date(2026, 1, 1), 100.0)
        _seed_price(session, "AAA", date(2026, 4, 3), 120.0)
        _seed_price(session, "BBB", date(2026, 1, 1), 100.0)
        _seed_price(session, "BBB", date(2026, 4, 3), 90.0)
        _seed_price(session, "CCC", date(2026, 1, 1), 100.0)
        _seed_price(session, "CCC", date(2026, 4, 3), 80.0)

    response = client.get("/scores/evaluation?horizon=90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["horizon"] == 90
    assert payload["count"] == 3
    assert payload["available_count"] == 3
    assert payload["groups"]["recommendation"]["ACCUMULATE"]["count"] == 1
    assert payload["groups"]["recommendation"]["WATCH"]["count"] == 1
    assert payload["groups"]["recommendation"]["AVOID"]["count"] == 1
    assert payload["groups"]["strategy_name"]["balanced"]["count"] == 2
    assert payload["groups"]["strategy_name"]["growth_momentum"]["count"] == 1
    assert round(payload["groups"]["recommendation"]["ACCUMULATE"]["average_return"], 2) == 20.0
    assert round(payload["groups"]["recommendation"]["WATCH"]["average_return"], 2) == -10.0


def test_score_evaluation_filters_and_details(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="FIL",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="ACCUMULATE",
            risk_category="MEDIUM_RISK",
            opportunity_score=75.0,
        )
        _seed_score(
            session,
            ticker="SKIP",
            as_of_date=date(2026, 1, 1),
            strategy_name="value_recovery",
            recommendation="AVOID",
            risk_category="SPECULATIVE",
            opportunity_score=20.0,
        )
        _seed_price(session, "FIL", date(2026, 1, 1), 100.0)
        _seed_price(session, "FIL", date(2026, 4, 2), 110.0)
        _seed_price(session, "SKIP", date(2026, 1, 1), 100.0)
        _seed_price(session, "SKIP", date(2026, 4, 2), 95.0)

    filtered = client.get("/scores/evaluation?horizon=90&strategy_name=balanced&recommendation=ACCUMULATE")
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["count"] == 1
    assert filtered_payload["available_count"] == 1
    assert filtered_payload["groups"]["strategy_name"]["balanced"]["count"] == 1
    assert "value_recovery" not in filtered_payload["groups"]["strategy_name"]

    details = client.get("/scores/evaluation/details?horizon=90&strategy_name=balanced")
    assert details.status_code == 200
    rows = details.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "FIL"
    assert row["scored_at"] == "2026-01-01"
    assert row["recommendation"] == "ACCUMULATE"
    assert row["horizon_return"] == 10.0
    assert row["horizon_price_date"] == "2026-04-02"


def test_score_evaluation_missing_horizon_data(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="MISS",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="MEDIUM_RISK",
            opportunity_score=50.0,
        )
        _seed_price(session, "MISS", date(2026, 1, 1), 100.0)

    response = client.get("/scores/evaluation?horizon=90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == 1
    assert payload["available_count"] == 0
    assert payload["groups"]["recommendation"] == {}
    details = client.get("/scores/evaluation/details?horizon=90")
    assert details.status_code == 200
    row = details.json()[0]
    assert row["horizon_return"] is None
    assert row["horizon_price_date"] is None
