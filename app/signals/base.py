from __future__ import annotations

from dataclasses import dataclass, asdict


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def signal_severity(normalized_score: float | None) -> str:
    if normalized_score is None:
        return "NEUTRAL"
    if normalized_score >= 80:
        return "STRONG_POSITIVE"
    if normalized_score >= 60:
        return "POSITIVE"
    if normalized_score >= 40:
        return "NEUTRAL"
    if normalized_score >= 20:
        return "NEGATIVE"
    return "STRONG_NEGATIVE"


def linear_score(value: float | None, low: float, high: float, higher_is_better: bool = True) -> float:
    if value is None:
        return 50.0
    if high == low:
        return 50.0
    ratio = (value - low) / (high - low)
    score = clamp(ratio * 100.0)
    return score if higher_is_better else 100.0 - score


def boolean_score(value: bool | None) -> float:
    if value is None:
        return 50.0
    return 100.0 if value else 0.0


@dataclass(frozen=True)
class SignalRecord:
    name: str
    category: str
    raw_value: float | None
    normalized_score: float
    weight: float
    direction: str
    confidence: str
    source: str
    explanation: str

    @property
    def severity(self) -> str:
        return signal_severity(self.normalized_score)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["normalized_score"] = round(float(self.normalized_score), 2)
        data["weight"] = round(float(self.weight), 4)
        data["severity"] = self.severity
        return data
