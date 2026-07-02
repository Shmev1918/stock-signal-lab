from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from json import JSONDecodeError
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.providers.base import MarketDataError, MarketDataNotFound, MarketDataTimeout


class PolygonAPIError(MarketDataError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class PolygonSmokeCheck:
    name: str
    endpoint: str
    ticker: str | None
    success: bool
    status_code: int | None = None
    error: str | None = None


class PolygonMarketDataProvider:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.polygon.io",
        timeout_seconds: int = 20,
        mode: str = "free",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.mode = mode

    def _ensure_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError("POLYGON_API_KEY is not set")

    def _request_json(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_api_key()
        query = dict(params or {})
        query["apiKey"] = self.api_key
        url = f"{self.base_url}{endpoint}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except JSONDecodeError as exc:  # pragma: no cover - defensive parser guard
                    raise PolygonAPIError(f"Invalid JSON response from {endpoint}") from exc
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            raise PolygonAPIError(
                f"Polygon request failed for {endpoint}: {exc.reason}",
                status_code=getattr(exc, "code", None),
                retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
            ) from exc
        except TimeoutError as exc:
            raise MarketDataTimeout(f"Timeout calling Polygon endpoint {endpoint}") from exc
        except URLError as exc:
            raise MarketDataError(f"Polygon request failed for {endpoint}: {exc.reason}") from exc

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        display_ticker = self._display_ticker(ticker)
        data = self._request_json(
            f"/v2/aggs/ticker/{self._provider_ticker(ticker)}/range/1/day/{start_date.isoformat()}/{end_date.isoformat()}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        results = data.get("results") or []
        if not results:
            raise MarketDataNotFound(f"No Polygon daily aggregates found for {ticker}")
        rows: list[dict[str, Any]] = []
        for row in results:
            ts = row.get("t")
            if ts is None:
                continue
            row_date = datetime.utcfromtimestamp(ts / 1000).date()
            rows.append(
                {
                    "ticker": display_ticker,
                    "price_date": row_date,
                    "open": self._maybe_float(row.get("o")),
                    "high": self._maybe_float(row.get("h")),
                    "low": self._maybe_float(row.get("l")),
                    "close": self._maybe_float(row.get("c")),
                    "adj_close": self._maybe_float(row.get("c")),
                    "volume": self._maybe_int(row.get("v")),
                    "source": "polygon",
                }
            )
        if not rows:
            raise MarketDataNotFound(f"No Polygon daily aggregate rows found for {ticker}")
        return rows

    def get_latest_quote(self, ticker: str) -> dict[str, Any]:
        display_ticker = self._display_ticker(ticker)
        data = self._request_json(f"/v2/last/trade/{self._provider_ticker(ticker)}")
        results = data.get("results") or {}
        price = results.get("p")
        if price is None:
            raise MarketDataNotFound(f"No Polygon quote found for {ticker}")
        return {"ticker": display_ticker, "price": self._maybe_float(price), "currency": "USD"}

    def get_company_profile(self, ticker: str) -> dict[str, Any]:
        display_ticker = self._display_ticker(ticker)
        data = self._request_json(f"/v3/reference/tickers/{self._provider_ticker(ticker)}")
        results = data.get("results") or {}
        if not results:
            raise MarketDataNotFound(f"No Polygon company profile found for {ticker}")
        return {
            "ticker": display_ticker,
            "name": results.get("name") or display_ticker,
            "sector": results.get("sic_description") or results.get("market") or results.get("locale"),
            "industry": results.get("primary_exchange"),
            "exchange": results.get("primary_exchange"),
            "market_cap": self._maybe_float(results.get("market_cap")),
            "source": "polygon",
            "_raw": results,
        }

    def get_fundamentals(self, ticker: str) -> dict[str, Any]:
        profile = self.get_company_profile(ticker)
        profile.update(
            {
                "as_of_date": date.today(),
                "revenue_growth": None,
                "gross_margin": None,
                "operating_margin": None,
                "free_cash_flow": None,
                "return_on_equity": None,
                "debt_to_equity": None,
                "interest_coverage": None,
                "pe_ratio": None,
                "forward_pe": None,
                "price_to_sales": None,
                "price_to_fcf": None,
                "_warnings": [
                    "Polygon v1 acquisition mode only maps ticker metadata, dividends, splits, and daily aggregates.",
                    "Financial statement normalization is planned but not yet implemented.",
                ],
            }
        )
        profile["source"] = "polygon_partial"
        return profile

    def get_dividends(self, ticker: str) -> list[dict[str, Any]]:
        display_ticker = self._display_ticker(ticker)
        data = self._request_json(
            "/v3/reference/dividends",
            params={"ticker": self._provider_ticker(ticker), "limit": 50000, "sort": "asc"},
        )
        results = data.get("results") or []
        rows: list[dict[str, Any]] = []
        for row in results:
            ex_date = self._parse_date(row.get("ex_dividend_date") or row.get("exDate") or row.get("ex_date"))
            if ex_date is None:
                continue
            rows.append(
                {
                    "ticker": display_ticker,
                    "ex_date": ex_date,
                    "pay_date": self._parse_date(row.get("pay_date") or row.get("payDate")),
                    "amount": self._maybe_float(row.get("cash_amount") or row.get("cashAmount") or row.get("amount")) or 0.0,
                    "source": "polygon",
                }
            )
        return rows

    def get_splits(self, ticker: str) -> list[dict[str, Any]]:
        display_ticker = self._display_ticker(ticker)
        data = self._request_json(
            "/stocks/v1/splits",
            params={"ticker": self._provider_ticker(ticker), "limit": 50000, "sort": "asc"},
        )
        results = data.get("results") or []
        rows: list[dict[str, Any]] = []
        for row in results:
            execution_date = self._parse_date(row.get("execution_date") or row.get("exDate"))
            if execution_date is None:
                continue
            split_from = self._maybe_float(row.get("split_from") or row.get("from"))
            split_to = self._maybe_float(row.get("split_to") or row.get("to"))
            ratio = None
            if split_from and split_to:
                ratio = split_to / split_from if split_from else None
            rows.append(
                {
                    "ticker": display_ticker,
                    "execution_date": execution_date,
                    "split_from": split_from,
                    "split_to": split_to,
                    "ratio": ratio,
                    "adjustment_factor": self._maybe_float(row.get("adjustment_factor") or row.get("factor")),
                    "raw": row,
                    "source": "polygon",
                }
            )
        return rows

    def get_options_chain_snapshot(self, ticker: str) -> dict[str, Any]:
        return self._request_json(f"/v3/snapshot/options/{self._provider_ticker(ticker)}")

    def smoke_checks(self, ticker: str = "AAPL") -> list[PolygonSmokeCheck]:
        checks: list[PolygonSmokeCheck] = []
        for endpoint_name, endpoint_fn, symbol in [
            ("daily_aggregates", self.get_daily_prices, ticker),
            ("ticker_details", self.get_company_profile, ticker),
            ("dividends", self.get_dividends, ticker),
            ("splits", self.get_splits, ticker),
            ("spx_daily_aggregates", self.get_daily_prices, "SPY"),
        ]:
            try:
                if endpoint_name == "spx_daily_aggregates":
                    endpoint_fn(symbol, date.today() - timedelta(days=10), date.today())
                elif endpoint_name == "daily_aggregates":
                    endpoint_fn(symbol, date.today() - timedelta(days=10), date.today())
                else:
                    endpoint_fn(symbol)
                checks.append(PolygonSmokeCheck(endpoint_name, endpoint_name, symbol, True))
            except Exception as exc:  # pragma: no cover - smoke test reports errors
                checks.append(
                    PolygonSmokeCheck(
                        endpoint_name,
                        endpoint_name,
                        symbol,
                        False,
                        error=str(exc),
                    )
                )
        try:
            self.get_options_chain_snapshot("SPY")
            checks.append(PolygonSmokeCheck("spy_options_chain_snapshot", "options_chain_snapshot", "SPY", True))
        except Exception as exc:  # pragma: no cover - optional endpoint
            checks.append(
                PolygonSmokeCheck(
                    "spy_options_chain_snapshot",
                    "options_chain_snapshot",
                    "SPY",
                    False,
                    error=str(exc),
                )
            )
        return checks

    def _normalize_ticker(self, ticker: str) -> str:
        return ticker.strip().upper().replace(".", "-")

    def _provider_ticker(self, ticker: str) -> str:
        return self._normalize_ticker(ticker)

    def _display_ticker(self, ticker: str) -> str:
        return ticker.strip().upper()

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def _maybe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _maybe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
