from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskInputs:
    volatility: float | None = None
    beta: float | None = None
    max_drawdown: float | None = None
    downside_deviation: float | None = None
    debt_to_equity: float | None = None
    earnings_inconsistency: float | None = None


def score_risk(inputs: RiskInputs) -> tuple[float, str, list[str]]:
    # TODO: replace placeholder thresholds with tuned formulas.
    score = 100.0
    signals: list[str] = []

    if inputs.volatility is not None:
        score -= min(max(inputs.volatility * 120, 0), 25)
        signals.append(f"volatility={inputs.volatility:.3f}")
    if inputs.beta is not None:
        score -= min(max(abs(inputs.beta - 1) * 12, 0), 15)
        signals.append(f"beta={inputs.beta:.2f}")
    if inputs.max_drawdown is not None:
        score -= min(max(abs(inputs.max_drawdown) * 100, 0), 20)
        signals.append(f"max_drawdown={inputs.max_drawdown:.2f}")
    if inputs.downside_deviation is not None:
        score -= min(max(inputs.downside_deviation * 120, 0), 10)
    if inputs.debt_to_equity is not None:
        score -= min(max(inputs.debt_to_equity * 4, 0), 20)
    if inputs.earnings_inconsistency is not None:
        score -= min(max(inputs.earnings_inconsistency * 20, 0), 10)

    score = max(0.0, min(100.0, score))
    if score >= 75:
        category = "STABLE"
    elif score >= 50:
        category = "MEDIUM_RISK"
    elif score >= 25:
        category = "HIGH_RISK"
    else:
        category = "SPECULATIVE"
    return score, category, signals

