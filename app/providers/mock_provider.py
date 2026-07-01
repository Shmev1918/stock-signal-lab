from __future__ import annotations

from datetime import date, datetime, timedelta
from random import Random
from typing import Any

from app.providers.base import MarketDataProvider


class MockMarketDataProvider(MarketDataProvider):
    def _rng(self, ticker: str) -> Random:
        return Random(sum(ord(c) for c in ticker.upper()))

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        rng = self._rng(ticker)
        days = (end_date - start_date).days
        base = 50 + (sum(ord(c) for c in ticker) % 300)
        prices: list[dict[str, Any]] = []
        close = float(base)
        for offset in range(max(days + 1, 1)):
            current = start_date + timedelta(days=offset)
            drift = rng.uniform(-0.03, 0.03)
            close = max(1.0, close * (1 + drift))
            high = close * (1 + rng.uniform(0.0, 0.02))
            low = close * (1 - rng.uniform(0.0, 0.02))
            open_price = close * (1 + rng.uniform(-0.01, 0.01))
            prices.append(
                {
                    "ticker": ticker.upper(),
                    "price_date": current,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "adj_close": round(close, 2),
                    "volume": int(1_000_000 + rng.random() * 5_000_000),
                    "source": "mock",
                }
            )
        return prices

    def get_latest_quote(self, ticker: str) -> dict[str, Any]:
        rng = self._rng(ticker)
        price = 50 + (sum(ord(c) for c in ticker) % 300) + rng.uniform(-10, 10)
        return {"ticker": ticker.upper(), "price": round(price, 2), "currency": "USD"}

    def get_company_profile(self, ticker: str) -> dict[str, Any]:
        sectors = ["Technology", "Financials", "Healthcare", "Consumer Staples", "Energy"]
        rng = self._rng(ticker)
        return {
            "ticker": ticker.upper(),
            "name": f"{ticker.upper()} Corp",
            "sector": sectors[rng.randrange(len(sectors))],
            "industry": "Mock Industry",
            "exchange": "NASDAQ",
            "market_cap": float(10_000_000_000 + rng.randrange(200_000_000_000)),
            "source": "mock",
        }

    def get_fundamentals(self, ticker: str) -> dict[str, Any]:
        rng = self._rng(ticker)
        return {
            "ticker": ticker.upper(),
            "as_of_date": date.today(),
            "revenue_growth": round(rng.uniform(-0.1, 0.3), 3),
            "gross_margin": round(rng.uniform(0.2, 0.8), 3),
            "operating_margin": round(rng.uniform(-0.1, 0.4), 3),
            "free_cash_flow": round(rng.uniform(-5e9, 2e10), 2),
            "return_on_equity": round(rng.uniform(-0.2, 0.6), 3),
            "debt_to_equity": round(rng.uniform(0.1, 4.0), 3),
            "interest_coverage": round(rng.uniform(1.0, 20.0), 2),
            "pe_ratio": round(rng.uniform(8, 80), 2),
            "forward_pe": round(rng.uniform(8, 75), 2),
            "price_to_sales": round(rng.uniform(1, 20), 2),
            "price_to_fcf": round(rng.uniform(5, 100), 2),
            "source": "mock",
        }

    def get_dividends(self, ticker: str) -> list[dict[str, Any]]:
        rng = self._rng(ticker)
        if rng.random() < 0.5:
            return []
        return [
            {
                "ticker": ticker.upper(),
                "ex_date": date.today() - timedelta(days=90),
                "pay_date": date.today() - timedelta(days=75),
                "amount": round(rng.uniform(0.1, 1.5), 2),
                "source": "mock",
            }
        ]

    def get_news(self, ticker: str) -> list[dict[str, Any]]:
        rng = self._rng(ticker)
        return [
            {
                "ticker": ticker.upper(),
                "published_at": datetime.now() - timedelta(days=i),
                "title": f"{ticker.upper()} mock headline {i}",
                "summary": "Synthetic news item for local experimentation.",
                "url": None,
                "sentiment": round(rng.uniform(-1, 1), 2),
                "source": "mock",
            }
            for i in range(3)
        ]
