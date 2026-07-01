from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.providers.base import MarketDataNotFound, MarketDataTimeout
from app.providers.yfinance_provider import YFinanceMarketDataProvider, normalize_ticker_for_provider


class _FakeHistory:
    empty = False

    def iterrows(self):
        yield datetime(2024, 1, 2), {
            "Open": 10.0,
            "High": 12.0,
            "Low": 9.5,
            "Close": 11.0,
            "Adj Close": 10.8,
            "Volume": 123456,
        }


class _FakeDividends:
    empty = False

    def items(self):
        yield datetime(2024, 1, 5), 0.25


class _FakeTicker:
    def __init__(self, info: dict[str, object] | None = None, history=None, dividends=None):
        self._info = info or {}
        self._history = history or _FakeHistory()
        self._dividends = dividends or _FakeDividends()

    @property
    def info(self):
        return self._info

    def history(self, **_kwargs):
        return self._history

    @property
    def dividends(self):
        return self._dividends


def _install_fake_yfinance(monkeypatch, ticker_factory) -> None:
    fake_module = SimpleNamespace(Ticker=ticker_factory)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)


def test_yfinance_provider_normalizes_ticker_aliases() -> None:
    assert normalize_ticker_for_provider("BRK.B") == "BRK-B"
    assert normalize_ticker_for_provider("aapl") == "AAPL"


def test_yfinance_provider_maps_common_fields(monkeypatch) -> None:
    ticker = _FakeTicker(
        info={
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NMS",
            "marketCap": 3_000_000_000_000,
            "currentPrice": 189.12,
            "currency": "USD",
            "revenueGrowth": 0.12,
            "grossMargins": 0.44,
            "operatingMargins": 0.31,
            "freeCashflow": 100_000_000_000,
            "returnOnEquity": 0.55,
            "debtToEquity": 1.2,
            "interestCoverage": 40.0,
            "trailingPE": 32.0,
            "forwardPE": 28.0,
            "priceToSalesTrailing12Months": 8.5,
            "priceToFreeCashFlow": 28.1,
        }
    )
    _install_fake_yfinance(monkeypatch, lambda _symbol: ticker)

    provider = YFinanceMarketDataProvider()

    prices = provider.get_daily_prices("AAPL", date(2024, 1, 1), date(2024, 1, 10))
    assert prices[0]["ticker"] == "AAPL"
    assert prices[0]["close"] == 11.0

    quote = provider.get_latest_quote("AAPL")
    assert quote == {"ticker": "AAPL", "price": 189.12, "currency": "USD"}

    profile = provider.get_company_profile("AAPL")
    assert profile["ticker"] == "AAPL"
    assert profile["sector"] == "Technology"
    assert "_warnings" in profile

    fundamentals = provider.get_fundamentals("AAPL")
    assert fundamentals["ticker"] == "AAPL"
    assert fundamentals["pe_ratio"] == 32.0
    assert "_warnings" in fundamentals

    dividends = provider.get_dividends("AAPL")
    assert dividends and dividends[0]["amount"] == 0.25


def test_yfinance_provider_raises_on_empty_history(monkeypatch) -> None:
    class EmptyHistory:
        empty = True

        def iterrows(self):
            return iter(())

    _install_fake_yfinance(monkeypatch, lambda _symbol: _FakeTicker(history=EmptyHistory()))
    provider = YFinanceMarketDataProvider()

    with pytest.raises(MarketDataNotFound):
        provider.get_daily_prices("ZZZZ", date(2024, 1, 1), date(2024, 1, 10))


def test_yfinance_provider_raises_on_timeout(monkeypatch) -> None:
    class TimeoutTicker(_FakeTicker):
        def history(self, **_kwargs):
            raise TimeoutError("timed out")

    _install_fake_yfinance(monkeypatch, lambda _symbol: TimeoutTicker())
    provider = YFinanceMarketDataProvider()

    with pytest.raises(MarketDataTimeout):
        provider.get_daily_prices("AAPL", date(2024, 1, 1), date(2024, 1, 10))


def test_yfinance_provider_best_effort_profile_and_fundamentals(monkeypatch) -> None:
    class NoInfoTicker(_FakeTicker):
        def get_info(self):
            raise Exception("info unavailable")

    ticker = NoInfoTicker()
    _install_fake_yfinance(monkeypatch, lambda _symbol: ticker)
    provider = YFinanceMarketDataProvider()

    profile = provider.get_company_profile("BRK.B")
    fundamentals = provider.get_fundamentals("BRK.B")

    assert profile["ticker"] == "BRK.B"
    assert profile["source"] == "yfinance_partial"
    assert profile["_warnings"]
    assert fundamentals["ticker"] == "BRK.B"
    assert fundamentals["source"] == "yfinance_partial"
    assert fundamentals["_warnings"]


def test_yfinance_provider_uses_broker_alias_for_history(monkeypatch) -> None:
    symbols: list[str] = []

    class HistoryTicker(_FakeTicker):
        pass

    def factory(symbol: str):
        symbols.append(symbol)
        return HistoryTicker()

    _install_fake_yfinance(monkeypatch, factory)
    provider = YFinanceMarketDataProvider()

    rows = provider.get_daily_prices("BRK.B", date(2024, 1, 1), date(2024, 1, 10))

    assert symbols[0] == "BRK-B"
    assert rows[0]["ticker"] == "BRK.B"
