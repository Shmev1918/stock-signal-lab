from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BacktestMetrics:
    total_return: float
    annualized_return: float
    max_drawdown: float
    volatility: float
    win_rate: float


def calculate_metrics(returns: list[float]) -> BacktestMetrics:
    # TODO: expand to benchmark-relative metrics.
    if not returns:
        return BacktestMetrics(0.0, 0.0, 0.0, 0.0, 0.0)
    total = 1.0
    peak = 1.0
    equity = 1.0
    drawdown = 0.0
    wins = 0
    for r in returns:
        if r > 0:
            wins += 1
        equity *= 1 + r
        total *= 1 + r
        peak = max(peak, equity)
        drawdown = min(drawdown, (equity - peak) / peak)
    volatility = (sum((r - sum(returns) / len(returns)) ** 2 for r in returns) / len(returns)) ** 0.5
    annualized = total ** (12 / max(len(returns), 1)) - 1
    return BacktestMetrics(
        total_return=total - 1,
        annualized_return=annualized,
        max_drawdown=drawdown,
        volatility=volatility,
        win_rate=wins / len(returns),
    )

