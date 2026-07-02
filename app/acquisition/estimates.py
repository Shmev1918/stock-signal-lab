from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.acquisition.jobs import get_campaign_universe


def estimate_acquisition(
    *,
    provider: str,
    universe_name: str,
    years: int,
    include_prices: bool,
    include_fundamentals: bool,
    include_options: bool,
    rate_limit_per_minute: int,
    config_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tickers = get_campaign_universe(universe_name, config_json)
    years = max(int(years), 1)
    rate_limit_per_minute = max(int(rate_limit_per_minute), 1)
    trading_days = int(252 * years)
    daily_calls = len(tickers) if include_prices else 0
    fundamental_calls = len(tickers) if include_fundamentals else 0
    options_calls = len(tickers) if include_options else 0
    estimated_calls = daily_calls + fundamental_calls + options_calls * 2
    estimated_rows = 0
    if include_prices:
        estimated_rows += len(tickers) * trading_days
    if include_fundamentals:
        estimated_rows += len(tickers) * max(years * 4, 1)
    if include_options:
        estimated_rows += len(tickers) * years * 50_000
    estimated_minutes = estimated_calls / rate_limit_per_minute
    storage_gb = round(max(estimated_rows * 0.0000015, 0.0), 3)
    warnings = []
    if include_options and len(tickers) > 10:
        warnings.append("Options scope is too broad for v1; keep under 10 underlyings.")
    if provider == "polygon" and years > 2:
        warnings.append("Polygon paid acquisition should start with a narrow historical window first.")
    if not include_prices:
        warnings.append("Without daily prices, backtesting and signal replay will be limited.")
    return {
        "provider": provider,
        "universe_name": universe_name,
        "years": years,
        "rate_limit_per_minute": rate_limit_per_minute,
        "tickers": len(tickers),
        "include_prices": include_prices,
        "include_fundamentals": include_fundamentals,
        "include_options": include_options,
        "estimated_api_calls": estimated_calls,
        "estimated_rows": estimated_rows,
        "estimated_runtime_minutes": round(estimated_minutes, 1),
        "rough_storage_gb": storage_gb,
        "flat_files": _flat_files_for_scope(include_prices=include_prices, include_options=include_options),
        "warnings": warnings,
        "window_start": (date.today() - timedelta(days=365 * years)).isoformat(),
        "window_end": date.today().isoformat(),
    }


def _flat_files_for_scope(*, include_prices: bool, include_options: bool) -> list[str]:
    files: list[str] = []
    if include_prices:
        files.extend(["us_stocks_sip/day_aggs_v1", "us_stocks_sip/trades_v1", "us_stocks_sip/quotes_v1"])
    if include_options:
        files.extend(["us_options_opra/day_aggs_v1", "us_options_opra/minute_aggs_v1", "us_options_opra/trades_v1", "us_options_opra/quotes_v1"])
    return files
