from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from json import JSONDecodeError
import json
import logging
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.providers.base import MarketDataError, MarketDataNotFound, MarketDataTimeout
from app.providers.polygon_rate_limit import PolygonRateLimitEvent, PolygonRateLimiter

_LOGGER = logging.getLogger(__name__)


class PolygonAPIError(MarketDataError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: int | None = None,
        error_kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.error_kind = error_kind


@dataclass(frozen=True)
class PolygonSmokeCheck:
    name: str
    endpoint: str
    ticker: str | None
    status: str
    http_status: int | None = None
    error: str | None = None
    cause: str = "UNKNOWN"
    rate_limited: bool = False

    @property
    def success(self) -> bool:
        return self.status == "PASS"


class PolygonMarketDataProvider:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.polygon.io",
        timeout_seconds: int = 20,
        mode: str = "free",
        rate_limit_per_minute: int = 3,
        rate_limit_clock: Callable[[], float] = time.monotonic,
        rate_limit_sleeper: Callable[[float], None] = time.sleep,
        http_get: Callable[[Request, int], Any] = urlopen,
        logger: logging.Logger | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.mode = mode
        self.http_get = http_get
        self.logger = logger or _LOGGER
        self.rate_limiter = PolygonRateLimiter(
            rate_limit_per_minute,
            clock=rate_limit_clock,
            sleeper=rate_limit_sleeper,
        )

    def _ensure_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError("POLYGON_API_KEY is not set")

    def _build_url(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        self._ensure_api_key()
        query = dict(params or {})
        query["apiKey"] = self.api_key
        url = f"{self.base_url}{endpoint}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"
        return url

    def _request_json(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._build_url(endpoint, params=params)
        request = Request(url, headers={"Accept": "application/json"})
        rate_event: PolygonRateLimitEvent = self.rate_limiter.acquire(endpoint)
        started_at = datetime.now()
        try:
            with self.http_get(request, timeout=self.timeout_seconds) as response:
                status_code = int(getattr(response, "status", getattr(response, "code", 200)))
                raw = response.read().decode("utf-8")
                elapsed_ms = int(max((datetime.now() - started_at).total_seconds() * 1000.0, 0.0))
                self.logger.info(
                    "polygon request endpoint=%s status=%s elapsed_ms=%s rate_limited=%s",
                    endpoint,
                    status_code,
                    elapsed_ms,
                    rate_event.rate_limited,
                )
                try:
                    return json.loads(raw)
                except JSONDecodeError as exc:  # pragma: no cover - defensive parser guard
                    raise PolygonAPIError(
                        f"Invalid JSON response from {endpoint}",
                        status_code=status_code,
                        error_kind="invalid_json",
                    ) from exc
        except HTTPError as exc:
            elapsed_ms = int(max((datetime.now() - started_at).total_seconds() * 1000.0, 0.0))
            retry_after = exc.headers.get("Retry-After")
            status_code = getattr(exc, "code", None)
            self.logger.info(
                "polygon request endpoint=%s status=%s elapsed_ms=%s rate_limited=%s",
                endpoint,
                status_code,
                elapsed_ms,
                rate_event.rate_limited,
            )
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8").strip()
            except Exception:  # pragma: no cover - best-effort detail extraction
                body_text = ""
            message = f"Polygon request failed for {endpoint}: {exc.reason}"
            if body_text:
                message = f"{message} ({body_text[:300]})"
            raise PolygonAPIError(
                message,
                status_code=status_code,
                retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
                error_kind=self._error_kind_from_status(status_code),
            ) from exc
        except TimeoutError as exc:
            elapsed_ms = int(max((datetime.now() - started_at).total_seconds() * 1000.0, 0.0))
            self.logger.info(
                "polygon request endpoint=%s status=timeout elapsed_ms=%s rate_limited=%s",
                endpoint,
                elapsed_ms,
                rate_event.rate_limited,
            )
            raise MarketDataTimeout(f"Timeout calling Polygon endpoint {endpoint}") from exc
        except URLError as exc:
            elapsed_ms = int(max((datetime.now() - started_at).total_seconds() * 1000.0, 0.0))
            self.logger.info(
                "polygon request endpoint=%s status=error elapsed_ms=%s rate_limited=%s",
                endpoint,
                elapsed_ms,
                rate_event.rate_limited,
            )
            raise MarketDataError(f"Polygon request failed for {endpoint}: {exc.reason}") from exc

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        display_ticker = self._display_ticker(ticker)
        data = self._request_json(
            f"/v2/aggs/ticker/{self._provider_ticker(ticker)}/range/1/day/{start_date.isoformat()}/{end_date.isoformat()}",
            params={"adjusted": "true", "sort": "timestamp.asc", "limit": 50000},
        )
        results = data.get("results") or []
        if not results:
            raise MarketDataNotFound(f"No Polygon daily aggregates found for {ticker}")
        rows: list[dict[str, Any]] = []
        for row in results:
            ts = row.get("t")
            if ts is None:
                continue
            row_date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date()
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
            "/stocks/v1/dividends",
            params={"ticker": self._provider_ticker(ticker), "limit": 5000, "sort": "ticker.asc"},
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
            params={"ticker": self._provider_ticker(ticker), "limit": 5000, "sort": "execution_date.asc"},
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

    def get_news(self, ticker: str) -> list[dict[str, Any]]:
        return []

    def smoke_checks(self, ticker: str = "AAPL") -> list[PolygonSmokeCheck]:
        checks: list[PolygonSmokeCheck] = []
        smoke_calls = [
            ("daily_aggregates", lambda: self.get_daily_prices(ticker, date.today() - timedelta(days=10), date.today()), ticker),
            ("spy_daily_aggregates", lambda: self.get_daily_prices("SPY", date.today() - timedelta(days=10), date.today()), "SPY"),
            ("ticker_details", lambda: self.get_company_profile(ticker), ticker),
            ("dividends", lambda: self.get_dividends(ticker), ticker),
            ("splits", lambda: self.get_splits(ticker), ticker),
            ("options_chain_snapshot", lambda: self.get_options_chain_snapshot("SPY"), "SPY"),
        ]
        for name, call, symbol in smoke_calls:
            checks.append(self._run_smoke_check(name, symbol, call))
        return checks

    def _run_smoke_check(self, name: str, ticker: str | None, func: Callable[[], Any]) -> PolygonSmokeCheck:
        try:
            result = func()
            if name == "options_chain_snapshot" and isinstance(result, dict) and not result.get("results"):
                return PolygonSmokeCheck(
                    name=name,
                    endpoint=self._smoke_endpoint_name(name),
                    ticker=ticker,
                    status="SKIPPED",
                    http_status=200,
                    error="No options chain snapshot returned",
                    cause="NO_DATA",
                )
            return PolygonSmokeCheck(
                name=name,
                endpoint=self._smoke_endpoint_name(name),
                ticker=ticker,
                status="PASS",
                http_status=200,
                cause="OK",
            )
        except PolygonAPIError as exc:
            status, cause = self._classify_polygon_error(name, exc)
            return PolygonSmokeCheck(
                name=name,
                endpoint=self._smoke_endpoint_name(name),
                ticker=ticker,
                status=status,
                http_status=exc.status_code,
                error=self._short_error(str(exc)),
                cause=cause,
            )
        except MarketDataNotFound as exc:
            return PolygonSmokeCheck(
                name=name,
                endpoint=self._smoke_endpoint_name(name),
                ticker=ticker,
                status="SKIPPED",
                http_status=None,
                error=self._short_error(str(exc)),
                cause="NO_DATA",
            )
        except Exception as exc:  # pragma: no cover - smoke report guard
            return PolygonSmokeCheck(
                name=name,
                endpoint=self._smoke_endpoint_name(name),
                ticker=ticker,
                status="FAIL",
                http_status=None,
                error=self._short_error(str(exc)),
                cause="UNKNOWN",
            )

    def _classify_polygon_error(self, name: str, exc: PolygonAPIError) -> tuple[str, str]:
        status_code = exc.status_code
        if status_code == 403:
            return "FORBIDDEN", "PLAN_RESTRICTED"
        if status_code == 401:
            return "FAIL", "INVALID_KEY"
        if status_code == 429:
            return "FAIL", "RATE_LIMITED"
        if status_code == 400:
            if name in {"dividends", "splits"}:
                return "BAD_REQUEST", "ENDPOINT_REQUEST_MISMATCH"
            return "BAD_REQUEST", "UNKNOWN"
        if status_code and status_code >= 500:
            return "FAIL", "PROVIDER_ERROR"
        return "FAIL", exc.error_kind.upper() if exc.error_kind else "UNKNOWN"

    @staticmethod
    def _smoke_endpoint_name(name: str) -> str:
        mapping = {
            "daily_aggregates": "/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
            "spy_daily_aggregates": "/v2/aggs/ticker/SPY/range/1/day/{start}/{end}",
            "ticker_details": "/v3/reference/tickers/{ticker}",
            "dividends": "/stocks/v1/dividends",
            "splits": "/stocks/v1/splits",
            "options_chain_snapshot": "/v3/snapshot/options/SPY",
        }
        return mapping.get(name, name)

    @staticmethod
    def _short_error(value: str | None, max_length: int = 240) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if len(trimmed) <= max_length:
            return trimmed
        return f"{trimmed[: max_length - 3]}..."

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

    @staticmethod
    def _error_kind_from_status(status_code: int | None) -> str | None:
        if status_code == 400:
            return "bad_request"
        if status_code == 401:
            return "invalid_key"
        if status_code == 403:
            return "plan_restricted"
        if status_code == 429:
            return "rate_limited"
        if status_code and status_code >= 500:
            return "provider_error"
        return None
