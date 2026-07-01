from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session

from app.db.models import DailyPrice, Experiment, ExperimentResult, Stock, StockScore, StockSignal
from app.db.session import engine
from app.experiments.outcome import OUTCOME_NEUTRAL, OUTCOME_OUTPERFORM, OUTCOME_UNDERPERFORM, classify_outcome


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


def _seed_stock_signal(
    session: Session,
    *,
    ticker: str,
    signal_date: date,
    signal_name: str,
    signal_category: str,
    normalized_score: float,
) -> None:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if stock is None:
        stock = Stock(ticker=ticker)
        session.add(stock)
        session.commit()
        session.refresh(stock)
    session.add(
        StockSignal(
            stock_id=stock.id or 0,
            signal_date=signal_date,
            signal_name=signal_name,
            signal_category=signal_category,
            raw_value=normalized_score,
            normalized_score=normalized_score,
            weight=0.5,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM",
            source="internal",
            explanation={"summary": "seeded"},
        )
    )
    session.commit()


def test_outcome_label_calculation() -> None:
    assert classify_outcome(5.0) == OUTCOME_OUTPERFORM
    assert classify_outcome(10.0) == OUTCOME_OUTPERFORM
    assert classify_outcome(0.0) == OUTCOME_NEUTRAL
    assert classify_outcome(-4.99) == OUTCOME_NEUTRAL
    assert classify_outcome(-5.0) == OUTCOME_UNDERPERFORM
    assert classify_outcome(None) is None


def test_strategy_score_threshold_experiment(client) -> None:
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
            opportunity_score=60.0,
        )
        _seed_price(session, "AAA", date(2026, 1, 1), 100.0)
        _seed_price(session, "AAA", date(2026, 6, 30), 120.0)
        _seed_price(session, "SPY", date(2026, 1, 1), 100.0)
        _seed_price(session, "SPY", date(2026, 6, 30), 110.0)

    response = client.post(
        "/experiments/run",
        json={
            "name": "balanced_high_opportunity_180d",
            "experiment_type": "strategy_score_threshold",
            "strategy_name": "balanced",
            "horizon_days": 180,
            "benchmark_ticker": "SPY",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "filters": {"min_opportunity_score": 70},
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["name"] == "balanced_high_opportunity_180d"
    assert payload["experiment_type"] == "strategy_score_threshold"
    assert payload["result_count"] == 1
    result = payload["results"][0]
    assert result["ticker"] == "AAA"
    assert result["status"] == "completed"
    assert result["outcome_label"] == OUTCOME_OUTPERFORM
    assert round(result["future_return"], 2) == 20.0
    assert round(result["benchmark_return"], 2) == 10.0
    assert round(result["excess_return"], 2) == 10.0

    summary = client.get(f"/experiments/{payload['id']}/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["total_observations"] == 1
    assert summary_payload["available_observations"] == 1
    assert summary_payload["outperform_count"] == 1
    assert summary_payload["best_result"]["ticker"] == "AAA"

    with Session(engine) as session:
        persisted = session.get(Experiment, payload["id"])
        assert persisted is not None
        rows = list(session.query(ExperimentResult).where(ExperimentResult.experiment_id == payload["id"]))  # type: ignore[attr-defined]
        assert rows


def test_recommendation_outcome_experiment_and_missing_future_data(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="ACC",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="ACCUMULATE",
            risk_category="MEDIUM_RISK",
            opportunity_score=85.0,
        )
        _seed_score(
            session,
            ticker="AVD",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="AVOID",
            risk_category="SPECULATIVE",
            opportunity_score=15.0,
        )
        _seed_score(
            session,
            ticker="MISS",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="MEDIUM_RISK",
            opportunity_score=50.0,
        )
        _seed_price(session, "ACC", date(2026, 1, 1), 100.0)
        _seed_price(session, "ACC", date(2026, 4, 1), 120.0)
        _seed_price(session, "AVD", date(2026, 1, 1), 100.0)
        _seed_price(session, "AVD", date(2026, 4, 1), 90.0)
        _seed_price(session, "MISS", date(2026, 1, 1), 100.0)
        _seed_price(session, "SPY", date(2026, 1, 1), 100.0)
        _seed_price(session, "SPY", date(2026, 4, 1), 100.0)

    response = client.post(
        "/experiments/run",
        json={
            "name": "recommendation_90d",
            "experiment_type": "recommendation_outcome",
            "strategy_name": "balanced",
            "horizon_days": 90,
            "benchmark_ticker": "SPY",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "filters": {"recommendations": ["ACCUMULATE", "AVOID"]},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result_count"] == 2
    assert {row["ticker"] for row in payload["results"]} == {"ACC", "AVD"}
    assert payload["results"][0]["status"] == "completed"

    with Session(engine) as session:
        row = session.exec(select(ExperimentResult).where(ExperimentResult.ticker == "MISS")).first()
        assert row is None


def test_signal_threshold_experiment(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="SIG1",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="ACCUMULATE",
            risk_category="MEDIUM_RISK",
            opportunity_score=75.0,
        )
        _seed_score(
            session,
            ticker="SIG2",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="MEDIUM_RISK",
            opportunity_score=55.0,
        )
        _seed_stock_signal(session, ticker="SIG1", signal_date=date(2026, 1, 1), signal_name="free_cash_flow_positive", signal_category="QUALITY", normalized_score=80.0)
        _seed_stock_signal(session, ticker="SIG2", signal_date=date(2026, 1, 1), signal_name="free_cash_flow_positive", signal_category="QUALITY", normalized_score=60.0)
        _seed_price(session, "SIG1", date(2026, 1, 1), 100.0)
        _seed_price(session, "SIG1", date(2026, 4, 1), 130.0)
        _seed_price(session, "SIG2", date(2026, 1, 1), 100.0)
        _seed_price(session, "SIG2", date(2026, 4, 1), 95.0)
        _seed_price(session, "SPY", date(2026, 1, 1), 100.0)
        _seed_price(session, "SPY", date(2026, 4, 1), 105.0)

    response = client.post(
        "/experiments/run",
        json={
            "name": "signal_threshold_test",
            "experiment_type": "signal_threshold",
            "strategy_name": "balanced",
            "horizon_days": 90,
            "benchmark_ticker": "SPY",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "filters": {
                "signal_name": "free_cash_flow_positive",
                "min_normalized_score": 70,
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result_count"] == 1
    assert payload["results"][0]["ticker"] == "SIG1"
    assert payload["results"][0]["outcome_label"] == OUTCOME_OUTPERFORM


def test_experiment_future_price_handling_and_no_leakage(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="LEAK",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="MEDIUM_RISK",
            opportunity_score=50.0,
        )
        _seed_price(session, "LEAK", date(2026, 1, 1), 100.0)
        _seed_price(session, "LEAK", date(2026, 6, 30), 110.0)
        _seed_price(session, "LEAK", date(2026, 7, 15), 150.0)
        _seed_price(session, "SPY", date(2026, 1, 1), 100.0)
        _seed_price(session, "SPY", date(2026, 6, 30), 105.0)
        _seed_price(session, "SPY", date(2026, 7, 15), 200.0)

    response = client.post(
        "/experiments/run",
        json={
            "name": "leak_check",
            "experiment_type": "strategy_score_threshold",
            "strategy_name": "balanced",
            "horizon_days": 180,
            "benchmark_ticker": "SPY",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "filters": {"min_opportunity_score": 40},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    result = payload["results"][0]
    assert result["future_price_date"] == "2026-06-30"
    assert round(result["future_return"], 2) == 10.0
    assert round(result["benchmark_return"], 2) == 5.0
    assert round(result["excess_return"], 2) == 5.0

