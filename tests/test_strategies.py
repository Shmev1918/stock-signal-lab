from __future__ import annotations

from sqlmodel import Session, select

from app.config import get_settings
from app.db.models import StockScore
from app.db.session import engine
from app.scoring.strategy_profiles import get_strategy_profile
from app.signals.base import SignalRecord
from app.signals.signal_engine import SignalEngine


def test_strategies_endpoint_lists_profiles(client) -> None:
    response = client.get("/strategies")
    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload}
    assert names == {"balanced", "conservative_quality", "growth_momentum", "value_recovery"}


def test_default_strategy_comes_from_config(client, monkeypatch) -> None:
    monkeypatch.setenv("SCORING_STRATEGY", "growth_momentum")
    get_settings.cache_clear()

    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    response = client.post("/score/AAPL")
    assert response.status_code == 200
    assert response.json()["strategy_name"] == "growth_momentum"

    with Session(engine) as session:
        score = session.exec(select(StockScore).where(StockScore.ticker == "AAPL")).first()
        assert score is not None
        assert score.strategy_name == "growth_momentum"

    get_settings.cache_clear()


def test_strategy_override_is_persisted(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    response = client.post("/score/AAPL?strategy=conservative_quality")
    assert response.status_code == 200
    assert response.json()["strategy_name"] == "conservative_quality"

    with Session(engine) as session:
        score = session.exec(select(StockScore).where(StockScore.ticker == "AAPL")).first()
        assert score is not None
        assert score.strategy_name == "conservative_quality"


def test_strategy_profiles_change_opportunity_score() -> None:
    signals = [
        SignalRecord(
            name="volatility",
            category="RISK",
            raw_value=0.2,
            normalized_score=80.0,
            weight=0.55,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Lower volatility is better.",
        ),
        SignalRecord(
            name="max_drawdown",
            category="RISK",
            raw_value=0.3,
            normalized_score=70.0,
            weight=0.45,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Lower drawdown is better.",
        ),
        SignalRecord(
            name="revenue_growth_consistency",
            category="QUALITY",
            raw_value=1.0,
            normalized_score=100.0,
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Strong growth consistency.",
        ),
        SignalRecord(
            name="roe",
            category="QUALITY",
            raw_value=0.1,
            normalized_score=50.0,
            weight=0.30,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Moderate return on equity.",
        ),
        SignalRecord(
            name="debt_to_equity",
            category="QUALITY",
            raw_value=3.0,
            normalized_score=0.0,
            weight=0.25,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="High debt burden.",
        ),
        SignalRecord(
            name="free_cash_flow_positive",
            category="QUALITY",
            raw_value=1.0,
            normalized_score=0.0,
            weight=0.20,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="No free cash flow edge.",
        ),
        SignalRecord(
            name="pe_ratio",
            category="VALUATION",
            raw_value=20.0,
            normalized_score=50.0,
            weight=0.55,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Average valuation.",
        ),
        SignalRecord(
            name="price_to_sales",
            category="VALUATION",
            raw_value=5.0,
            normalized_score=50.0,
            weight=0.45,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Average sales multiple.",
        ),
        SignalRecord(
            name="return_3m",
            category="MOMENTUM",
            raw_value=0.1,
            normalized_score=50.0,
            weight=0.30,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Neutral short-term momentum.",
        ),
        SignalRecord(
            name="return_6m",
            category="MOMENTUM",
            raw_value=0.1,
            normalized_score=50.0,
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Neutral medium-term momentum.",
        ),
        SignalRecord(
            name="return_12m",
            category="MOMENTUM",
            raw_value=0.1,
            normalized_score=50.0,
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Neutral long-term momentum.",
        ),
        SignalRecord(
            name="ma_50_vs_200",
            category="MOMENTUM",
            raw_value=0.0,
            normalized_score=50.0,
            weight=0.20,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Neutral trend.",
        ),
    ]
    engine = SignalEngine()
    balanced = engine.opportunity_score(engine.category_scores(signals, get_strategy_profile("balanced")), "balanced")
    conservative = engine.opportunity_score(engine.category_scores(signals, get_strategy_profile("conservative_quality")), "conservative_quality")
    growth = engine.opportunity_score(engine.category_scores(signals, get_strategy_profile("growth_momentum")), "growth_momentum")

    assert len({balanced, conservative, growth}) >= 2
    assert conservative != growth
