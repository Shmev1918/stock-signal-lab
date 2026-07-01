from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

os.environ.setdefault("DATABASE_URL", "sqlite:///./stock_signal_lab_test.db")

from app.db.models import (  # noqa: E402
    BacktestResult,
    BacktestRun,
    Experiment,
    ExperimentResult,
    DailyPrice,
    Dividend,
    Fundamental,
    NewsItem,
    InvestmentDecision,
    Recommendation,
    Stock,
    StockScore,
    StockSignal,
    WatchlistItem,
)
from app.db.session import engine, init_db
from app.main import app
from sqlmodel import Session


TABLES = [
    BacktestResult,
    BacktestRun,
    Experiment,
    ExperimentResult,
    DailyPrice,
    Dividend,
    Fundamental,
    NewsItem,
    InvestmentDecision,
    Recommendation,
    StockScore,
    StockSignal,
    WatchlistItem,
    Stock,
]


@pytest.fixture(scope="session", autouse=True)
def _ensure_tables() -> None:
    if Path("stock_signal_lab_test.db").exists():
        Path("stock_signal_lab_test.db").unlink()
    SQLModel.metadata.drop_all(engine)
    init_db()


@pytest.fixture(autouse=True)
def _clean_db() -> Generator[None, None, None]:
    with Session(engine) as session:
        for table in TABLES:
            session.exec(table.__table__.delete())
        session.commit()
    yield


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
