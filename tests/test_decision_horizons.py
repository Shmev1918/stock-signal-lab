from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.db.models import DailyPrice, InvestmentDecision
from app.db.session import engine


def _seed_decision(session: Session, ticker: str, action: str, strategy_name: str, conviction: int) -> None:
    session.add(
        InvestmentDecision(
            ticker=ticker,
            decision_date=date(2026, 1, 1),
            action=action,
            strategy_name=strategy_name,
            price_at_decision=100.0,
            quantity=None,
            conviction=conviction,
            thesis=f"{ticker} thesis",
            risks=f"{ticker} risks",
            engine_recommendation="HOLD",
            engine_opportunity_score=50.0,
            engine_risk_category="MEDIUM_RISK",
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


def test_decision_horizons_use_nearest_trading_day(client) -> None:
    with Session(engine) as session:
        _seed_decision(session, "HZN", "BUY", "balanced", 4)
        _seed_price(session, "HZN", date(2026, 1, 1), 100.0)
        _seed_price(session, "HZN", date(2026, 2, 2), 110.0)
        _seed_price(session, "HZN", date(2026, 4, 15), 130.0)
        _seed_price(session, "HZN", date(2026, 6, 30), 95.0)

    response = client.get("/decisions/performance-horizons?horizons=30,90,180,365")
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == 1
    assert payload["horizons"] == [30, 90, 180, 365]
    row = payload["decisions"][0]
    assert round(row["return_30d"], 2) == 10.0
    assert round(row["return_90d"], 2) == 30.0
    assert round(row["return_180d"], 2) == -5.0
    assert row["return_365d"] is None
    assert payload["summary_by_horizon"]["30"]["count"] == 1
    assert payload["summary_by_horizon"]["90"]["count"] == 1
    assert payload["summary_by_horizon"]["180"]["count"] == 1
    assert payload["summary_by_horizon"]["365"]["count"] == 0


def test_decision_horizons_filters_apply(client) -> None:
    with Session(engine) as session:
        _seed_decision(session, "AAA", "BUY", "balanced", 5)
        _seed_decision(session, "BBB", "HOLD", "growth_momentum", 2)
        _seed_price(session, "AAA", date(2026, 1, 1), 100.0)
        _seed_price(session, "AAA", date(2026, 2, 1), 120.0)
        _seed_price(session, "BBB", date(2026, 1, 1), 100.0)
        _seed_price(session, "BBB", date(2026, 2, 1), 80.0)

    response = client.get(
        "/decisions/performance-horizons?horizons=30&action=BUY&strategy_name=balanced&min_conviction=4"
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == 1
    assert len(payload["decisions"]) == 1
    assert payload["decisions"][0]["ticker"] == "AAA"
    assert payload["decisions"][0]["return_30d"] == 20.0
    assert payload["summary_by_horizon"]["30"]["count"] == 1


def test_decision_horizons_missing_data_is_null(client) -> None:
    with Session(engine) as session:
        _seed_decision(session, "MIS", "WATCH", "balanced", 3)
        _seed_price(session, "MIS", date(2026, 1, 1), 100.0)

    response = client.get("/decisions/performance-horizons?horizons=30,90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == 1
    row = payload["decisions"][0]
    assert row["return_30d"] is None
    assert row["return_90d"] is None
    assert payload["summary_by_horizon"]["30"]["count"] == 0
    assert payload["summary_by_horizon"]["90"]["count"] == 0
