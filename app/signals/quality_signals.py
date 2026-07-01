from __future__ import annotations

from collections.abc import Sequence
from statistics import mean

from app.db.models import Fundamental
from app.signals.base import SignalRecord, boolean_score, clamp, linear_score


def _growth_consistency(fundamentals: Sequence[Fundamental]) -> float | None:
    values = [row.revenue_growth for row in fundamentals if row.revenue_growth is not None]
    if not values:
        return None
    if len(values) < 3:
        return values[-1]
    avg = mean(values)
    spread = mean(abs(value - avg) for value in values)
    return clamp(1.0 - min(spread * 5.0, 1.0))


def build_quality_signals(fundamentals: Sequence[Fundamental]) -> list[SignalRecord]:
    latest = fundamentals[-1] if fundamentals else None
    growth_consistency = _growth_consistency(fundamentals)

    signals = [
        SignalRecord(
            name="revenue_growth_consistency",
            category="QUALITY",
            raw_value=growth_consistency,
            normalized_score=linear_score(growth_consistency, -0.1, 0.3, higher_is_better=True) if growth_consistency is not None else 50.0,
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM" if len(fundamentals) >= 3 else "LOW",
            source="internal",
            explanation="Revenue growth is stronger when recent fundamentals remain consistently positive.",
        ),
        SignalRecord(
            name="roe",
            category="QUALITY",
            raw_value=latest.return_on_equity if latest else None,
            normalized_score=linear_score(latest.return_on_equity if latest else None, -0.1, 0.4, higher_is_better=True),
            weight=0.30,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM" if latest else "LOW",
            source="internal",
            explanation="Return on equity rewards companies that generate more profit from shareholder capital.",
        ),
        SignalRecord(
            name="debt_to_equity",
            category="QUALITY",
            raw_value=latest.debt_to_equity if latest else None,
            normalized_score=linear_score(latest.debt_to_equity if latest else None, 0.0, 4.0, higher_is_better=False),
            weight=0.25,
            direction="LOWER_IS_BETTER",
            confidence="MEDIUM" if latest else "LOW",
            source="internal",
            explanation="Lower debt/equity supports balance-sheet flexibility.",
        ),
        SignalRecord(
            name="free_cash_flow_positive",
            category="QUALITY",
            raw_value=1.0 if latest and latest.free_cash_flow is not None and latest.free_cash_flow > 0 else 0.0 if latest else None,
            normalized_score=boolean_score(bool(latest and latest.free_cash_flow is not None and latest.free_cash_flow > 0)),
            weight=0.20,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM" if latest else "LOW",
            source="internal",
            explanation="Positive free cash flow indicates the business can self-fund operations and growth.",
        ),
    ]

    return signals
