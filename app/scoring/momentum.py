from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MomentumInputs:
    return_3m: float | None = None
    return_6m: float | None = None
    return_12m: float | None = None
    ma_50_vs_200: float | None = None
    distance_from_52w_high: float | None = None
    volume_trend: float | None = None


def score_momentum(inputs: MomentumInputs) -> tuple[float, list[str], list[str]]:
    # TODO: replace with a proper normalized momentum model.
    score = 50.0
    positives: list[str] = []
    negatives: list[str] = []

    for label, value, scale in [
        ("return_3m", inputs.return_3m, 20),
        ("return_6m", inputs.return_6m, 15),
        ("return_12m", inputs.return_12m, 10),
        ("ma_50_vs_200", inputs.ma_50_vs_200, 15),
        ("volume_trend", inputs.volume_trend, 5),
    ]:
        if value is None:
            continue
        score += max(min(value * scale, scale), -scale)
        if value >= 0:
            positives.append(f"{label}={value:.2f}")
        else:
            negatives.append(f"{label}={value:.2f}")

    if inputs.distance_from_52w_high is not None:
        score += max(min((0.25 - inputs.distance_from_52w_high) * 20, 10), -10)

    return max(0.0, min(100.0, score)), positives, negatives

