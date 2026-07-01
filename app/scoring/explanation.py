from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def build_explanation(
    summary: str,
    score_breakdown: dict[str, float],
    confidence: str,
    data_warnings: list[str],
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    safe_signals = [_json_safe(signal) for signal in signals]
    positive_signals: list[dict[str, Any]] = []
    negative_signals: list[dict[str, Any]] = []
    for signal in safe_signals:
        severity = str(signal.get("severity", "NEUTRAL"))
        if severity in {"STRONG_POSITIVE", "POSITIVE"}:
            positive_signals.append(signal)
        elif severity in {"NEGATIVE", "STRONG_NEGATIVE"}:
            negative_signals.append(signal)

    return {
        "summary": summary,
        "positive_signals": positive_signals,
        "negative_signals": negative_signals,
        "score_breakdown": score_breakdown,
        "confidence": confidence,
        "data_warnings": data_warnings,
        "signals": safe_signals,
        "generated_at": date.today().isoformat(),
    }
