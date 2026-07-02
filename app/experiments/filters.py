from __future__ import annotations

from typing import Any

from app.db.models import StockScore, StockSignal


def normalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(filters or {})
    signal_name = normalized.get("signal_name")
    if signal_name == "momentum_3m":
        normalized["signal_name"] = "return_3m"
    elif signal_name == "momentum_6m":
        normalized["signal_name"] = "return_6m"
    elif signal_name == "momentum_12m":
        normalized["signal_name"] = "return_12m"
    return normalized


def _as_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else None


def score_matches_filters(score: StockScore, experiment_type: str, filters: dict[str, Any]) -> bool:
    if experiment_type == "strategy_score_threshold":
        threshold = filters.get("min_opportunity_score")
        if threshold is not None and score.opportunity_score < float(threshold):
            return False
    elif experiment_type == "recommendation_outcome":
        allowed = _as_list(filters.get("recommendations")) or _as_list(filters.get("recommendation"))
        if allowed and score.recommendation not in allowed:
            return False
    elif experiment_type == "risk_category_outcome":
        allowed = _as_list(filters.get("risk_categories")) or _as_list(filters.get("risk_category"))
        if allowed and score.risk_category not in allowed:
            return False
    return True


def signal_matches_filters(signal: StockSignal, filters: dict[str, Any]) -> bool:
    signal_name = filters.get("signal_name")
    if signal_name and signal.signal_name != signal_name:
        return False
    signal_category = filters.get("signal_category")
    if signal_category and signal.signal_category != signal_category:
        return False
    min_score = filters.get("min_normalized_score")
    if min_score is not None and signal.normalized_score < float(min_score):
        return False
    max_score = filters.get("max_normalized_score")
    if max_score is not None and signal.normalized_score > float(max_score):
        return False
    return True
