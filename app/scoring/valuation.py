from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValuationInputs:
    pe_ratio: float | None = None
    forward_pe: float | None = None
    price_to_sales: float | None = None
    price_to_fcf: float | None = None
    historical_discount: float | None = None
    sector_relative_discount: float | None = None


def score_valuation(inputs: ValuationInputs) -> tuple[float, list[str], list[str]]:
    # TODO: calibrate with sector-aware historical baselines.
    score = 50.0
    positives: list[str] = []
    negatives: list[str] = []

    if inputs.pe_ratio is not None:
        if inputs.pe_ratio < 15:
            score += 15
            positives.append(f"pe_ratio={inputs.pe_ratio:.2f}")
        elif inputs.pe_ratio > 35:
            score -= 15
            negatives.append(f"pe_ratio={inputs.pe_ratio:.2f}")
    if inputs.forward_pe is not None:
        score += 10 if inputs.forward_pe < 20 else -10
    if inputs.price_to_sales is not None:
        score += 8 if inputs.price_to_sales < 5 else -8
    if inputs.price_to_fcf is not None:
        score += 10 if inputs.price_to_fcf < 25 else -10
    if inputs.historical_discount is not None:
        score += inputs.historical_discount * 15
    if inputs.sector_relative_discount is not None:
        score += inputs.sector_relative_discount * 10

    return max(0.0, min(100.0, score)), positives, negatives

