from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityInputs:
    revenue_growth_consistency: float | None = None
    gross_margin_stability: float | None = None
    operating_margin_stability: float | None = None
    free_cash_flow_strength: float | None = None
    return_on_equity: float | None = None
    debt_to_equity: float | None = None
    interest_coverage: float | None = None


def score_quality(inputs: QualityInputs) -> tuple[float, list[str], list[str]]:
    # TODO: tune against historical performance.
    score = 50.0
    positives: list[str] = []
    negatives: list[str] = []

    if inputs.revenue_growth_consistency is not None:
        score += inputs.revenue_growth_consistency * 20
        positives.append(f"revenue_growth_consistency={inputs.revenue_growth_consistency:.2f}")
    if inputs.gross_margin_stability is not None:
        score += inputs.gross_margin_stability * 10
    if inputs.operating_margin_stability is not None:
        score += inputs.operating_margin_stability * 10
    if inputs.free_cash_flow_strength is not None:
        score += inputs.free_cash_flow_strength * 15
    if inputs.return_on_equity is not None:
        score += inputs.return_on_equity * 20
        positives.append(f"roe={inputs.return_on_equity:.2f}")
    if inputs.debt_to_equity is not None:
        score -= min(inputs.debt_to_equity * 5, 20)
        negatives.append(f"debt_to_equity={inputs.debt_to_equity:.2f}")
    if inputs.interest_coverage is not None and inputs.interest_coverage < 3:
        score -= 10
        negatives.append(f"interest_coverage={inputs.interest_coverage:.2f}")

    return max(0.0, min(100.0, score)), positives, negatives

