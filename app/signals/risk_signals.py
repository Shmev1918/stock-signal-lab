from __future__ import annotations

from collections.abc import Sequence
from statistics import mean

from app.db.models import DailyPrice, Fundamental
from app.signals.base import SignalRecord, clamp


def _returns(prices: Sequence[DailyPrice]) -> list[float]:
    values: list[float] = []
    for idx in range(1, len(prices)):
        prev = prices[idx - 1].close
        curr = prices[idx].close
        if prev > 0:
            values.append((curr - prev) / prev)
    return values


def _volatility(prices: Sequence[DailyPrice]) -> float | None:
    returns = _returns(prices)
    if len(returns) < 2:
        return None
    avg = mean(returns)
    variance = sum((value - avg) ** 2 for value in returns) / len(returns)
    return (variance**0.5) * (252**0.5)


def _max_drawdown(prices: Sequence[DailyPrice]) -> float | None:
    if len(prices) < 2:
        return None
    peak = prices[0].close
    worst = 0.0
    for row in prices:
        peak = max(peak, row.close)
        if peak > 0:
            worst = min(worst, (row.close - peak) / peak)
    return worst


def build_risk_signals(prices: Sequence[DailyPrice], fundamentals: Sequence[Fundamental]) -> list[SignalRecord]:
    volatility = _volatility(prices)
    drawdown = _max_drawdown(prices)
    signals = [
        SignalRecord(
            name="volatility",
            category="RISK",
            raw_value=volatility,
            normalized_score=clamp(100.0 - min((volatility or 0.0) * 250.0, 100.0)) if volatility is not None else 50.0,
            weight=0.55,
            direction="LOWER_IS_BETTER",
            confidence="MEDIUM" if len(prices) >= 90 else "LOW",
            source="internal",
            explanation="Annualized volatility is lower when the price series is calmer.",
        ),
        SignalRecord(
            name="max_drawdown",
            category="RISK",
            raw_value=drawdown,
            normalized_score=clamp(100.0 - min(abs(drawdown or 0.0) * 100.0, 100.0)) if drawdown is not None else 50.0,
            weight=0.45,
            direction="LOWER_IS_BETTER",
            confidence="MEDIUM" if len(prices) >= 90 else "LOW",
            source="internal",
            explanation="Maximum drawdown is smaller when the worst peak-to-trough decline is limited.",
        ),
    ]
    return signals
