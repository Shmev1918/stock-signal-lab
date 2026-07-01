from datetime import date

from app.providers.mock_provider import MockMarketDataProvider


def test_mock_provider_returns_expected_shapes() -> None:
    provider = MockMarketDataProvider()
    prices = provider.get_daily_prices("AAPL", date(2024, 1, 1), date(2024, 1, 10))
    assert prices
    assert {"ticker", "price_date", "close"} <= set(prices[0])
    assert provider.get_latest_quote("AAPL")["ticker"] == "AAPL"
    assert provider.get_company_profile("AAPL")["ticker"] == "AAPL"
    assert provider.get_fundamentals("AAPL")["ticker"] == "AAPL"
    assert provider.get_news("AAPL")

