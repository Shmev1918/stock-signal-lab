from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.db.models import Stock, StockScore, StockSignal
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


def _seed_signal(
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


def test_distribution_endpoint_numeric_percentiles(client) -> None:
    with Session(engine) as session:
        seed_values = [
            ("A", 10.0, 20.0, 30.0, 40.0, 50.0),
            ("B", 20.0, 30.0, 40.0, 50.0, 60.0),
            ("C", 30.0, 40.0, 50.0, 60.0, 70.0),
            ("D", 40.0, 50.0, 60.0, 70.0, 80.0),
        ]
        for ticker, opportunity, risk, quality, valuation, momentum in seed_values:
            _seed_score(
                session,
                ticker=ticker,
                as_of_date=date(2026, 1, 1),
                strategy_name="balanced",
                recommendation="ACCUMULATE",
                risk_category="MEDIUM_RISK",
                opportunity_score=opportunity,
                risk_score=risk,
                quality_score=quality,
                valuation_score=valuation,
                momentum_score=momentum,
            )

    response = client.get("/diagnostics/distributions?strategy_name=balanced")
    assert response.status_code == 200
    payload = response.json()

    opportunity = payload["scores"]["opportunity_score"]
    assert opportunity["count"] == 4
    assert opportunity["min"] == 10.0
    assert opportunity["max"] == 40.0
    assert opportunity["mean"] == 25.0
    assert opportunity["median"] == 25.0
    assert opportunity["p10"] == 13.0
    assert opportunity["p50"] == 25.0
    assert opportunity["p90"] == 37.0


def test_distribution_endpoint_categorical_counts(client) -> None:
    with Session(engine) as session:
        _seed_score(
            session,
            ticker="AAA",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="ACCUMULATE",
            risk_category="STABLE",
            opportunity_score=80.0,
            risk_score=20.0,
            quality_score=90.0,
            valuation_score=70.0,
            momentum_score=60.0,
        )
        _seed_score(
            session,
            ticker="BBB",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="WATCH",
            risk_category="MEDIUM_RISK",
            opportunity_score=55.0,
            risk_score=50.0,
            quality_score=60.0,
            valuation_score=50.0,
            momentum_score=40.0,
        )
        _seed_score(
            session,
            ticker="CCC",
            as_of_date=date(2026, 1, 1),
            strategy_name="balanced",
            recommendation="AVOID",
            risk_category="HIGH_RISK",
            opportunity_score=10.0,
            risk_score=80.0,
            quality_score=20.0,
            valuation_score=30.0,
            momentum_score=25.0,
        )

    response = client.get("/diagnostics/distributions?strategy_name=balanced")
    assert response.status_code == 200
    payload = response.json()

    assert payload["recommendations"] == {"ACCUMULATE": 1, "AVOID": 1, "WATCH": 1}
    assert payload["risk_categories"] == {"HIGH_RISK": 1, "MEDIUM_RISK": 1, "STABLE": 1}


def test_distribution_endpoint_signal_grouping(client) -> None:
    with Session(engine) as session:
        _seed_signal(session, ticker="AAA", signal_date=date(2026, 1, 1), signal_name="volatility", signal_category="RISK", normalized_score=0.0)
        _seed_signal(session, ticker="BBB", signal_date=date(2026, 1, 1), signal_name="volatility", signal_category="RISK", normalized_score=0.0)
        _seed_signal(session, ticker="AAA", signal_date=date(2026, 1, 1), signal_name="free_cash_flow_positive", signal_category="QUALITY", normalized_score=50.0)
        _seed_signal(session, ticker="BBB", signal_date=date(2026, 1, 1), signal_name="free_cash_flow_positive", signal_category="QUALITY", normalized_score=50.0)
        _seed_signal(session, ticker="AAA", signal_date=date(2026, 1, 1), signal_name="ma_50_vs_200", signal_category="MOMENTUM", normalized_score=10.0)
        _seed_signal(session, ticker="BBB", signal_date=date(2026, 1, 1), signal_name="ma_50_vs_200", signal_category="MOMENTUM", normalized_score=20.0)

    response = client.get("/diagnostics/distributions")
    assert response.status_code == 200
    payload = response.json()

    signals = payload["signals"]
    assert signals["volatility"]["always_0"] is True
    assert signals["free_cash_flow_positive"]["always_50"] is True
    assert signals["ma_50_vs_200"]["has_variation"] is True
    assert "ma_50_vs_200" in payload["signal_summary"]["has_variation"]
    assert "volatility" in payload["signal_summary"]["always_0"]
    assert "free_cash_flow_positive" in payload["signal_summary"]["always_50"]


def test_distribution_endpoint_empty_dataset(client) -> None:
    response = client.get("/diagnostics/distributions")
    assert response.status_code == 200
    payload = response.json()

    assert payload["counts"] == {"score_rows": 0, "signal_rows": 0}
    assert payload["scores"]["opportunity_score"]["count"] == 0
    assert payload["recommendations"] == {}
    assert payload["risk_categories"] == {}
    assert payload["signals"] == {}
