from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.providers.base import MarketDataError, MarketDataNotFound, MarketDataTimeout, MarketDataProvider


def normalize_ticker_for_provider(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


class YFinanceMarketDataProvider(MarketDataProvider):
    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def _ticker(self, ticker: str):
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - dependency installation issue
            raise RuntimeError("yfinance is not installed; install the optional dependency") from exc
        return yf.Ticker(ticker)

    def _guard(self, ticker: str) -> str:
        cleaned = ticker.strip().upper()
        if not cleaned:
            raise MarketDataNotFound("Ticker is empty")
        return cleaned

    def _provider_candidates(self, ticker: str) -> list[str]:
        display = self._guard(ticker)
        provider_symbol = normalize_ticker_for_provider(display)
        candidates = [provider_symbol]
        if display != provider_symbol:
            candidates.append(display)
        return candidates

    def _get_info(self, ticker: str) -> dict[str, Any]:
        ticker_obj = self._ticker(ticker)
        if hasattr(ticker_obj, "get_info"):
            info = ticker_obj.get_info() or {}
        else:  # pragma: no cover - compatibility path
            info = getattr(ticker_obj, "info", {}) or {}
        return info

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        display_ticker = self._guard(ticker)
        timeout_error: TimeoutError | None = None
        last_error: Exception | None = None
        for provider_ticker in self._provider_candidates(display_ticker):
            try:
                data = self._ticker(provider_ticker).history(
                    start=start_date,
                    end=end_date + timedelta(days=1),
                    interval="1d",
                    auto_adjust=False,
                    actions=False,
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                timeout_error = exc
                continue
            except Exception as exc:  # pragma: no cover - defensive yfinance wrapper
                last_error = exc
                continue

            if data is None or getattr(data, "empty", True):
                last_error = MarketDataNotFound(f"No daily price history found for {provider_ticker}")
                continue

            rows: list[dict[str, Any]] = []
            for row_date, row in data.iterrows():
                close = row.get("Close")
                if close is None:
                    continue
                rows.append(
                    {
                        "ticker": display_ticker,
                        "price_date": row_date.date() if hasattr(row_date, "date") else row_date,
                        "open": _maybe_float(row.get("Open")),
                        "high": _maybe_float(row.get("High")),
                        "low": _maybe_float(row.get("Low")),
                        "close": _maybe_float(close),
                        "adj_close": _maybe_float(row.get("Adj Close", close)),
                        "volume": _maybe_int(row.get("Volume")),
                        "source": "yfinance",
                    }
                )
            if rows:
                return rows
            last_error = MarketDataNotFound(f"No usable price rows found for {provider_ticker}")

        if timeout_error is not None:
            raise MarketDataTimeout(f"Timeout fetching historical prices for {display_ticker}") from timeout_error
        if last_error is not None:
            raise MarketDataNotFound(f"Unable to fetch price history for {display_ticker}") from last_error
        raise MarketDataNotFound(f"Unable to fetch price history for {display_ticker}")

    def get_latest_quote(self, ticker: str) -> dict[str, Any]:
        display_ticker = self._guard(ticker)
        info: dict[str, Any] = {}
        last_error: Exception | None = None
        for provider_ticker in self._provider_candidates(display_ticker):
            try:
                info = self._get_info(provider_ticker)
                if info:
                    break
            except TimeoutError as exc:
                last_error = exc
            except Exception as exc:  # pragma: no cover - defensive yfinance wrapper
                last_error = exc
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is None:
            try:
                history = self.get_daily_prices(display_ticker, date.today() - timedelta(days=10), date.today())
                price = history[-1]["close"]
            except MarketDataError as exc:
                last_error = exc
        if price is None:
            if isinstance(last_error, TimeoutError):
                raise MarketDataTimeout(f"Timeout fetching quote for {display_ticker}") from last_error
            raise MarketDataNotFound(f"Unable to fetch quote for {display_ticker}")
        return {
            "ticker": display_ticker,
            "price": _maybe_float(price),
            "currency": info.get("currency") or "USD",
        }

    def get_company_profile(self, ticker: str) -> dict[str, Any]:
        display_ticker = self._guard(ticker)
        info, info_warnings = self._best_effort_info(display_ticker)
        warnings = list(info_warnings)
        profile = {
            "ticker": display_ticker,
            "name": info.get("longName") or info.get("shortName") or display_ticker,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange"),
            "market_cap": _maybe_float(info.get("marketCap")),
            "_warnings": warnings,
            "source": "yfinance",
        }
        if profile["sector"] is None:
            warnings.append(f"sector unavailable for {display_ticker}")
        if profile["industry"] is None:
            warnings.append(f"industry unavailable for {display_ticker}")
        if profile["market_cap"] is None:
            warnings.append(f"market cap unavailable for {display_ticker}")
        if warnings or not info:
            profile["source"] = "yfinance_partial"
        return profile

    def get_fundamentals(self, ticker: str) -> dict[str, Any]:
        display_ticker = self._guard(ticker)
        info, warnings = self._best_effort_info(display_ticker)
        fundamentals = {
            "ticker": display_ticker,
            "as_of_date": date.today(),
            "revenue_growth": _maybe_float(info.get("revenueGrowth")),
            "gross_margin": _maybe_float(info.get("grossMargins")),
            "operating_margin": _maybe_float(info.get("operatingMargins")),
            "free_cash_flow": _maybe_float(info.get("freeCashflow")),
            "return_on_equity": _maybe_float(info.get("returnOnEquity")),
            "debt_to_equity": _maybe_float(info.get("debtToEquity")),
            "interest_coverage": _maybe_float(info.get("interestCoverage")),
            "pe_ratio": _maybe_float(info.get("trailingPE") or info.get("trailingPe")),
            "forward_pe": _maybe_float(info.get("forwardPE")),
            "price_to_sales": _maybe_float(info.get("priceToSalesTrailing12Months")),
            "price_to_fcf": _maybe_float(info.get("priceToFreeCashFlow")),
            "raw": dict(info),
            "_warnings": warnings,
            "source": "yfinance",
        }
        missing = [
            name
            for name in (
                "revenue_growth",
                "gross_margin",
                "operating_margin",
                "free_cash_flow",
                "return_on_equity",
                "debt_to_equity",
                "pe_ratio",
                "price_to_sales",
            )
            if fundamentals[name] is None
        ]
        if missing:
            fundamentals["_warnings"].append(
                f"partial fundamentals for {display_ticker}: missing {', '.join(missing)}"
            )
            fundamentals["source"] = "yfinance_partial"
        if not info and "No company data" not in " ".join(fundamentals["_warnings"]):
            fundamentals["source"] = "yfinance_partial"
        return fundamentals

    def get_dividends(self, ticker: str) -> list[dict[str, Any]]:
        display_ticker = self._guard(ticker)
        timeout_seen = False
        for provider_ticker in self._provider_candidates(display_ticker):
            try:
                dividends = self._ticker(provider_ticker).dividends
            except TimeoutError:
                timeout_seen = True
                continue
            except Exception:  # pragma: no cover - defensive yfinance wrapper
                continue

            if dividends is None or getattr(dividends, "empty", True):
                continue

            rows: list[dict[str, Any]] = []
            for ex_date, amount in dividends.items():
                rows.append(
                    {
                        "ticker": display_ticker,
                        "ex_date": ex_date.date() if hasattr(ex_date, "date") else ex_date,
                        "pay_date": None,
                        "amount": _maybe_float(amount) or 0.0,
                        "source": "yfinance",
                    }
                )
            if rows:
                return rows
        if timeout_seen:
            raise MarketDataTimeout(f"Timeout fetching dividends for {display_ticker}")
        return []

    def get_news(self, ticker: str) -> list[dict[str, Any]]:
        return []

    def _best_effort_info(self, ticker: str) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        last_timeout: TimeoutError | None = None
        for provider_ticker in self._provider_candidates(ticker):
            try:
                info = self._get_info(provider_ticker)
            except TimeoutError as exc:
                last_timeout = exc
                warnings.append(f"timeout fetching company data for {provider_ticker}")
                continue
            except Exception:  # pragma: no cover - defensive yfinance wrapper
                warnings.append(f"unable to fetch company data for {provider_ticker}")
                continue
            if info:
                return info, warnings
            warnings.append(f"no company data found for {provider_ticker}")
        if last_timeout is not None:
            warnings.append(f"timeout fetching company data for {ticker}")
        return {}, warnings


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
