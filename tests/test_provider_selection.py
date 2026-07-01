from __future__ import annotations

from types import SimpleNamespace

from app.config import get_settings
from app.providers.factory import get_market_data_provider
from app.providers.mock_provider import MockMarketDataProvider
from app.providers.yfinance_provider import YFinanceMarketDataProvider


def test_provider_selection_defaults_to_mock(monkeypatch) -> None:
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    get_settings.cache_clear()
    assert isinstance(get_market_data_provider(), MockMarketDataProvider)


def test_provider_selection_can_use_yfinance(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yfinance")
    get_settings.cache_clear()
    fake_module = SimpleNamespace(Ticker=lambda _symbol: None)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    provider = get_market_data_provider()
    assert isinstance(provider, YFinanceMarketDataProvider)
