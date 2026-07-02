from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from sqlmodel import Session, select

from app.acquisition.estimates import estimate_acquisition
from app.acquisition.jobs import AcquisitionJobCreateRequest, create_acquisition_job, pause_acquisition_job, retry_failed_tasks, resume_acquisition_job, run_acquisition_job
from app.acquisition.provider_calls import call_provider
from app.acquisition.raw_payloads import mark_payload_normalized, store_raw_payload
from app.acquisition.rate_limit import ProviderRateLimiter
from app.db.models import AcquisitionTask, DailyPrice, Fundamental, ProviderAPICall, RawProviderPayload, Stock, StockSplit
from app.db.session import engine


class StubAcquisitionProvider:
    def __init__(self, *, fail_dividends: bool = False) -> None:
        self.fail_dividends = fail_dividends
        self.calls: Counter[str] = Counter()

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date):
        self.calls["daily_prices"] += 1
        rows = []
        current = start_date
        while current <= end_date:
            rows.append(
                {
                    "ticker": ticker,
                    "price_date": current,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "adj_close": 100.5,
                    "volume": 1_000_000,
                    "source": "mock",
                }
            )
            current += timedelta(days=1)
        return rows

    def get_company_profile(self, ticker: str):
        self.calls["profile"] += 1
        return {
            "ticker": ticker,
            "name": f"{ticker} Corp",
            "sector": "Technology",
            "industry": "Software",
            "exchange": "NASDAQ",
            "market_cap": 100_000_000_000,
            "source": "mock",
        }

    def get_fundamentals(self, ticker: str):
        self.calls["fundamentals"] += 1
        return {
            "ticker": ticker,
            "as_of_date": date(2026, 1, 10),
            "revenue_growth": 0.12,
            "gross_margin": 0.5,
            "operating_margin": 0.25,
            "free_cash_flow": 1_000_000_000,
            "return_on_equity": 0.3,
            "debt_to_equity": 0.4,
            "interest_coverage": 10.0,
            "pe_ratio": 25.0,
            "forward_pe": 22.0,
            "price_to_sales": 8.0,
            "price_to_fcf": 18.0,
            "source": "mock",
        }

    def get_dividends(self, ticker: str):
        self.calls["dividends"] += 1
        if self.fail_dividends:
            raise RuntimeError("dividends failed")
        return [
            {
                "ticker": ticker,
                "ex_date": date(2026, 1, 5),
                "pay_date": date(2026, 1, 20),
                "amount": 0.25,
                "source": "mock",
            }
        ]

    def get_splits(self, ticker: str):
        self.calls["splits"] += 1
        return [
            {
                "ticker": ticker,
                "execution_date": date(2026, 1, 7),
                "split_from": 1,
                "split_to": 2,
                "ratio": 2.0,
                "adjustment_factor": 0.5,
                "raw": {"ticker": ticker},
                "source": "mock",
            }
        ]

    def get_options_chain_snapshot(self, ticker: str):
        self.calls["options_chain_snapshot"] += 1
        return {"ticker": ticker, "results": []}


def _create_custom_job(session: Session, *, provider: str = "mock", years: int = 1):
    request = AcquisitionJobCreateRequest(
        job_name="acq-test",
        provider=provider,
        universe_name="CUSTOM",
        years=years,
        include_prices=True,
        include_fundamentals=True,
        include_dividends=True,
        include_splits=True,
        include_options=False,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        config_json={"tickers": ["AAPL"]},
    )
    return create_acquisition_job(session, request)


def test_acquisition_job_creation_and_run_checkpoint_resume() -> None:
    with Session(engine) as session:
        report = _create_custom_job(session)
        job_id = report["job"]["id"]
        provider = StubAcquisitionProvider()

        run_report = run_acquisition_job(session, job_id, provider=provider)
        assert run_report["job"]["status"] == "COMPLETED"
        assert run_report["task_counts"]["COMPLETED"] >= 4
        assert provider.calls["daily_prices"] == 1
        assert provider.calls["profile"] == 1
        assert provider.calls["fundamentals"] == 1
        assert provider.calls["dividends"] == 1
        assert provider.calls["splits"] == 1

        rerun_report = run_acquisition_job(session, job_id, provider=provider)
        assert rerun_report["job"]["status"] == "COMPLETED"
        assert provider.calls["daily_prices"] == 1
        assert provider.calls["profile"] == 1
        assert provider.calls["fundamentals"] == 1
        assert provider.calls["dividends"] == 1
        assert provider.calls["splits"] == 1

        stock = session.exec(select(Stock).where(Stock.ticker == "AAPL")).first()
        assert stock is not None
        assert session.exec(select(DailyPrice).where(DailyPrice.ticker == "AAPL")).first() is not None
        assert session.exec(select(Fundamental).where(Fundamental.ticker == "AAPL")).first() is not None
        assert session.exec(select(StockSplit).where(StockSplit.ticker == "AAPL")).first() is not None


def test_acquisition_pause_resume_and_retry_failed() -> None:
    with Session(engine) as session:
        report = _create_custom_job(session)
        job_id = report["job"]["id"]
        provider = StubAcquisitionProvider(fail_dividends=True)

        paused = pause_acquisition_job(session, job_id)
        assert paused["job"]["status"] == "PAUSED"
        paused_run = run_acquisition_job(session, job_id, provider=provider)
        assert paused_run["job"]["status"] == "PAUSED"
        assert provider.calls == Counter()

        resumed = resume_acquisition_job(session, job_id)
        assert resumed["job"]["status"] in {"PENDING", "RUNNING", "COMPLETED"}
        run_acquisition_job(session, job_id, provider=provider)
        failed_task = session.exec(
            select(AcquisitionTask).where(AcquisitionTask.job_id == job_id, AcquisitionTask.task_type == "DIVIDENDS")
        ).first()
        assert failed_task is not None and failed_task.status == "FAILED"

        retry_failed_tasks(session, job_id)
        retried_task = session.exec(
            select(AcquisitionTask).where(AcquisitionTask.job_id == job_id, AcquisitionTask.task_type == "DIVIDENDS")
        ).first()
        assert retried_task is not None and retried_task.status == "PENDING"

        provider.fail_dividends = False
        final_report = run_acquisition_job(session, job_id, provider=provider)
        assert final_report["job"]["status"] == "COMPLETED"
        assert provider.calls["dividends"] >= 2


def test_provider_call_logging_and_raw_payload_storage() -> None:
    with Session(engine) as session:
        result = call_provider(
            session,
            provider="polygon",
            endpoint="daily_prices",
            request_key="job:1:daily_prices",
            ticker="AAPL",
            func=lambda: {"results": [{"ticker": "AAPL"}]},
        )
        assert result.value["results"][0]["ticker"] == "AAPL"
        call_row = session.exec(select(ProviderAPICall)).first()
        assert call_row is not None and call_row.success is True and call_row.endpoint == "daily_prices"

        raw = store_raw_payload(
            session,
            provider="polygon",
            endpoint="daily_prices",
            request_key="job:1:daily_prices",
            ticker="AAPL",
            payload={"results": [{"ticker": "AAPL", "date": date(2026, 1, 1)}]},
        )
        assert raw.normalized is False
        assert raw.payload_json["results"][0]["date"] == "2026-01-01"
        mark_payload_normalized(session, raw)
        refreshed = session.get(RawProviderPayload, raw.id)
        assert refreshed is not None and refreshed.normalized is True and refreshed.normalized_at is not None


def test_normalization_failure_keeps_raw_payload(monkeypatch) -> None:
    with Session(engine) as session:
        report = _create_custom_job(session)
        job_id = report["job"]["id"]
        provider = StubAcquisitionProvider()

        monkeypatch.setattr("app.acquisition.jobs._upsert_daily_prices", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad normalization")))
        run_acquisition_job(session, job_id, provider=provider)
        raw_payload = session.exec(select(RawProviderPayload).where(RawProviderPayload.endpoint == "daily_prices")).first()
        task = session.exec(select(AcquisitionTask).where(AcquisitionTask.job_id == job_id, AcquisitionTask.task_type == "DAILY_PRICES")).first()
        assert raw_payload is not None
        assert raw_payload.normalized is False
        assert task is not None and task.status == "FAILED"


def test_rate_limiter_and_estimator() -> None:
    sleeps: list[float] = []
    current_time = {"value": 0.0}

    def clock() -> float:
        return current_time["value"]

    limiter = ProviderRateLimiter(60, clock=clock, sleeper=sleeps.append)
    limiter.acquire("polygon")
    current_time["value"] = 0.2
    limiter.acquire("polygon")
    assert sleeps and 0.7 < sleeps[0] < 0.9

    estimate = estimate_acquisition(
        provider="polygon",
        universe_name="STOCK_RESEARCH_CORE",
        years=2,
        include_prices=True,
        include_fundamentals=True,
        include_options=False,
        rate_limit_per_minute=3,
    )
    assert estimate["estimated_api_calls"] > 0
    assert "us_stocks_sip/day_aggs_v1" in estimate["flat_files"]
    assert estimate["provider"] == "polygon"
