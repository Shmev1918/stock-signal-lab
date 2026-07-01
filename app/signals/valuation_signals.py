from __future__ import annotations

from app.db.models import Fundamental
from app.signals.base import SignalRecord, linear_score


def build_valuation_signals(fundamentals: list[Fundamental]) -> list[SignalRecord]:
    latest = fundamentals[-1] if fundamentals else None
    pe_ratio = latest.pe_ratio if latest else None
    price_to_sales = latest.price_to_sales if latest else None

    return [
        SignalRecord(
            name="pe_ratio",
            category="VALUATION",
            raw_value=pe_ratio,
            normalized_score=linear_score(pe_ratio, 8.0, 45.0, higher_is_better=False),
            weight=0.55,
            direction="LOWER_IS_BETTER",
            confidence="MEDIUM" if latest else "LOW",
            source="internal",
            explanation="Lower P/E usually implies a cheaper earnings multiple.",
        ),
        SignalRecord(
            name="price_to_sales",
            category="VALUATION",
            raw_value=price_to_sales,
            normalized_score=linear_score(price_to_sales, 1.0, 15.0, higher_is_better=False),
            weight=0.45,
            direction="LOWER_IS_BETTER",
            confidence="MEDIUM" if latest else "LOW",
            source="internal",
            explanation="Lower price-to-sales can indicate a more conservative valuation.",
        ),
    ]
