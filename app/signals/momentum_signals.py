from __future__ import annotations

from collections.abc import Sequence
from statistics import mean

from app.db.models import DailyPrice
from app.signals.base import SignalRecord, linear_score


def _price_returns(prices: Sequence[DailyPrice], window: int) -> float | None:
    if len(prices) <= window:
        return None
    start = prices[-(window + 1)].close
    end = prices[-1].close
    if start <= 0:
        return None
    return (end - start) / start


def _moving_average(prices: Sequence[DailyPrice], window: int) -> float | None:
    if len(prices) < window:
        return None
    return mean(row.close for row in prices[-window:])


def build_momentum_signals(prices: Sequence[DailyPrice]) -> list[SignalRecord]:
    ma_50 = _moving_average(prices, 50)
    ma_200 = _moving_average(prices, 200)
    ma_50_vs_200 = None
    if ma_50 is not None and ma_200 is not None and ma_200 > 0:
        ma_50_vs_200 = (ma_50 / ma_200) - 1.0

    return [
        SignalRecord(
            name="return_3m",
            category="MOMENTUM",
            raw_value=_price_returns(prices, 63),
            normalized_score=linear_score(_price_returns(prices, 63), -0.3, 0.3, higher_is_better=True),
            weight=0.30,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM" if len(prices) >= 90 else "LOW",
            source="internal",
            explanation="Three-month return shows short-term trend direction.",
        ),
        SignalRecord(
            name="return_6m",
            category="MOMENTUM",
            raw_value=_price_returns(prices, 126),
            normalized_score=linear_score(_price_returns(prices, 126), -0.4, 0.4, higher_is_better=True),
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM" if len(prices) >= 180 else "LOW",
            source="internal",
            explanation="Six-month return helps separate sustained trend from noise.",
        ),
        SignalRecord(
            name="return_12m",
            category="MOMENTUM",
            raw_value=_price_returns(prices, 252),
            normalized_score=linear_score(_price_returns(prices, 252), -0.6, 0.8, higher_is_better=True),
            weight=0.25,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM" if len(prices) >= 300 else "LOW",
            source="internal",
            explanation="Twelve-month return captures longer trend persistence.",
        ),
        SignalRecord(
            name="ma_50_vs_200",
            category="MOMENTUM",
            raw_value=ma_50_vs_200,
            normalized_score=linear_score(ma_50_vs_200, -0.25, 0.25, higher_is_better=True),
            weight=0.20,
            direction="HIGHER_IS_BETTER",
            confidence="MEDIUM" if ma_200 is not None else "LOW",
            source="internal",
            explanation="A 50-day average above the 200-day average suggests a healthier trend.",
        ),
    ]
