from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.db.models import DailyPrice, InvestmentDecision
from app.db.session import engine


def _seed_decision(
    session: Session,
    *,
    ticker: str,
    action: str,
    strategy_name: str,
    conviction: int,
    engine_recommendation: str,
) -> None:
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
            engine_recommendation=engine_recommendation,
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


def test_decision_evaluation_groups_by_human_action_and_engine(client) -> None:
    with Session(engine) as session:
        _seed_decision(
            session,
            ticker="BUY1",
            action="BUY",
            strategy_name="balanced",
            conviction=5,
            engine_recommendation="AVOID",
        )
        _seed_decision(
            session,
            ticker="WAT1",
            action="WATCH",
            strategy_name="growth_momentum",
            conviction=3,
            engine_recommendation="ACCUMULATE",
        )
        _seed_decision(
            session,
            ticker="HLD1",
            action="HOLD",
            strategy_name="value_recovery",
            conviction=4,
            engine_recommendation="HOLD",
        )
        _seed_price(session, "BUY1", date(2026, 4, 1), 120.0)
        _seed_price(session, "WAT1", date(2026, 4, 1), 80.0)
        _seed_price(session, "HLD1", date(2026, 4, 1), 100.0)

    response = client.get("/decisions/evaluation?horizon=90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["horizon"] == 90
    assert payload["count"] == 3
    assert payload["available_count"] == 3
    assert payload["groups"]["human_action"]["BUY"]["count"] == 1
    assert payload["groups"]["human_action"]["WATCH"]["count"] == 1
    assert payload["groups"]["human_action"]["HOLD"]["count"] == 1
    assert payload["groups"]["engine_recommendation"]["AVOID"]["count"] == 1
    assert payload["groups"]["engine_recommendation"]["ACCUMULATE"]["count"] == 1
    assert payload["groups"]["engine_recommendation"]["HOLD"]["count"] == 1
    assert payload["groups"]["strategy_name"]["balanced"]["count"] == 1
    assert payload["groups"]["strategy_name"]["growth_momentum"]["count"] == 1
    assert payload["groups"]["strategy_name"]["value_recovery"]["count"] == 1


def test_decision_evaluation_disagreement_detection(client) -> None:
    with Session(engine) as session:
        _seed_decision(
            session,
            ticker="BUYX",
            action="BUY",
            strategy_name="balanced",
            conviction=5,
            engine_recommendation="SPECULATIVE",
        )
        _seed_decision(
            session,
            ticker="AVOX",
            action="AVOID",
            strategy_name="balanced",
            conviction=4,
            engine_recommendation="ACCUMULATE",
        )
        _seed_decision(
            session,
            ticker="WTCX",
            action="WATCH",
            strategy_name="balanced",
            conviction=3,
            engine_recommendation="ACCUMULATE",
        )
        _seed_price(session, "BUYX", date(2026, 4, 1), 110.0)
        _seed_price(session, "AVOX", date(2026, 4, 1), 90.0)
        _seed_price(session, "WTCX", date(2026, 4, 1), 105.0)

    response = client.get("/decisions/evaluation?horizon=90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["disagreements"]["human_buy_engine_avoid_or_speculative"]["count"] == 1
    assert payload["disagreements"]["human_avoid_engine_accumulate"]["count"] == 1
    assert payload["disagreements"]["human_watch_engine_accumulate"]["count"] == 1


def test_decision_evaluation_filters_and_missing_data(client) -> None:
    with Session(engine) as session:
        _seed_decision(
            session,
            ticker="FILT",
            action="BUY",
            strategy_name="balanced",
            conviction=5,
            engine_recommendation="ACCUMULATE",
        )
        _seed_decision(
            session,
            ticker="SKIP",
            action="SELL",
            strategy_name="growth_momentum",
            conviction=2,
            engine_recommendation="AVOID",
        )
        _seed_price(session, "FILT", date(2026, 4, 1), 140.0)

    filtered = client.get("/decisions/evaluation?horizon=90&strategy_name=balanced&min_conviction=4")
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["count"] == 1
    assert filtered_payload["available_count"] == 1
    assert filtered_payload["groups"]["strategy_name"]["balanced"]["count"] == 1
    assert "growth_momentum" not in filtered_payload["groups"]["strategy_name"]

    missing = client.get("/decisions/evaluation?horizon=90")
    assert missing.status_code == 200
    missing_payload = missing.json()
    assert missing_payload["count"] == 2
    assert missing_payload["available_count"] == 1

