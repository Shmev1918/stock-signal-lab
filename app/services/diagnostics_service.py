from __future__ import annotations

from collections import Counter, defaultdict
from math import floor, ceil
from statistics import median
from typing import Any

from sqlmodel import Session, select

from app.db.models import StockScore, StockSignal


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    position = (len(ordered) - 1) * (percentile / 100.0)
    lower = floor(position)
    upper = ceil(position)
    if lower == upper:
        return float(ordered[int(position)])
    lower_value = ordered[lower]
    upper_value = ordered[upper]
    weight = position - lower
    return float(lower_value + (upper_value - lower_value) * weight)


def _numeric_distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "available_count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "p10": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
        }
    ordered = sorted(float(value) for value in values)
    count = len(ordered)
    return {
        "count": count,
        "available_count": count,
        "min": float(min(ordered)),
        "max": float(max(ordered)),
        "mean": float(sum(ordered) / count),
        "median": float(median(ordered)),
        "p10": _percentile(ordered, 10),
        "p25": _percentile(ordered, 25),
        "p50": _percentile(ordered, 50),
        "p75": _percentile(ordered, 75),
        "p90": _percentile(ordered, 90),
    }


def _categorical_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _score_rows(
    session: Session,
    strategy_name: str | None = None,
) -> list[StockScore]:
    stmt = select(StockScore)
    if strategy_name is not None:
        stmt = stmt.where(StockScore.strategy_name == strategy_name)
    stmt = stmt.order_by(StockScore.as_of_date.asc(), StockScore.created_at.asc(), StockScore.id.asc())
    return list(session.exec(stmt))


def _signal_rows(
    session: Session,
    signal_name: str | None = None,
    signal_category: str | None = None,
) -> list[StockSignal]:
    stmt = select(StockSignal)
    if signal_name is not None:
        stmt = stmt.where(StockSignal.signal_name == signal_name)
    if signal_category is not None:
        stmt = stmt.where(StockSignal.signal_category == signal_category)
    stmt = stmt.order_by(StockSignal.signal_name.asc(), StockSignal.signal_date.asc(), StockSignal.created_at.asc(), StockSignal.id.asc())
    return list(session.exec(stmt))


def _signal_distribution(signal_name: str, rows: list[StockSignal]) -> dict[str, Any]:
    scores = [float(row.normalized_score) for row in rows if row.normalized_score is not None]
    stats = _numeric_distribution(scores)
    stats.update(
        {
            "signal_name": signal_name,
            "signal_category": rows[0].signal_category if rows else None,
            "always_0": bool(scores) and all(score == 0 for score in scores),
            "always_50": bool(scores) and all(score == 50 for score in scores),
            "always_100": bool(scores) and all(score == 100 for score in scores),
            "has_variation": len(set(scores)) > 1 if scores else False,
        }
    )
    return stats


def _score_distribution_scores(rows: list[StockScore], field_name: str) -> dict[str, Any]:
    values = [float(getattr(row, field_name)) for row in rows if getattr(row, field_name) is not None]
    return _numeric_distribution(values)


def get_distribution_diagnostics(
    session: Session,
    strategy_name: str | None = None,
    signal_name: str | None = None,
    signal_category: str | None = None,
) -> dict[str, Any]:
    scores = _score_rows(session, strategy_name=strategy_name)
    signals = _signal_rows(session, signal_name=signal_name, signal_category=signal_category)

    score_fields = {
        "opportunity_score": "opportunity_score",
        "risk_score": "risk_score",
        "quality_score": "quality_score",
        "valuation_score": "valuation_score",
        "momentum_score": "momentum_score",
    }

    score_distributions = {name: _score_distribution_scores(scores, field) for name, field in score_fields.items()}
    recommendations = _categorical_counts([row.recommendation for row in scores])
    risk_categories = _categorical_counts([row.risk_category for row in scores])

    grouped_signals: dict[str, list[StockSignal]] = defaultdict(list)
    for row in signals:
        grouped_signals[row.signal_name].append(row)

    signal_distributions = {
        name: _signal_distribution(name, rows)
        for name, rows in sorted(grouped_signals.items())
    }

    signal_summary = {
        "always_0": sorted(name for name, data in signal_distributions.items() if data["always_0"]),
        "always_50": sorted(name for name, data in signal_distributions.items() if data["always_50"]),
        "always_100": sorted(name for name, data in signal_distributions.items() if data["always_100"]),
        "has_variation": sorted(name for name, data in signal_distributions.items() if data["has_variation"]),
    }

    return {
        "filters": {
            "strategy_name": strategy_name,
            "signal_name": signal_name,
            "signal_category": signal_category,
        },
        "scores": score_distributions,
        "recommendations": recommendations,
        "risk_categories": risk_categories,
        "signals": signal_distributions,
        "signal_summary": signal_summary,
        "counts": {
            "score_rows": len(scores),
            "signal_rows": len(signals),
        },
    }
