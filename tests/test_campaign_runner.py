from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.acquisition.campaign import (
    StockCampaignRequest,
    build_campaign_plan_from_config,
    build_stock_only_campaign_plan,
    campaign_audit_report,
    campaign_status_report,
    load_stock_campaign_config,
    plan_stock_campaign,
    run_stock_campaign_phase,
)
from app.db.models import CampaignPhaseRun, CampaignRun
from app.db.session import engine


CONFIG_PATH = Path("configs/stock_historical_campaign.yml")


def test_stock_campaign_plan_is_dry_run_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 1, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.estimate_flat_file_plan",
        lambda **kwargs: {"provider": kwargs["provider"], "estimated_files": 2, "estimated_download_size_mb": 1.0},
    )
    monkeypatch.setattr("app.acquisition.campaign.request_universe_tickers", lambda universe_name: ["AAPL", "MSFT"])

    plan = build_stock_only_campaign_plan(
        None,
        StockCampaignRequest(
            provider="polygon",
            universe_name="STOCK_RESEARCH_CORE",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 31),
        ),
    )

    assert plan["campaign"]["live"] is False
    assert len(plan["phases"]) == 6
    assert plan["phases"][0]["name"] == "readiness-report"
    assert plan["phases"][1]["name"] == "stocks_daily-flat-files"
    assert plan["phases"][1]["status"] == "PLANNED"
    assert plan["phases"][5]["status"] == "PLANNED"
    assert plan["summary"]["phase_count"] == 6


def test_stock_campaign_yaml_loads_all_phases(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.estimate_flat_file_plan",
        lambda **kwargs: {"provider": kwargs["provider"], "estimated_files": 2, "estimated_download_size_mb": 1.0},
    )
    monkeypatch.setattr("app.acquisition.campaign.request_universe_tickers", lambda universe_name: ["AAPL", "MSFT"])

    config = load_stock_campaign_config(CONFIG_PATH)
    plan = build_campaign_plan_from_config(config, live=False)

    assert config["campaign_name"] == "stock_historical_campaign"
    assert len(plan["phases"]) == 6
    assert [phase["phase"] for phase in plan["phases"]] == [0, 1, 2, 3, 4, 5]
    assert plan["phases"][1]["name"] == "stocks_daily-flat-files"
    assert plan["phases"][5]["status"] == "PLANNED"


def test_campaign_plan_persists_without_network(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.estimate_flat_file_plan",
        lambda **kwargs: {"provider": kwargs["provider"], "estimated_files": 2, "estimated_download_size_mb": 1.0},
    )
    monkeypatch.setattr("app.acquisition.campaign.request_universe_tickers", lambda universe_name: ["AAPL", "MSFT"])

    with Session(engine) as session:
        report = plan_stock_campaign(session, CONFIG_PATH)
        assert report["campaign_id"] is not None
        assert len(report["phases"]) == 6
        campaign = session.get(CampaignRun, report["campaign_id"])
        assert campaign is not None
        phases = list(session.exec(select(CampaignPhaseRun).where(CampaignPhaseRun.campaign_id == campaign.id)))
        assert len(phases) == 6
        assert all(phase.status == "PLANNED" for phase in phases)


def test_campaign_resume_does_not_duplicate_work(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.estimate_flat_file_plan",
        lambda **kwargs: {"provider": kwargs["provider"], "estimated_files": 2, "estimated_download_size_mb": 1.0},
    )
    monkeypatch.setattr("app.acquisition.campaign.request_universe_tickers", lambda universe_name: ["AAPL", "MSFT"])

    with Session(engine) as session:
        first = plan_stock_campaign(session, CONFIG_PATH)
        second = plan_stock_campaign(session, CONFIG_PATH)
        assert first["campaign_id"] == second["campaign_id"]
        campaigns = list(session.exec(select(CampaignRun).where(CampaignRun.campaign_name == "stock_historical_campaign")))
        phase_rows = list(session.exec(select(CampaignPhaseRun).where(CampaignPhaseRun.campaign_id == first["campaign_id"])))
        assert len(campaigns) == 1
        assert len(phase_rows) == 6


def test_campaign_phase_1_requires_massive_credentials_before_download(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign._phase_1_disk_space_check",
        lambda **kwargs: {"checks": [], "blocker": None, "min_free_bytes": kwargs["min_free_bytes"], "staging_path": "flat_file_staging", "postgres_data_path": None},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.get_settings",
        lambda: SimpleNamespace(
            polygon_flat_file_access_key_id=None,
            polygon_flat_file_secret_access_key=None,
            polygon_rate_limit_per_minute=3,
            flat_file_staging_dir="flat_file_staging",
        ),
    )
    with Session(engine) as session:
        with pytest.raises(ValueError, match="Massive S3 flat-file credentials are missing"):
            run_stock_campaign_phase(
                session,
                CONFIG_PATH,
                phase=1,
                live=True,
                max_files=10,
                max_bytes=1_000_000_000,
            )


def test_campaign_phase_1_enforces_max_files_and_bytes(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign._phase_1_disk_space_check",
        lambda **kwargs: {"checks": [], "blocker": None, "min_free_bytes": kwargs["min_free_bytes"], "staging_path": "flat_file_staging", "postgres_data_path": None},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.get_settings",
        lambda: SimpleNamespace(
            polygon_flat_file_access_key_id="key",
            polygon_flat_file_secret_access_key="secret",
            polygon_rate_limit_per_minute=3,
            flat_file_staging_dir="flat_file_staging",
        ),
    )
    with Session(engine) as session:
        with pytest.raises(ValueError, match="--max-files"):
            run_stock_campaign_phase(session, CONFIG_PATH, phase=1, live=True, max_bytes=1_000_000_000)
        with pytest.raises(ValueError, match="--max-bytes"):
            run_stock_campaign_phase(session, CONFIG_PATH, phase=1, live=True, max_files=10)


def test_campaign_rest_phases_enforce_max_requests(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign._phase_1_disk_space_check",
        lambda **kwargs: {"checks": [], "blocker": None, "min_free_bytes": kwargs["min_free_bytes"], "staging_path": "flat_file_staging", "postgres_data_path": None},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.get_settings",
        lambda: SimpleNamespace(
            polygon_flat_file_access_key_id="key",
            polygon_flat_file_secret_access_key="secret",
            polygon_rate_limit_per_minute=3,
            flat_file_staging_dir="flat_file_staging",
        ),
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.estimate_flat_file_plan",
        lambda **kwargs: {"provider": kwargs["provider"], "estimated_files": 2, "estimated_download_size_mb": 1.0},
    )
    with Session(engine) as session:
        with pytest.raises(ValueError, match="--max-requests"):
            run_stock_campaign_phase(
                session,
                CONFIG_PATH,
                phase=2,
                live=True,
                max_files=10,
                max_bytes=1_000_000_000,
            )


def test_campaign_phase_1_refuses_when_disk_space_is_low(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign._phase_1_disk_space_check",
        lambda **kwargs: {
            "checks": [
                {
                    "check": "staging free space",
                    "status": "FAIL",
                    "path": "flat_file_staging",
                    "free_bytes": 100,
                    "minimum_free_bytes": kwargs["min_free_bytes"],
                }
            ],
            "blocker": "Staging path free space 100 bytes is below min_free_bytes 200.",
            "min_free_bytes": kwargs["min_free_bytes"],
            "staging_path": "flat_file_staging",
            "postgres_data_path": None,
        },
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.get_settings",
        lambda: SimpleNamespace(
            polygon_flat_file_access_key_id="key",
            polygon_flat_file_secret_access_key="secret",
            polygon_rate_limit_per_minute=3,
            flat_file_staging_dir="flat_file_staging",
        ),
    )
    with Session(engine) as session:
        with pytest.raises(ValueError, match="min_free_bytes"):
            run_stock_campaign_phase(
                session,
                CONFIG_PATH,
                phase=1,
                live=True,
                max_files=100000,
                max_bytes=1_000_000_000_000,
                min_free_bytes=200,
            )


def test_campaign_status_and_audit_reports(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.acquisition.campaign.build_acquisition_readiness_report",
        lambda: {"summary": {"pass": 5, "warn": 0, "fail": 0}},
    )
    monkeypatch.setattr(
        "app.acquisition.campaign.estimate_flat_file_plan",
        lambda **kwargs: {"provider": kwargs["provider"], "estimated_files": 2, "estimated_download_size_mb": 1.0},
    )
    monkeypatch.setattr("app.acquisition.campaign.request_universe_tickers", lambda universe_name: ["AAPL", "MSFT"])

    with Session(engine) as session:
        report = plan_stock_campaign(session, CONFIG_PATH)
        status = campaign_status_report(session, report["campaign_id"])
        audit = campaign_audit_report(session, report["campaign_id"])
        assert status["summary"]["phase_count"] == 6
        assert audit["summary"]["phase_count"] == 6
        assert len(audit["phase_audits"]) == 6
