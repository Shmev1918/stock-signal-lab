from __future__ import annotations

from statistics import median
from typing import Any

from app.experiments.outcome import OUTCOME_NEUTRAL, OUTCOME_OUTPERFORM, OUTCOME_UNDERPERFORM


def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if row.get(key) is not None]


def summarize_experiment_results(experiment: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in results if row.get("status") == "completed" and row.get("future_return") is not None]
    returns = _numeric_values(completed, "future_return")
    benchmark_returns = _numeric_values(completed, "benchmark_return")
    excess_returns = _numeric_values(completed, "excess_return")

    if excess_returns:
        best_result = max(completed, key=lambda row: float(row["excess_return"]))
        worst_result = min(completed, key=lambda row: float(row["excess_return"]))
    else:
        best_result = None
        worst_result = None

    labels = {
        OUTCOME_OUTPERFORM: sum(1 for row in completed if row.get("outcome_label") == OUTCOME_OUTPERFORM),
        OUTCOME_NEUTRAL: sum(1 for row in completed if row.get("outcome_label") == OUTCOME_NEUTRAL),
        OUTCOME_UNDERPERFORM: sum(1 for row in completed if row.get("outcome_label") == OUTCOME_UNDERPERFORM),
    }
    winning = [value for value in excess_returns if value >= 0]
    return {
        "experiment": experiment,
        "total_observations": len(results),
        "available_observations": len(completed),
        "average_future_return": (sum(returns) / len(returns)) if returns else None,
        "average_benchmark_return": (sum(benchmark_returns) / len(benchmark_returns)) if benchmark_returns else None,
        "average_excess_return": (sum(excess_returns) / len(excess_returns)) if excess_returns else None,
        "median_excess_return": median(excess_returns) if excess_returns else None,
        "win_rate_vs_benchmark": (len(winning) / len(excess_returns)) if excess_returns else None,
        "outperform_count": labels[OUTCOME_OUTPERFORM],
        "neutral_count": labels[OUTCOME_NEUTRAL],
        "underperform_count": labels[OUTCOME_UNDERPERFORM],
        "best_result": best_result,
        "worst_result": worst_result,
    }
