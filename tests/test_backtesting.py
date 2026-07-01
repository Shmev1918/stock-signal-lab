from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.backtesting.runner import BacktestRequest, run_backtest
from app.db.models import BacktestRun
from app.db.session import engine
from app.providers.mock_provider import MockMarketDataProvider


def test_backtest_scaffold_runs() -> None:
    with Session(engine) as session:
        result = run_backtest(
            session,
            BacktestRequest(
                name="test",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                universe=["AAPL"],
            ),
        )
        assert "metrics" in result
        assert "portfolio" in result


def test_backtest_metadata_is_persisted() -> None:
    with Session(engine) as session:
        run_backtest(
            session,
            BacktestRequest(
                name="metadata",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                universe=["AAPL"],
            ),
        )
        rows = list(session.exec(select(BacktestRun).where(BacktestRun.name == "metadata")))
        assert rows
        row = rows[-1]
        assert row.provider in {"mock", "yfinance"}
        assert row.scoring_model_version == "0.1.0"
        assert row.signal_model_version == "0.1.0"
        assert row.run_timestamp is not None


def test_backtesting_uses_provider_factory(monkeypatch) -> None:
    calls = {"prices": 0}

    class StubProvider(MockMarketDataProvider):
        def get_daily_prices(self, ticker: str, start_date: date, end_date: date):
            calls["prices"] += 1
            return super().get_daily_prices(ticker, start_date, end_date)

    monkeypatch.setattr("app.backtesting.runner.get_market_data_provider", lambda: StubProvider())

    with Session(engine) as session:
        run_backtest(
            session,
            BacktestRequest(
                name="factory",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 1),
                universe=["AAPL"],
            ),
        )

    assert calls["prices"] >= 1
