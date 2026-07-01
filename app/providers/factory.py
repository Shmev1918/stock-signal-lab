from __future__ import annotations

from app.providers.base import MarketDataProvider
from app.providers.mock_provider import MockMarketDataProvider


def get_market_data_provider(provider_name: str | None = None) -> MarketDataProvider:
    if provider_name is None:
        from app.config import get_settings

        provider_name = get_settings().market_data_provider

    provider_name = provider_name.lower()
    if provider_name == "yfinance":
        from app.providers.yfinance_provider import YFinanceMarketDataProvider

        return YFinanceMarketDataProvider()
    return MockMarketDataProvider()
