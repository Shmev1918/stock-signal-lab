from __future__ import annotations

from app.scoring.strategy_profiles import get_strategy_profile
from app.signals.base import SignalRecord
from app.signals.signal_engine import SignalEngine


def _prepare_analysis_data(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")


def test_compare_strategies_returns_all_profiles(client) -> None:
    _prepare_analysis_data(client)

    response = client.get("/analysis/AAPL/compare-strategies")
    assert response.status_code == 200
    payload = response.json()

    assert [item["strategy_name"] for item in payload] == [
        "balanced",
        "conservative_quality",
        "growth_momentum",
        "value_recovery",
    ]
    assert all(item["positive_signals"] and item["negative_signals"] is not None for item in payload)
    assert all(len(item["positive_signals"]) <= 3 for item in payload)
    assert all(len(item["negative_signals"]) <= 3 for item in payload)
    assert all(item["summary"] for item in payload)


def test_compare_strategies_returns_selected_profiles_in_order(client) -> None:
    _prepare_analysis_data(client)

    response = client.get("/analysis/AAPL/compare-strategies?strategies=value_recovery,balanced")
    assert response.status_code == 200
    payload = response.json()

    assert [item["strategy_name"] for item in payload] == ["value_recovery", "balanced"]


def test_compare_strategies_reuses_existing_signal_set(client, monkeypatch) -> None:
    _prepare_analysis_data(client)

    import app.services.signal_service as signal_service_module

    def _fail(*args, **kwargs):  # pragma: no cover - executed only if regression occurs
        raise AssertionError("compare-strategies should not regenerate signals when they already exist")

    monkeypatch.setattr(signal_service_module, "generate_signals", _fail)

    response = client.get("/analysis/AAPL/compare-strategies")
    assert response.status_code == 200
    assert response.json()


def test_strategy_profiles_can_produce_different_opportunity_scores() -> None:
    signals = [
        SignalRecord(
            name="volatility",
            category="RISK",
            raw_value=0.2,
            normalized_score=90.0,
            weight=0.55,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Low volatility.",
        ),
        SignalRecord(
            name="max_drawdown",
            category="RISK",
            raw_value=0.15,
            normalized_score=85.0,
            weight=0.45,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Low drawdown.",
        ),
        SignalRecord(
            name="revenue_growth_consistency",
            category="QUALITY",
            raw_value=0.9,
            normalized_score=95.0,
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Strong growth consistency.",
        ),
        SignalRecord(
            name="roe",
            category="QUALITY",
            raw_value=0.2,
            normalized_score=65.0,
            weight=0.30,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Solid ROE.",
        ),
        SignalRecord(
            name="debt_to_equity",
            category="QUALITY",
            raw_value=2.0,
            normalized_score=35.0,
            weight=0.25,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Moderate debt.",
        ),
        SignalRecord(
            name="free_cash_flow_positive",
            category="QUALITY",
            raw_value=1.0,
            normalized_score=100.0,
            weight=0.20,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Positive FCF.",
        ),
        SignalRecord(
            name="pe_ratio",
            category="VALUATION",
            raw_value=45.0,
            normalized_score=15.0,
            weight=0.55,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Rich valuation.",
        ),
        SignalRecord(
            name="price_to_sales",
            category="VALUATION",
            raw_value=12.0,
            normalized_score=20.0,
            weight=0.45,
            direction="LOWER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Rich sales multiple.",
        ),
        SignalRecord(
            name="return_3m",
            category="MOMENTUM",
            raw_value=0.3,
            normalized_score=85.0,
            weight=0.30,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Strong 3m momentum.",
        ),
        SignalRecord(
            name="return_6m",
            category="MOMENTUM",
            raw_value=0.25,
            normalized_score=80.0,
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Strong 6m momentum.",
        ),
        SignalRecord(
            name="return_12m",
            category="MOMENTUM",
            raw_value=0.2,
            normalized_score=75.0,
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Strong 12m momentum.",
        ),
        SignalRecord(
            name="ma_50_vs_200",
            category="MOMENTUM",
            raw_value=0.1,
            normalized_score=70.0,
            weight=0.20,
            direction="HIGHER_IS_BETTER",
            confidence="HIGH",
            source="internal",
            explanation="Bullish trend.",
        ),
    ]

    engine = SignalEngine()
    balanced = engine.opportunity_score(engine.category_scores(signals, get_strategy_profile("balanced")), "balanced")
    conservative = engine.opportunity_score(
        engine.category_scores(signals, get_strategy_profile("conservative_quality")),
        "conservative_quality",
    )
    growth = engine.opportunity_score(engine.category_scores(signals, get_strategy_profile("growth_momentum")), "growth_momentum")

    assert len({balanced, conservative, growth}) >= 2
