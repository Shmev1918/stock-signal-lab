from __future__ import annotations

import io
import json
from datetime import date
from urllib.error import HTTPError

from app.providers.polygon_provider import PolygonAPIError, PolygonMarketDataProvider


class FakeHTTPResponse:
    def __init__(self, payload: dict | list, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _error_response(url: str, status: int, message: str, body: dict | None = None, headers: dict[str, str] | None = None):
    raise HTTPError(url, status, message, headers or {}, io.BytesIO(json.dumps(body or {}).encode("utf-8")))


def test_polygon_provider_builds_correct_urls_and_parses_success() -> None:
    requests: list[str] = []

    def http_get(request, timeout):
        requests.append(request.full_url)
        if "/stocks/v1/dividends" in request.full_url:
            return FakeHTTPResponse(
                {
                    "results": [
                        {
                            "ticker": "AAPL",
                            "ex_dividend_date": "2026-01-05",
                            "pay_date": "2026-01-20",
                            "cash_amount": 0.25,
                        }
                    ]
                }
            )
        if "/stocks/v1/splits" in request.full_url:
            return FakeHTTPResponse(
                {
                    "results": [
                        {
                            "ticker": "AAPL",
                            "execution_date": "2026-01-07",
                            "split_from": 1,
                            "split_to": 2,
                            "factor": 0.5,
                        }
                    ]
                }
            )
        if "/v3/reference/tickers/AAPL" in request.full_url:
            return FakeHTTPResponse({"results": {"ticker": "AAPL", "name": "Apple Inc.", "primary_exchange": "NASDAQ"}})
        if "/v2/aggs/ticker/AAPL/range/1/day/" in request.full_url:
            return FakeHTTPResponse(
                {
                    "results": [
                        {"t": 1767225600000, "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000},
                    ]
                }
            )
        return FakeHTTPResponse({"results": []})

    provider = PolygonMarketDataProvider(api_key="test", rate_limit_per_minute=0, http_get=http_get)

    prices = provider.get_daily_prices("AAPL", date(2026, 1, 1), date(2026, 1, 5))
    profile = provider.get_company_profile("AAPL")
    dividends = provider.get_dividends("AAPL")
    splits = provider.get_splits("AAPL")

    assert prices[0]["ticker"] == "AAPL"
    assert profile["ticker"] == "AAPL"
    assert dividends[0]["ticker"] == "AAPL"
    assert splits[0]["ticker"] == "AAPL"
    assert any("/stocks/v1/dividends?ticker=AAPL" in request for request in requests)
    assert any("/stocks/v1/splits?ticker=AAPL" in request for request in requests)
    assert any("sort=ticker.asc" in request for request in requests if "/stocks/v1/dividends" in request)
    assert any("sort=execution_date.asc" in request for request in requests if "/stocks/v1/splits" in request)


def test_polygon_provider_smoke_checks_classify_free_tier_results() -> None:
    def http_get(request, timeout):
        url = request.full_url
        if "/v2/aggs/ticker/AAPL/" in url or "/v2/aggs/ticker/SPY/" in url:
            return FakeHTTPResponse({"results": [{"t": 1767225600000, "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000}]})
        if "/v3/reference/tickers/AAPL" in url:
            return FakeHTTPResponse({"results": {"ticker": "AAPL", "name": "Apple Inc."}})
        if "/stocks/v1/dividends" in url:
            return _error_response(url, 400, "Bad Request", {"status": "BAD_REQUEST"})
        if "/stocks/v1/splits" in url:
            return _error_response(url, 400, "Bad Request", {"status": "BAD_REQUEST"})
        if "/v3/snapshot/options/SPY" in url:
            return _error_response(url, 403, "Forbidden", {"status": "FORBIDDEN"})
        return FakeHTTPResponse({"results": []})

    provider = PolygonMarketDataProvider(api_key="test", rate_limit_per_minute=0, http_get=http_get)
    checks = provider.smoke_checks("AAPL")

    by_name = {check.name: check for check in checks}
    assert by_name["daily_aggregates"].status == "PASS"
    assert by_name["spy_daily_aggregates"].status == "PASS"
    assert by_name["ticker_details"].status == "PASS"
    assert by_name["dividends"].status == "BAD_REQUEST"
    assert by_name["dividends"].cause == "ENDPOINT_REQUEST_MISMATCH"
    assert by_name["splits"].status == "BAD_REQUEST"
    assert by_name["options_chain_snapshot"].status == "FORBIDDEN"
    assert by_name["options_chain_snapshot"].cause == "PLAN_RESTRICTED"


def test_polygon_provider_maps_http_statuses() -> None:
    def http_get(request, timeout):
        url = request.full_url
        if "400" in url:
            return _error_response(url, 400, "Bad Request", {"status": "BAD_REQUEST"})
        if "401" in url:
            return _error_response(url, 401, "Unauthorized", {"status": "UNAUTHORIZED"})
        if "403" in url:
            return _error_response(url, 403, "Forbidden", {"status": "FORBIDDEN"})
        if "429" in url:
            return _error_response(url, 429, "Too Many Requests", {"status": "TOO_MANY_REQUESTS"}, {"Retry-After": "2"})
        if "500" in url:
            return _error_response(url, 500, "Server Error", {"status": "ERROR"})
        return FakeHTTPResponse({"results": []})

    provider = PolygonMarketDataProvider(api_key="test", rate_limit_per_minute=0, http_get=http_get)

    for status in [400, 401, 403, 429, 500]:
        try:
            provider._request_json(f"/status/{status}")
        except PolygonAPIError as exc:
            assert exc.status_code == status
            assert exc.error_kind is not None
            if status == 429:
                assert exc.retry_after == 2
        else:  # pragma: no cover - defensive
            raise AssertionError(f"expected PolygonAPIError for status {status}")


def test_polygon_provider_rate_limiter_is_centralized() -> None:
    sleeps: list[float] = []
    current = {"value": 0.0}

    def clock() -> float:
        return current["value"]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    calls: list[str] = []

    def http_get(request, timeout):
        calls.append(request.full_url)
        return FakeHTTPResponse({"results": {"ticker": "AAPL", "name": "Apple Inc."}})

    provider = PolygonMarketDataProvider(
        api_key="test",
        rate_limit_per_minute=60,
        rate_limit_clock=clock,
        rate_limit_sleeper=sleeper,
        http_get=http_get,
    )

    provider.get_company_profile("AAPL")
    current["value"] = 0.2
    provider.get_company_profile("MSFT")

    assert calls[0] != calls[1]
    assert sleeps and 0.7 < sleeps[0] < 0.9
