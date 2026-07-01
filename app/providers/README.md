# Provider contract

All market data providers should implement `MarketDataProvider` in `base.py`.

Required methods:

- `get_daily_prices(ticker, start_date, end_date)`
- `get_latest_quote(ticker)`
- `get_company_profile(ticker)`
- `get_fundamentals(ticker)`
- `get_dividends(ticker)`
- `get_news(ticker)`

The first implementation is `MockMarketDataProvider`.

Planned providers:

- Alpha Vantage
- Finnhub
- Polygon
- SEC EDGAR
- yfinance for local experimentation

