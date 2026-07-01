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
    risk_score: float,
    quality_score: float,
    valuation_score: float,
    momentum_score: float,
) -> None:
    session.add(
        StockScore(
            ticker=ticker,
            as_of_date=as_of_date,
            risk_score=risk_score,
            quality_score=quality_score,
            valuation_score=valuation_score,
            momentum_score=momentum_score,
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


def test_score_strategy_evaluation_groups_and_benchmark(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="AAA",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="ACCUMULATE",
            risk_category="MEDIUM_RISK",
            opportunity_score=80.0,
            risk_score=40.0,
            quality_score=50.0,
            valuation_score=60.0,
            momentum_score=70.0,
        )
        _seed_score(
            session,
            ticker="BBB",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="HIGH_RISK",
            opportunity_score=55.0,
            risk_score=30.0,
            quality_score=40.0,
            valuation_score=50.0,
            momentum_score=60.0,
        )
        _seed_score(
            session,
            ticker="CCC",
            as_of_date=date(2026, 1, 1),
            strategy_name="growth_momentum",
            recommendation="AVOID",
            risk_category="SPECULATIVE",
            opportunity_score=25.0,
            risk_score=20.0,
            quality_score=30.0,
            valuation_score=40.0,
            momentum_score=50.0,
        )
        _seed_score(
            session,
            ticker="DDD",
            as_of_date=date(2026, 1, 1),
            strategy_name="value_recovery",
            recommendation="ACCUMULATE",
            risk_category="MEDIUM_RISK",
            opportunity_score=65.0,
            risk_score=35.0,
            quality_score=55.0,
            valuation_score=45.0,
            momentum_score=55.0,
        )
        for ticker, start, end in [
            ("AAA", 100.0, 120.0),
            ("BBB", 100.0, 90.0),
            ("CCC", 100.0, 130.0),
            ("DDD", 100.0, 115.0),
            ("SPY", 100.0, 110.0),
        ]:
            _seed_price(session, ticker, date(2026, 1, 1), start)
            _seed_price(session, ticker, date(2026, 4, 3), end)

    response = client.get("/scores/evaluation/strategies?horizon=90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["horizon"] == 90
    assert payload["count"] == 4
    assert set(payload["strategies"]) == {"balanced", "growth_momentum", "value_recovery"}

    balanced = payload["strategies"]["balanced"]
    assert balanced["count"] == 2
    assert balanced["available_count"] == 2
    assert round(balanced["average_return"], 2) == 5.0
    assert round(balanced["median_return"], 2) == 5.0
    assert round(balanced["win_rate"], 2) == 0.5
    assert round(balanced["best_return"], 2) == 20.0
    assert round(balanced["worst_return"], 2) == -10.0
    assert round(balanced["average_opportunity_score"], 2) == 67.5
    assert round(balanced["average_risk_score"], 2) == 35.0
    assert round(balanced["average_quality_score"], 2) == 45.0
    assert round(balanced["average_valuation_score"], 2) == 55.0
    assert round(balanced["average_momentum_score"], 2) == 65.0
    assert round(balanced["benchmark_return"], 2) == 10.0
    assert round(balanced["excess_return_vs_benchmark"], 2) == -5.0

    growth = payload["strategies"]["growth_momentum"]
    assert growth["count"] == 1
    assert round(growth["benchmark_return"], 2) == 10.0
    assert round(growth["excess_return_vs_benchmark"], 2) == 20.0


def test_score_strategy_evaluation_filters_and_missing_benchmark(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="AAA",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="ACCUMULATE",
            risk_category="MEDIUM_RISK",
            opportunity_score=80.0,
            risk_score=40.0,
            quality_score=50.0,
            valuation_score=60.0,
            momentum_score=70.0,
        )
        _seed_score(
            session,
            ticker="BBB",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="HIGH_RISK",
            opportunity_score=55.0,
            risk_score=30.0,
            quality_score=40.0,
            valuation_score=50.0,
            momentum_score=60.0,
        )
        _seed_score(
            session,
            ticker="CCC",
            as_of_date=date(2026, 1, 1),
            strategy_name="growth_momentum",
            recommendation="AVOID",
            risk_category="SPECULATIVE",
            opportunity_score=25.0,
            risk_score=20.0,
            quality_score=30.0,
            valuation_score=40.0,
            momentum_score=50.0,
        )
        for ticker, start, end in [
            ("AAA", 100.0, 120.0),
            ("BBB", 100.0, 90.0),
            ("CCC", 100.0, 130.0),
        ]:
            _seed_price(session, ticker, date(2026, 1, 1), start)
            _seed_price(session, ticker, date(2026, 4, 3), end)

    filtered = client.get(
        "/scores/evaluation/strategies?horizon=90&recommendation=ACCUMULATE&min_opportunity_score=70&risk_category=MEDIUM_RISK"
    )
    assert filtered.status_code == 200
    payload = filtered.json()
    assert set(payload["strategies"]) == {"balanced"}
    balanced = payload["strategies"]["balanced"]
    assert balanced["count"] == 1
    assert balanced["available_count"] == 1

    missing_benchmark = client.get("/scores/evaluation/strategies?horizon=90&recommendation=WATCH")
    assert missing_benchmark.status_code == 200
    missing_payload = missing_benchmark.json()
    watched = missing_payload["strategies"]["balanced"]
    assert watched["benchmark_return"] is None
    assert watched["excess_return_vs_benchmark"] is None
