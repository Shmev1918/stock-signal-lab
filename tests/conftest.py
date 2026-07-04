from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

TEST_DB_PATH = Path(tempfile.gettempdir()) / f"stock_signal_lab_test_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["MARKET_DATA_PROVIDER"] = "mock"

from app.db.models import (  # noqa: E402
    AcquisitionJob,
    AcquisitionTask,
    CampaignPhaseRun,
    CampaignRun,
    BacktestResult,
    BacktestRun,
    Experiment,
    ExperimentResult,
    FlatFileManifest,
    ProviderAPICall,
    DailyPrice,
    Dividend,
    Fundamental,
    NewsItem,
    InvestmentDecision,
    RawProviderPayload,
    Recommendation,
    Security,
    FlatFileQualityEvent,
    RawPolygonStockDailyBar,
    StockDailyPrice,
    Stock,
    StockScore,
    StockSignal,
    StockSplit,
    WatchlistItem,
)
from app.db.session import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from sqlmodel import Session  # noqa: E402


TABLES = [
    AcquisitionTask,
    AcquisitionJob,
    CampaignRun,
    CampaignPhaseRun,
    BacktestResult,
    BacktestRun,
    Experiment,
    ExperimentResult,
    FlatFileManifest,
    DailyPrice,
    Dividend,
    Fundamental,
    NewsItem,
    InvestmentDecision,
    ProviderAPICall,
    RawProviderPayload,
    Recommendation,
    StockScore,
    StockSignal,
    StockSplit,
    FlatFileQualityEvent,
    RawPolygonStockDailyBar,
    StockDailyPrice,
    Security,
    WatchlistItem,
    Stock,
]


@pytest.fixture(scope="session", autouse=True)
def _ensure_tables() -> None:
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
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
