from __future__ import annotations

OUTCOME_OUTPERFORM = "OUTPERFORM"
OUTCOME_NEUTRAL = "NEUTRAL"
OUTCOME_UNDERPERFORM = "UNDERPERFORM"


def classify_outcome(excess_return: float | None) -> str | None:
    if excess_return is None:
        return None
    if excess_return >= 5.0:
        return OUTCOME_OUTPERFORM
    if excess_return <= -5.0:
        return OUTCOME_UNDERPERFORM
    return OUTCOME_NEUTRAL
