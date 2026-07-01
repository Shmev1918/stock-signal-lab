from __future__ import annotations


def recommend(opportunity: float, risk: float, valuation: float, quality: float, momentum: float) -> str:
    # TODO: learn thresholds from backtests.
    if opportunity >= 82 and quality >= 70 and risk >= 55:
        return "ACCUMULATE"
    if opportunity >= 72 and risk >= 45:
        return "STRONG_WATCH"
    if opportunity >= 60:
        return "WATCH"
    if opportunity >= 45:
        return "HOLD"
    if risk < 30:
        return "SPECULATIVE"
    return "AVOID"

