from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Holding:
    ticker: str
    weight: float


def equal_weight_portfolio(tickers: list[str]) -> list[Holding]:
    if not tickers:
        return []
    weight = 1.0 / len(tickers)
    return [Holding(ticker=t, weight=weight) for t in tickers]

