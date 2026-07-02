from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.acquisition.checkpoints import task_is_runnable, task_request_key
from app.acquisition.provider_calls import call_provider
from app.acquisition.queue import build_queue
from app.acquisition.raw_payloads import mark_payload_normalized, store_raw_payload
from app.acquisition.rate_limit import ProviderRateLimiter
from app.acquisition.reports import build_job_report
from app.config import get_settings
from app.db.models import AcquisitionJob, AcquisitionTask, DailyPrice, Dividend, Fundamental, Stock, StockSplit
from app.providers.base import MarketDataError
from app.providers.factory import get_market_data_provider
from app.providers.mock_provider import MockMarketDataProvider
from app.providers.polygon_provider import PolygonMarketDataProvider

STOCK_RESEARCH_CORE = "STOCK_RESEARCH_CORE"
OPTIONS_RESEARCH_CORE = "OPTIONS_RESEARCH_CORE"

STOCK_RESEARCH_CORE_SYMBOLS = (
    "SPY",
    "QQQ",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "IWM",
)

OPTIONS_RESEARCH_CORE_SYMBOLS = STOCK_RESEARCH_CORE_SYMBOLS


class AcquisitionJobCreateRequest(BaseModel):
    job_name: str
    provider: str = "polygon"
    universe_name: str = STOCK_RESEARCH_CORE
    years: int = Field(default_factory=lambda: get_settings().polygon_historical_years)
    include_prices: bool = True
    include_fundamentals: bool = True
    include_dividends: bool = True
    include_splits: bool = True
    include_options: bool = False
    rate_limit_per_minute: int = Field(default_factory=lambda: get_settings().polygon_rate_limit_per_minute)
    start_date: date | None = None
    end_date: date | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)


def get_campaign_universe(universe_name: str, config_json: dict[str, Any] | None = None) -> list[str]:
    name = universe_name.upper()
    if name == STOCK_RESEARCH_CORE:
        return list(STOCK_RESEARCH_CORE_SYMBOLS)
    if name == OPTIONS_RESEARCH_CORE:
        return list(OPTIONS_RESEARCH_CORE_SYMBOLS)
    if name == "CUSTOM":
        tickers = (config_json or {}).get("tickers") or []
        return [str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()]
    raise LookupError(f"Unknown acquisition universe: {universe_name}")


def _build_task_specs(request: AcquisitionJobCreateRequest) -> list[dict[str, Any]]:
    tickers = get_campaign_universe(request.universe_name, request.config_json)
    end_date = request.end_date or date.today()
    start_date = request.start_date or (end_date - timedelta(days=365 * max(request.years, 1)))
    task_specs: list[dict[str, Any]] = []
    for ticker in tickers:
        if request.include_prices:
            task_specs.append(
                {
                    "task_type": "DAILY_PRICES",
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
        if request.include_fundamentals:
            task_specs.append(
                {
                    "task_type": "FUNDAMENTALS",
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
        if request.include_dividends:
            task_specs.append(
                {
                    "task_type": "DIVIDENDS",
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
        if request.include_splits:
            task_specs.append(
                {
                    "task_type": "SPLITS",
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
        if request.include_options:
            task_specs.append(
                {
                    "task_type": "OPTIONS_CONTRACTS",
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
    return task_specs


def create_acquisition_job(session: Session, request: AcquisitionJobCreateRequest) -> dict[str, Any]:
    tickers = get_campaign_universe(request.universe_name, request.config_json)
    job = AcquisitionJob(
        job_name=request.job_name,
        provider=request.provider,
        status="PENDING",
        universe_name=request.universe_name,
        config_json={
            **request.config_json,
            "tickers": tickers,
            "years": request.years,
            "include_prices": request.include_prices,
            "include_fundamentals": request.include_fundamentals,
            "include_dividends": request.include_dividends,
            "include_splits": request.include_splits,
            "include_options": request.include_options,
            "rate_limit_per_minute": request.rate_limit_per_minute,
            "start_date": request.start_date.isoformat() if request.start_date else None,
            "end_date": request.end_date.isoformat() if request.end_date else None,
        },
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    for spec in _build_task_specs(request):
        session.add(
            AcquisitionTask(
                job_id=job.id or 0,
                task_type=spec["task_type"],
                ticker=spec["ticker"],
                start_date=spec["start_date"],
                end_date=spec["end_date"],
            )
        )
    session.commit()
    return build_job_report(session, job.id or 0)


def list_acquisition_jobs(session: Session) -> list[dict[str, Any]]:
    jobs = list(session.exec(select(AcquisitionJob).order_by(AcquisitionJob.created_at.desc(), AcquisitionJob.id.desc())))
    return [_job_summary(session, job) for job in jobs]


def get_acquisition_job(session: Session, job_id: int) -> dict[str, Any]:
    return build_job_report(session, job_id)


def pause_acquisition_job(session: Session, job_id: int) -> dict[str, Any]:
    job = _get_job_or_raise(session, job_id)
    job.status = "PAUSED"
    session.add(job)
    session.commit()
    return build_job_report(session, job_id)


def resume_acquisition_job(session: Session, job_id: int) -> dict[str, Any]:
    job = _get_job_or_raise(session, job_id)
    if job.status == "PAUSED":
        job.status = "PENDING"
        session.add(job)
        session.commit()
    return build_job_report(session, job_id)


def retry_failed_tasks(session: Session, job_id: int) -> dict[str, Any]:
    job = _get_job_or_raise(session, job_id)
    tasks = list(session.exec(select(AcquisitionTask).where(AcquisitionTask.job_id == job.id, AcquisitionTask.status == "FAILED")))
    for task in tasks:
        task.status = "PENDING"
        task.last_error = None
        session.add(task)
    session.commit()
    return build_job_report(session, job_id)


def run_acquisition_job(
    session: Session,
    job_id: int,
    *,
    force: bool = False,
    provider: Any | None = None,
) -> dict[str, Any]:
    job = _get_job_or_raise(session, job_id)
    if job.status == "PAUSED":
        return {
            **build_job_report(session, job_id),
            "warnings": ["Job is paused; resume it before running."],
        }
    if job.started_at is None:
        job.started_at = datetime.now()
    job.status = "RUNNING"
    session.add(job)
    session.commit()

    resolved_provider = provider or _resolve_provider(job.provider)
    rate_limit_per_minute = int(job.config_json.get("rate_limit_per_minute") or get_settings().polygon_rate_limit_per_minute)
    limiter = ProviderRateLimiter(rate_limit_per_minute) if job.provider.lower() == "polygon" else None
    tasks = list(session.exec(select(AcquisitionTask).where(AcquisitionTask.job_id == job.id)))
    for queue_item in build_queue(tasks):
        task = session.get(AcquisitionTask, queue_item.task_id)
        if task is None or not task_is_runnable(task, force=force):
            continue
        _run_task(session, job, task, resolved_provider, limiter, force=force)

    remaining_failed = list(
        session.exec(
            select(AcquisitionTask).where(AcquisitionTask.job_id == job.id, AcquisitionTask.status == "FAILED")
        )
    )
    remaining_pending = list(
        session.exec(
            select(AcquisitionTask).where(AcquisitionTask.job_id == job.id, AcquisitionTask.status == "PENDING")
        )
    )
    if remaining_failed:
        job.status = "FAILED"
    elif remaining_pending:
        job.status = "RUNNING"
    else:
        job.status = "COMPLETED"
        job.completed_at = datetime.now()
    session.add(job)
    session.commit()
    return build_job_report(session, job_id)


def _run_task(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    *,
    force: bool,
) -> None:
    task.status = "RUNNING"
    task.attempts += 1
    task.started_at = task.started_at or datetime.now()
    session.add(task)
    session.commit()
    request_key = task_request_key(job.id or 0, task, force=force)
    try:
        rows_imported = _dispatch_task(session, job, task, provider, limiter, request_key)
        task.status = "COMPLETED"
        task.rows_imported = rows_imported
        task.last_error = None
        task.completed_at = datetime.now()
    except NotImplementedError as exc:
        task.status = "SKIPPED"
        task.last_error = str(exc)
        task.completed_at = datetime.now()
    except Exception as exc:  # pragma: no cover - bulk guard
        task.status = "FAILED"
        task.last_error = str(exc)
        task.completed_at = datetime.now()
    session.add(task)
    session.commit()


def _dispatch_task(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    request_key: str,
) -> int:
    handler = _TASK_HANDLERS.get(task.task_type)
    if handler is None:
        raise NotImplementedError(f"Task type {task.task_type} is not implemented yet")
    return handler(session, job, task, provider, limiter, request_key)


def _handle_daily_prices(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    request_key: str,
) -> int:
    ticker = task.ticker or ""
    start_date = task.start_date or (date.today() - timedelta(days=365 * max(int(job.config_json.get("years") or 1), 1)))
    end_date = task.end_date or date.today()
    stock_rows = 0

    if not session.exec(select(Stock).where(Stock.ticker == ticker)).first():
        session.add(Stock(ticker=ticker, last_updated=datetime.now()))
        session.commit()

    price_result = call_provider(
        session,
        provider=job.provider,
        endpoint="daily_prices",
        request_key=f"{request_key}:daily_prices",
        ticker=ticker,
        rate_limiter=limiter,
        func=lambda: provider.get_daily_prices(ticker, start_date, end_date),
    )
    price_payload = {"results": price_result.value}
    raw_price = store_raw_payload(
        session,
        provider=job.provider,
        endpoint="daily_prices",
        request_key=f"{request_key}:daily_prices",
        ticker=ticker,
        payload=price_payload,
    )
    stock_rows += _upsert_daily_prices(session, price_result.value)
    mark_payload_normalized(session, raw_price)

    try:
        profile_result = call_provider(
            session,
            provider=job.provider,
            endpoint="ticker_details",
            request_key=f"{request_key}:ticker_details",
            ticker=ticker,
            rate_limiter=limiter,
            func=lambda: provider.get_company_profile(ticker),
        )
        raw_profile = store_raw_payload(
            session,
            provider=job.provider,
            endpoint="ticker_details",
            request_key=f"{request_key}:ticker_details",
            ticker=ticker,
            payload=profile_result.value,
        )
        stock_rows += _upsert_stock_reference(session, profile_result.value)
        mark_payload_normalized(session, raw_profile)
    except MarketDataError:
        pass
    except Exception:
        pass
    return stock_rows


def _handle_fundamentals(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    request_key: str,
) -> int:
    ticker = task.ticker or ""
    payload = call_provider(
        session,
        provider=job.provider,
        endpoint="fundamentals",
        request_key=f"{request_key}:fundamentals",
        ticker=ticker,
        rate_limiter=limiter,
        func=lambda: provider.get_fundamentals(ticker),
    ).value
    raw = store_raw_payload(
        session,
        provider=job.provider,
        endpoint="fundamentals",
        request_key=f"{request_key}:fundamentals",
        ticker=ticker,
        payload=payload,
    )
    rows = _upsert_fundamentals(session, payload)
    mark_payload_normalized(session, raw)
    return rows


def _handle_dividends(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    request_key: str,
) -> int:
    ticker = task.ticker or ""
    dividends = call_provider(
        session,
        provider=job.provider,
        endpoint="dividends",
        request_key=f"{request_key}:dividends",
        ticker=ticker,
        rate_limiter=limiter,
        func=lambda: provider.get_dividends(ticker),
    ).value
    raw = store_raw_payload(
        session,
        provider=job.provider,
        endpoint="dividends",
        request_key=f"{request_key}:dividends",
        ticker=ticker,
        payload={"results": dividends},
    )
    rows = _upsert_dividends(session, dividends)
    mark_payload_normalized(session, raw)
    return rows


def _handle_splits(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    request_key: str,
) -> int:
    ticker = task.ticker or ""
    splits = call_provider(
        session,
        provider=job.provider,
        endpoint="splits",
        request_key=f"{request_key}:splits",
        ticker=ticker,
        rate_limiter=limiter,
        func=lambda: provider.get_splits(ticker) if hasattr(provider, "get_splits") else [],
    ).value
    raw = store_raw_payload(
        session,
        provider=job.provider,
        endpoint="splits",
        request_key=f"{request_key}:splits",
        ticker=ticker,
        payload={"results": splits},
    )
    rows = _upsert_splits(session, splits)
    mark_payload_normalized(session, raw)
    return rows


def _handle_corporate_actions(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    request_key: str,
) -> int:
    rows = 0
    rows += _handle_dividends(session, job, task, provider, limiter, f"{request_key}:corp")
    rows += _handle_splits(session, job, task, provider, limiter, f"{request_key}:corp")
    return rows


def _handle_options_contracts(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter | None,
    request_key: str,
) -> int:
    ticker = task.ticker or ""
    if not hasattr(provider, "get_options_chain_snapshot"):
        raise NotImplementedError("Options chain snapshot is not implemented yet")
    payload = call_provider(
        session,
        provider=job.provider,
        endpoint="options_chain_snapshot",
        request_key=f"{request_key}:options_chain_snapshot",
        ticker=ticker,
        rate_limiter=limiter,
        func=lambda: provider.get_options_chain_snapshot(ticker),
    ).value
    raw = store_raw_payload(
        session,
        provider=job.provider,
        endpoint="options_chain_snapshot",
        request_key=f"{request_key}:options_chain_snapshot",
        ticker=ticker,
        payload=payload,
    )
    mark_payload_normalized(session, raw)
    return 0


def _handle_unimplemented(
    session: Session,
    job: AcquisitionJob,
    task: AcquisitionTask,
    provider: Any,
    limiter: ProviderRateLimiter,
    request_key: str,
) -> int:
    raise NotImplementedError(f"Task type {task.task_type} is scaffolded but not yet implemented")


_TASK_HANDLERS: dict[str, Callable[[Session, AcquisitionJob, AcquisitionTask, Any, ProviderRateLimiter, str], int]] = {
    "DAILY_PRICES": _handle_daily_prices,
    "FUNDAMENTALS": _handle_fundamentals,
    "DIVIDENDS": _handle_dividends,
    "SPLITS": _handle_splits,
    "CORPORATE_ACTIONS": _handle_corporate_actions,
    "FINANCIAL_STATEMENTS": _handle_unimplemented,
    "EARNINGS": _handle_unimplemented,
    "OPTIONS_CONTRACTS": _handle_options_contracts,
    "OPTIONS_AGGREGATES": _handle_unimplemented,
    "OPTIONS_TRADES": _handle_unimplemented,
    "OPTIONS_QUOTES": _handle_unimplemented,
}


def _upsert_stock_reference(session: Session, payload: dict[str, Any]) -> int:
    ticker = str(payload.get("ticker") or payload.get("symbol") or "").strip().upper()
    if not ticker:
        raise ValueError("ticker missing from company profile payload")
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if stock is None:
        stock = Stock(ticker=ticker, last_updated=datetime.now())
    stock.name = payload.get("name") or payload.get("longName") or payload.get("shortName") or ticker
    stock.sector = payload.get("sector")
    stock.industry = payload.get("industry")
    stock.exchange = payload.get("exchange")
    stock.market_cap = _maybe_float(payload.get("market_cap") or payload.get("marketCap"))
    stock.last_updated = datetime.now()
    session.add(stock)
    session.commit()
    return 1


def _upsert_daily_prices(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ticker = str(rows[0]["ticker"]).upper()
    start_date = min(row["price_date"] for row in rows)
    end_date = max(row["price_date"] for row in rows)
    existing_dates = set(
        session.exec(
            select(DailyPrice.price_date).where(
                DailyPrice.ticker == ticker,
                DailyPrice.price_date >= start_date,
                DailyPrice.price_date <= end_date,
            )
        )
    )
    count = 0
    for row in rows:
        if row["price_date"] in existing_dates:
            continue
        session.add(DailyPrice(**row))
        count += 1
    session.commit()
    return count


def _upsert_fundamentals(session: Session, payload: dict[str, Any]) -> int:
    ticker = str(payload.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("ticker missing from fundamentals payload")
    as_of_date = payload.get("as_of_date") or date.today()
    if isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(as_of_date)
    existing = session.exec(
        select(Fundamental).where(Fundamental.ticker == ticker, Fundamental.as_of_date == as_of_date)
    ).first()
    data = {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "revenue_growth": payload.get("revenue_growth"),
        "gross_margin": payload.get("gross_margin"),
        "operating_margin": payload.get("operating_margin"),
        "free_cash_flow": payload.get("free_cash_flow"),
        "return_on_equity": payload.get("return_on_equity"),
        "debt_to_equity": payload.get("debt_to_equity"),
        "interest_coverage": payload.get("interest_coverage"),
        "pe_ratio": payload.get("pe_ratio"),
        "forward_pe": payload.get("forward_pe"),
        "price_to_sales": payload.get("price_to_sales"),
        "price_to_fcf": payload.get("price_to_fcf"),
        "raw": payload.get("raw") or payload.get("_raw") or {},
        "source": payload.get("source") or "polygon",
    }
    if existing is None:
        session.add(Fundamental(**data))
    else:
        for key, value in data.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        session.add(existing)
    session.commit()
    return 1


def _upsert_dividends(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ticker = str(rows[0]["ticker"]).upper()
    existing_dates = set(session.exec(select(Dividend.ex_date).where(Dividend.ticker == ticker)))
    count = 0
    for row in rows:
        if row["ex_date"] in existing_dates:
            continue
        session.add(Dividend(**row))
        count += 1
    session.commit()
    return count


def _upsert_splits(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ticker = str(rows[0]["ticker"]).upper()
    existing_dates = set(session.exec(select(StockSplit.execution_date).where(StockSplit.ticker == ticker)))
    count = 0
    for row in rows:
        if row["execution_date"] in existing_dates:
            continue
        session.add(StockSplit(**row))
        count += 1
    session.commit()
    return count


def _resolve_provider(provider_name: str) -> Any:
    normalized = provider_name.lower()
    if normalized == "mock":
        return MockMarketDataProvider()
    if normalized == "polygon":
        settings = get_settings()
        return PolygonMarketDataProvider(
            api_key=settings.polygon_api_key,
            mode=settings.polygon_mode,
        )
    if normalized == "yfinance":
        return get_market_data_provider("yfinance")
    raise LookupError(f"Unsupported acquisition provider: {provider_name}")


def _get_job_or_raise(session: Session, job_id: int) -> AcquisitionJob:
    job = session.get(AcquisitionJob, job_id)
    if job is None:
        raise LookupError(f"Acquisition job not found: {job_id}")
    return job


def _job_summary(session: Session, job: AcquisitionJob) -> dict[str, Any]:
    tasks = list(session.exec(select(AcquisitionTask).where(AcquisitionTask.job_id == job.id)))
    counts = {
        "PENDING": sum(1 for task in tasks if task.status == "PENDING"),
        "RUNNING": sum(1 for task in tasks if task.status == "RUNNING"),
        "COMPLETED": sum(1 for task in tasks if task.status == "COMPLETED"),
        "FAILED": sum(1 for task in tasks if task.status == "FAILED"),
        "SKIPPED": sum(1 for task in tasks if task.status == "SKIPPED"),
    }
    return {
        **job.model_dump(),
        "task_counts": counts,
        "task_total": len(tasks),
    }


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
