from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.config import get_settings
from app.constants import SCORING_MODEL_VERSION, SIGNAL_MODEL_VERSION
from app.db.models import Recommendation, StockScore
from app.scoring.explanation import build_explanation
from app.scoring.summary import build_summary
from app.scoring.strategy_profiles import get_strategy_profile
from app.services.signal_service import generate_signals, signal_dicts
from app.services.stock_service import get_latest_signals
from app.signals.signal_engine import SignalEngine


def _ensure_signals(session: Session, ticker: str, as_of_date: date) -> list[dict[str, object]]:
    latest_signals = get_latest_signals(session, ticker)
    if latest_signals:
        return signal_dicts(latest_signals)
    generated = generate_signals(session, ticker, as_of_date=as_of_date)
    return signal_dicts(generated)


def score_ticker(session: Session, ticker: str, as_of_date: date | None = None, strategy_name: str | None = None) -> StockScore:
    as_of_date = as_of_date or date.today()
    selected_strategy = strategy_name or get_settings().scoring_strategy
    profile = get_strategy_profile(selected_strategy)
    signals = _ensure_signals(session, ticker, as_of_date)
    engine = SignalEngine()
    signal_views = [SignalView(signal) for signal in signals]
    category_scores = engine.category_scores(signal_views, profile)
    opportunity_score = engine.opportunity_score(category_scores, profile)
    recommendation_label = engine.recommendation(category_scores, opportunity_score)
    risk_category = engine.risk_category(category_scores["risk"])
    positives, negatives = engine.positive_negative_signals(signal_views)
    summary = build_summary(risk_category, positives, negatives, category_scores)

    explanation = build_explanation(
        summary=summary,
        score_breakdown={
            "risk": round(category_scores["risk"], 2),
            "quality": round(category_scores["quality"], 2),
            "valuation": round(category_scores["valuation"], 2),
            "momentum": round(category_scores["momentum"], 2),
            "opportunity": round(opportunity_score, 2),
        },
        confidence="LOW" if not signals else "MEDIUM" if len(signals) < 6 else "HIGH",
        data_warnings=[
            "Signals are generated from locally stored price and fundamental data.",
            "Signal formulas are intentionally simple and should be tuned over time.",
        ],
        signals=signals,
    )

    score = StockScore(
        ticker=ticker,
        as_of_date=as_of_date,
        risk_score=category_scores["risk"],
        quality_score=category_scores["quality"],
        valuation_score=category_scores["valuation"],
        momentum_score=category_scores["momentum"],
        opportunity_score=opportunity_score,
        risk_category=risk_category,
        recommendation=recommendation_label,
        explanation=explanation,
        source="internal",
        scoring_model_version=SCORING_MODEL_VERSION,
        signal_model_version=SIGNAL_MODEL_VERSION,
        strategy_name=profile.name,
    )
    session.add(score)
    session.add(
        Recommendation(
            ticker=ticker,
            as_of_date=as_of_date,
            label=recommendation_label,
            explanation=explanation,
        )
    )
    session.commit()
    session.refresh(score)
    return score


class SignalView:
    def __init__(self, data: dict[str, object]):
        self.name = data["signal_name"]
        self.category = data["signal_category"]
        self.raw_value = data["raw_value"]
        self.normalized_score = data["normalized_score"]
        self.severity = data.get("severity", "NEUTRAL")
        self.weight = data["weight"]
        self.direction = data["direction"]
        self.confidence = data["confidence"]
        self.source = data["source"]
        self.explanation = data["explanation"]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "category": self.category,
            "raw_value": self.raw_value,
            "normalized_score": self.normalized_score,
            "severity": self.severity,
            "weight": self.weight,
            "direction": self.direction,
            "confidence": self.confidence,
            "source": self.source,
            "explanation": self.explanation,
        }
