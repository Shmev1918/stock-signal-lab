from __future__ import annotations

from datetime import timedelta
from statistics import median

from sqlmodel import Session

from app.db.models import StockScore
from app.services.stock_service import get_price_on_or_after, get_score_history_all


def _summary_statistics(values: list[float]) -> dict[str, object]:
    if not values:
        return {
            "count": 0,
            "available_count": 0,
            "average_return": None,
            "median_return": None,
            "win_rate": None,
            "best_return": None,
            "worst_return": None,
        }
    winning = [value for value in values if value > 0]
    return {
        "count": len(values),
        "available_count": len(values),
        "average_return": sum(values) / len(values),
        "median_return": median(values),
        "win_rate": len(winning) / len(values),
        "best_return": max(values),
        "worst_return": min(values),
    }


def _compute_horizon_return(session: Session, score: StockScore, horizon_days: int) -> dict[str, object]:
    scored_at = score.as_of_date
    start_price = get_price_on_or_after(session, score.ticker, scored_at)
    if start_price is None:
        return {
            "ticker": score.ticker,
            "scored_at": scored_at,
            "strategy_name": score.strategy_name,
            "recommendation": score.recommendation,
            "risk_category": score.risk_category,
            "opportunity_score": score.opportunity_score,
            "horizon_days": horizon_days,
            "horizon_return": None,
            "horizon_price_date": None,
        }
    target_date = scored_at + timedelta(days=horizon_days)
    horizon_price = get_price_on_or_after(session, score.ticker, target_date)
    if horizon_price is None:
        return {
            "ticker": score.ticker,
            "scored_at": scored_at,
            "strategy_name": score.strategy_name,
            "recommendation": score.recommendation,
            "risk_category": score.risk_category,
            "opportunity_score": score.opportunity_score,
            "horizon_days": horizon_days,
            "horizon_return": None,
            "horizon_price_date": None,
        }
    horizon_return = ((horizon_price.close - start_price.close) / start_price.close) * 100.0 if start_price.close else None
    return {
        "ticker": score.ticker,
        "scored_at": scored_at,
        "strategy_name": score.strategy_name,
        "recommendation": score.recommendation,
        "risk_category": score.risk_category,
        "opportunity_score": score.opportunity_score,
        "horizon_days": horizon_days,
        "horizon_return": horizon_return,
        "horizon_price_date": horizon_price.price_date,
    }


def _grouped_stats(rows: list[dict[str, object]], key: str) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        value = row.get("horizon_return")
        if value is None:
            continue
        grouped.setdefault(str(row.get(key)), []).append(float(value))
    return {group: _summary_statistics(values) for group, values in grouped.items()}


def get_score_evaluation(
    session: Session,
    horizon_days: int = 90,
    strategy_name: str | None = None,
    recommendation: str | None = None,
) -> dict[str, object]:
    scores = get_score_history_all(
        session,
        strategy_name=strategy_name,
        recommendation=recommendation,
    )
    rows = [_compute_horizon_return(session, score, horizon_days) for score in scores]
    available_returns = [float(row["horizon_return"]) for row in rows if row.get("horizon_return") is not None]
    return {
        "horizon": horizon_days,
        "count": len(rows),
        "available_count": len(available_returns),
        "groups": {
            "recommendation": _grouped_stats(rows, "recommendation"),
            "risk_category": _grouped_stats(rows, "risk_category"),
            "strategy_name": _grouped_stats(rows, "strategy_name"),
        },
        "details": rows,
    }


def _benchmark_return(session: Session, score: StockScore, horizon_days: int, benchmark_ticker: str = "SPY") -> float | None:
    start_price = get_price_on_or_after(session, benchmark_ticker, score.as_of_date)
    if start_price is None:
        return None
    target_date = score.as_of_date + timedelta(days=horizon_days)
    horizon_price = get_price_on_or_after(session, benchmark_ticker, target_date)
    if horizon_price is None or not start_price.close:
        return None
    return ((horizon_price.close - start_price.close) / start_price.close) * 100.0


def _strategy_group_stats(rows: list[dict[str, object]]) -> dict[str, object]:
    returns = [float(row["horizon_return"]) for row in rows if row.get("horizon_return") is not None]
    benchmark_returns = [float(row["benchmark_return"]) for row in rows if row.get("benchmark_return") is not None]
    opportunity_scores = [float(row["opportunity_score"]) for row in rows if row.get("opportunity_score") is not None]
    risk_scores = [float(row["risk_score"]) for row in rows if row.get("risk_score") is not None]
    quality_scores = [float(row["quality_score"]) for row in rows if row.get("quality_score") is not None]
    valuation_scores = [float(row["valuation_score"]) for row in rows if row.get("valuation_score") is not None]
    momentum_scores = [float(row["momentum_score"]) for row in rows if row.get("momentum_score") is not None]

    stats = _summary_statistics(returns)
    benchmark_return = (sum(benchmark_returns) / len(benchmark_returns)) if benchmark_returns else None
    return {
        "count": len(rows),
        "available_count": len(returns),
        "average_return": stats["average_return"],
        "median_return": stats["median_return"],
        "win_rate": stats["win_rate"],
        "best_return": stats["best_return"],
        "worst_return": stats["worst_return"],
        "average_opportunity_score": (sum(opportunity_scores) / len(opportunity_scores)) if opportunity_scores else None,
        "average_risk_score": (sum(risk_scores) / len(risk_scores)) if risk_scores else None,
        "average_quality_score": (sum(quality_scores) / len(quality_scores)) if quality_scores else None,
        "average_valuation_score": (sum(valuation_scores) / len(valuation_scores)) if valuation_scores else None,
        "average_momentum_score": (sum(momentum_scores) / len(momentum_scores)) if momentum_scores else None,
        "benchmark_return": benchmark_return,
        "excess_return_vs_benchmark": (stats["average_return"] - benchmark_return) if stats["average_return"] is not None and benchmark_return is not None else None,
    }


def get_score_strategy_evaluation(
    session: Session,
    horizon_days: int = 90,
    recommendation: str | None = None,
    min_opportunity_score: float | None = None,
    risk_category: str | None = None,
) -> dict[str, object]:
    scores = get_score_history_all(
        session,
        recommendation=recommendation,
    )
    rows: list[dict[str, object]] = []
    for score in scores:
        if min_opportunity_score is not None and score.opportunity_score < min_opportunity_score:
            continue
        if risk_category is not None and score.risk_category != risk_category:
            continue
        horizon_row = _compute_horizon_return(session, score, horizon_days)
        horizon_row["benchmark_return"] = _benchmark_return(session, score, horizon_days)
        horizon_row["risk_score"] = score.risk_score
        horizon_row["quality_score"] = score.quality_score
        horizon_row["valuation_score"] = score.valuation_score
        horizon_row["momentum_score"] = score.momentum_score
        rows.append(horizon_row)

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["strategy_name"]), []).append(row)

    return {
        "horizon": horizon_days,
        "count": len(rows),
        "strategies": {strategy_name: _strategy_group_stats(strategy_rows) for strategy_name, strategy_rows in grouped.items()},
    }
