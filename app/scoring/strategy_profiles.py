from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyProfile:
    name: str
    description: str
    category_weights: dict[str, float]
    signal_weight_overrides: dict[str, dict[str, float]] = field(default_factory=dict)

    def signal_weight(self, category: str, signal_name: str, default_weight: float) -> float:
        return self.signal_weight_overrides.get(category.upper(), {}).get(signal_name, default_weight)


STRATEGY_PROFILES: dict[str, StrategyProfile] = {
    "balanced": StrategyProfile(
        name="balanced",
        description="General-purpose default with even attention to quality, valuation, momentum, and risk.",
        category_weights={"risk": 0.25, "quality": 0.30, "valuation": 0.20, "momentum": 0.15},
    ),
    "conservative_quality": StrategyProfile(
        name="conservative_quality",
        description="Prioritizes stability, cash flow, and low debt while de-emphasizing momentum and valuation.",
        category_weights={"risk": 0.35, "quality": 0.40, "valuation": 0.10, "momentum": 0.10},
        signal_weight_overrides={
            "RISK": {"volatility": 0.70, "max_drawdown": 0.30},
            "QUALITY": {
                "revenue_growth_consistency": 0.15,
                "roe": 0.30,
                "debt_to_equity": 0.30,
                "free_cash_flow_positive": 0.25,
            },
        },
    ),
    "growth_momentum": StrategyProfile(
        name="growth_momentum",
        description="Prioritizes growth and momentum while tolerating higher valuation and risk.",
        category_weights={"risk": 0.15, "quality": 0.25, "valuation": 0.10, "momentum": 0.40},
        signal_weight_overrides={
            "QUALITY": {
                "revenue_growth_consistency": 0.35,
                "roe": 0.20,
                "debt_to_equity": 0.15,
                "free_cash_flow_positive": 0.30,
            },
            "MOMENTUM": {
                "return_3m": 0.20,
                "return_6m": 0.25,
                "return_12m": 0.35,
                "ma_50_vs_200": 0.20,
            },
        },
    ),
    "value_recovery": StrategyProfile(
        name="value_recovery",
        description="Prioritizes lower valuation and improving momentum as the core recovery signal.",
        category_weights={"risk": 0.20, "quality": 0.25, "valuation": 0.35, "momentum": 0.20},
        signal_weight_overrides={
            "VALUATION": {"pe_ratio": 0.55, "price_to_sales": 0.45},
            "MOMENTUM": {
                "return_3m": 0.25,
                "return_6m": 0.25,
                "return_12m": 0.25,
                "ma_50_vs_200": 0.25,
            },
        },
    ),
}


def get_strategy_profile(name: str | None) -> StrategyProfile:
    key = (name or "balanced").lower()
    if key not in STRATEGY_PROFILES:
        raise LookupError(f"Unknown strategy: {name}")
    return STRATEGY_PROFILES[key]


def list_strategy_profiles() -> list[StrategyProfile]:
    return list(STRATEGY_PROFILES.values())
