from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from sqlmodel import Session, select

from app.db.models import DailyPrice, Fundamental, Stock
from app.scoring.opportunity import score_opportunity
from app.scoring.recommendation import recommend
from app.scoring.summary import build_summary as build_analysis_summary
from app.scoring.strategy_profiles import StrategyProfile, get_strategy_profile
from app.signals.base import SignalRecord
from app.signals.momentum_signals import build_momentum_signals
from app.signals.quality_signals import build_quality_signals
from app.signals.risk_signals import build_risk_signals
from app.signals.valuation_signals import build_valuation_signals


class SignalEngine:
    def load_context(self, session: Session, ticker: str, as_of_date: date) -> tuple[Stock, list[DailyPrice], list[Fundamental]]:
        stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
        if stock is None:
            raise LookupError(f"Stock not found: {ticker}")

        prices = list(
            session.exec(
                select(DailyPrice)
                .where(DailyPrice.ticker == ticker, DailyPrice.price_date <= as_of_date)
                .order_by(DailyPrice.price_date)
            )
        )
        fundamentals = list(
            session.exec(
                select(Fundamental)
                .where(Fundamental.ticker == ticker, Fundamental.as_of_date <= as_of_date)
                .order_by(Fundamental.as_of_date)
            )
        )
        return stock, prices, fundamentals

    def generate(self, session: Session, ticker: str, as_of_date: date | None = None) -> list[SignalRecord]:
        as_of_date = as_of_date or date.today()
        _, prices, fundamentals = self.load_context(session, ticker, as_of_date)
        signals: list[SignalRecord] = []
        signals.extend(build_risk_signals(prices, fundamentals))
        signals.extend(build_quality_signals(fundamentals))
        signals.extend(build_valuation_signals(fundamentals))
        signals.extend(build_momentum_signals(prices))
        return signals

    @staticmethod
    def _effective_weight(signal: SignalRecord, strategy: StrategyProfile) -> float:
        return strategy.signal_weight(signal.category, signal.name, signal.weight)

    @staticmethod
    def category_scores(signals: Iterable[SignalRecord], strategy: StrategyProfile | str | None = None) -> dict[str, float]:
        profile = get_strategy_profile(strategy) if isinstance(strategy, str) or strategy is None else strategy
        grouped: dict[str, list[SignalRecord]] = defaultdict(list)
        for signal in signals:
            grouped[signal.category].append(signal)
        scores: dict[str, float] = {}
        for category, rows in grouped.items():
            weight_sum = sum(SignalEngine._effective_weight(row, profile) for row in rows)
            if weight_sum <= 0:
                scores[category.lower()] = 50.0
                continue
            scores[category.lower()] = round(
                sum(row.normalized_score * SignalEngine._effective_weight(row, profile) for row in rows) / weight_sum,
                2,
            )
        for category in ("risk", "quality", "valuation", "momentum"):
            scores.setdefault(category, 50.0)
        return scores

    @staticmethod
    def opportunity_score(scores: dict[str, float], strategy: StrategyProfile | str | None = None) -> float:
        return score_opportunity(scores["risk"], scores["quality"], scores["valuation"], scores["momentum"], strategy)

    @staticmethod
    def recommendation(scores: dict[str, float], opportunity_score: float) -> str:
        return recommend(opportunity_score, scores["risk"], scores["valuation"], scores["quality"], scores["momentum"])

    @staticmethod
    def risk_category(score: float) -> str:
        if score >= 75:
            return "STABLE"
        if score >= 50:
            return "MEDIUM_RISK"
        if score >= 25:
            return "HIGH_RISK"
        return "SPECULATIVE"

    @staticmethod
    def positive_negative_signals(signals: Iterable[SignalRecord]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        positives: list[dict[str, object]] = []
        negatives: list[dict[str, object]] = []
        for signal in signals:
            payload = signal.to_dict()
            if getattr(signal, "severity", "NEUTRAL") in {"STRONG_POSITIVE", "POSITIVE"}:
                positives.append(payload)
            elif getattr(signal, "severity", "NEUTRAL") in {"NEGATIVE", "STRONG_NEGATIVE"}:
                negatives.append(payload)
        return positives, negatives

    @staticmethod
    def build_summary(scores: dict[str, float], positives: list[dict[str, object]], negatives: list[dict[str, object]]) -> str:
        return build_analysis_summary(
            risk_category=SignalEngine.risk_category(scores["risk"]),
            positive_signals=positives,
            negative_signals=negatives,
            scores=scores,
        )
