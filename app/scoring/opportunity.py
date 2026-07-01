from __future__ import annotations

from app.scoring.strategy_profiles import StrategyProfile, get_strategy_profile


def score_opportunity(
    risk: float,
    quality: float,
    valuation: float,
    momentum: float,
    strategy: StrategyProfile | str | None = None,
) -> float:
    profile = get_strategy_profile(strategy) if isinstance(strategy, str) or strategy is None else strategy
    weights = profile.category_weights
    base = risk * weights["risk"] + quality * weights["quality"] + valuation * weights["valuation"] + momentum * weights["momentum"]
    bonus = 0.0
    if quality >= 70 and valuation >= 55 and risk >= 50:
        bonus += 10
    if momentum >= 60:
        bonus += 5
    return max(0.0, min(100.0, base + bonus))
