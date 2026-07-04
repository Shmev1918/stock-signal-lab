from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import Session
from sqlmodel import select

from app.acquisition.flat_files import FlatFileImportService, estimate_flat_file_plan
from app.acquisition.jobs import (
    AcquisitionJobCreateRequest,
    STOCK_RESEARCH_CORE,
    create_acquisition_job,
    run_acquisition_job,
)
from app.acquisition.readiness import build_acquisition_readiness_report
from app.acquisition.raw_payloads import sanitize_json
from app.config import get_settings
from app.db.models import CampaignPhaseRun, CampaignRun
from app.providers.flat_file_provider import PolygonFlatFileProvider


DEFAULT_MIN_FREE_BYTES = int(1.5 * 1024**4)


@dataclass(frozen=True)
class StockCampaignRequest:
    provider: str = "polygon"
    universe_name: str = "STOCK_RESEARCH_CORE"
    market: str = "US"
    start_date: date | None = None
    end_date: date | None = None
    live: bool = False
    force_reingest: bool = False
    staging_dir: str | Path | None = None
    max_flat_files: int | None = None
    max_rest_requests: int | None = None
    max_total_requests: int | None = None
    min_free_bytes: int | None = None


def build_stock_only_campaign_plan(session: Session | None, request: StockCampaignRequest) -> dict[str, Any]:
    if request.start_date is None or request.end_date is None:
        raise ValueError("Stock campaign requires start_date and end_date")
    settings = get_settings()
    phases: list[dict[str, Any]] = []
    readiness_audit = build_acquisition_readiness_report()
    readiness_summary = readiness_audit.get("summary", {})
    readiness_status = "PLANNED"
    if request.live:
        if isinstance(readiness_summary, dict) and int(readiness_summary.get("fail", 0) or 0) > 0:
            readiness_status = "BLOCKED"
        elif isinstance(readiness_summary, dict) and int(readiness_summary.get("warn", 0) or 0) > 0:
            readiness_status = "WARN"
        else:
            readiness_status = "COMPLETED"

    phases.append(
        {
            "phase": 0,
            "name": "readiness-report",
            "status": readiness_status,
            "mode": "diagnostic",
            "description": "Inspect local DB, Alembic, and acquisition guardrails.",
            "audit": readiness_audit,
        }
    )

    flat_file_plan = estimate_flat_file_plan(
        provider=request.provider,
        dataset="stocks_daily",
        market=request.market,
        start_date=request.start_date,
        end_date=request.end_date,
        staging_dir=request.staging_dir,
    )
    flat_file_status = "PLANNED"
    flat_file_blocker: str | None = None
    flat_file_disk_audit: dict[str, Any] | None = None
    if request.live:
        flat_file_status = "READY"
        if request.provider.lower() != "polygon":
            flat_file_status = "BLOCKED"
            flat_file_blocker = "Stock campaign flat files currently target Polygon/Massive only."
        elif not _has_massive_flat_file_credentials(settings):
            flat_file_status = "BLOCKED"
            flat_file_blocker = "Massive S3 flat-file credentials are missing."
        else:
            flat_file_disk_audit = _phase_1_disk_space_check(
                staging_dir=request.staging_dir or settings.flat_file_staging_dir,
                min_free_bytes=int(request.min_free_bytes or DEFAULT_MIN_FREE_BYTES),
                settings=settings,
            )
            if flat_file_disk_audit["blocker"]:
                flat_file_status = "BLOCKED"
                flat_file_blocker = str(flat_file_disk_audit["blocker"])
            elif request.max_flat_files is None:
                flat_file_status = "BLOCKED"
                flat_file_blocker = "Live phase 1 requires --max-flat-files."
            elif int(flat_file_plan["estimated_files"]) > int(request.max_flat_files):
                flat_file_status = "BLOCKED"
                flat_file_blocker = (
                    f"Estimated files {flat_file_plan['estimated_files']} exceed max_flat_files {request.max_flat_files}."
                )
    phases.append(
        {
            "phase": 1,
            "name": "stocks_daily-flat-files",
            "status": flat_file_status,
            "mode": "flat_files",
            "description": "Bulk stock history via Massive flat files into staging -> raw landing -> canonical prices.",
            "estimate": flat_file_plan,
            "audit": {
                "estimate": flat_file_plan,
                "blocker": flat_file_blocker,
                "disk": flat_file_disk_audit,
            },
            "blocker": flat_file_blocker,
        }
    )

    rest_phases = [
        (
            2,
            "corporate-actions-rest",
            {
                "include_prices": False,
                "include_metadata": False,
                "include_fundamentals": False,
                "include_dividends": True,
                "include_splits": True,
                "include_options": False,
            },
            "Dividend and split backfill via Polygon REST.",
        ),
        (
            3,
            "security-reference-rest",
            {
                "include_prices": False,
                "include_metadata": True,
                "include_fundamentals": False,
                "include_dividends": False,
                "include_splits": False,
                "include_options": False,
            },
            "Ticker/reference metadata normalization via Polygon REST.",
        ),
        (
            4,
            "financial-statements-rest",
            {
                "include_prices": False,
                "include_metadata": False,
                "include_fundamentals": True,
                "include_dividends": False,
                "include_splits": False,
                "include_options": False,
            },
            "Financial statements / fundamentals normalization via Polygon REST.",
        ),
    ]

    estimated_rest_requests = 0
    rest_tickers = request_universe_tickers(request.universe_name)
    for phase_number, name, job_flags, description in rest_phases:
        estimate = _estimate_rest_phase(
            provider=request.provider,
            tickers=rest_tickers,
            job_flags=job_flags,
            rate_limit_per_minute=max(int(settings.polygon_rate_limit_per_minute or 3), 1),
        )
        estimated_rest_requests += int(estimate["estimated_api_calls"])
        status = "PLANNED"
        blocker: str | None = None
        if request.live:
            status = "READY"
            if request.provider.lower() != "polygon":
                status = "BLOCKED"
                blocker = "REST campaign phases currently target Polygon only."
            elif request.max_rest_requests is None:
                status = "BLOCKED"
                blocker = "Live REST phases require --max-rest-requests."
            elif int(estimate["estimated_api_calls"]) > int(request.max_rest_requests):
                status = "BLOCKED"
                blocker = f"Estimated requests {estimate['estimated_api_calls']} exceed max_rest_requests {request.max_rest_requests}."
        phases.append(
            {
                "phase": phase_number,
                "name": name,
                "status": status,
                "mode": "rest",
                "description": description,
                "estimate": estimate,
                "audit": {"estimate": estimate, "blocker": blocker},
                "job_flags": job_flags,
                "blocker": blocker,
            }
        )

    phases.append(
        {
            "phase": 5,
            "name": "earnings-ratios-rest",
            "status": "PLANNED" if not request.live else "BLOCKED",
            "mode": "rest",
            "description": "Earnings and ratios REST is planned but not yet wired into the acquisition runner.",
            "estimate": {
                "provider": request.provider,
                "estimated_api_calls": 0,
                "estimated_rows": 0,
            },
            "audit": {
                "message": "Earnings / ratios REST is not yet wired into the acquisition runner.",
                "next_step": "Add provider support and task handlers before enabling this phase.",
            },
            "blocker": "Polygon earnings/ratios importer is scaffolded but not implemented yet.",
        }
    )

    warnings: list[str] = []
    if request.live and request.max_total_requests is not None and estimated_rest_requests > int(request.max_total_requests):
        warnings.append(
            f"Planned REST requests {estimated_rest_requests} exceed max_total_requests {request.max_total_requests}."
        )
    if request.live and not _has_massive_flat_file_credentials(settings):
        warnings.append("Massive S3 credentials are missing; phase 1 cannot download flat files.")
    return {
        "campaign": {
            "provider": request.provider,
            "universe_name": request.universe_name,
            "market": request.market,
            "live": request.live,
            "force_reingest": request.force_reingest,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "max_flat_files": request.max_flat_files,
            "max_rest_requests": request.max_rest_requests,
            "max_total_requests": request.max_total_requests,
        },
        "phases": phases,
        "warnings": warnings,
        "summary": {
            "phase_count": len(phases),
            "plannable_phases": sum(1 for phase in phases if phase["status"] in {"PLANNED", "READY", "COMPLETED", "PARTIAL"}),
            "blocked_phases": sum(1 for phase in phases if phase["status"] == "BLOCKED"),
        },
    }


def run_stock_only_campaign(session: Session, request: StockCampaignRequest) -> dict[str, Any]:
    plan = build_stock_only_campaign_plan(session, request)
    if not request.live:
        return plan

    settings = get_settings()
    phases = plan["phases"]

    phases[0]["audit"] = build_acquisition_readiness_report()
    if phases[0]["status"] == "BLOCKED":
        plan["warnings"].append("Live execution stopped after readiness report because phase 0 blocked the campaign.")
        plan["summary"] = {
            **plan["summary"],
            "live": True,
            "blocked_phases": sum(1 for phase in phases if phase["status"] == "BLOCKED"),
            "stopped_after_phase": 0,
        }
        return plan

    phase1 = phases[1]
    if phase1["status"] != "BLOCKED":
        try:
            disk_audit = _phase_1_disk_space_check(
                staging_dir=request.staging_dir or settings.flat_file_staging_dir,
                min_free_bytes=int(request.min_free_bytes or DEFAULT_MIN_FREE_BYTES),
                settings=settings,
            )
            if disk_audit["blocker"]:
                raise ValueError(str(disk_audit["blocker"]))
            provider = PolygonFlatFileProvider(
                access_key_id=settings.polygon_flat_file_access_key_id,
                secret_access_key=settings.polygon_flat_file_secret_access_key,
                endpoint_url=settings.polygon_flat_file_endpoint,
                bucket_name=settings.polygon_flat_file_bucket,
                region=settings.polygon_flat_file_region,
            )
            staging_dir = Path(request.staging_dir or settings.flat_file_staging_dir)
            service = FlatFileImportService(session, provider, staging_dir)
            phase1["audit"] = service.run(
                "stocks_daily",
                start_date=request.start_date or date.today(),
                end_date=request.end_date or date.today(),
                market=request.market,
                force=request.force_reingest,
            )
            if phase1["audit"]["files_failed"] == 0:
                phase1["status"] = "COMPLETED"
            elif phase1["audit"]["files_downloaded"] > 0:
                phase1["status"] = "PARTIAL"
            else:
                phase1["status"] = "FAILED"
        except Exception as exc:  # pragma: no cover - defensive campaign guard
            phase1["status"] = "FAILED"
            phase1["audit"] = {"error": str(exc)}

    rest_phase_configs = [
        (
            2,
            "phase2",
            {
                "include_prices": False,
                "include_metadata": False,
                "include_fundamentals": False,
                "include_dividends": True,
                "include_splits": True,
                "include_options": False,
            },
        ),
        (
            3,
            "phase3",
            {
                "include_prices": False,
                "include_metadata": True,
                "include_fundamentals": False,
                "include_dividends": False,
                "include_splits": False,
                "include_options": False,
            },
        ),
        (
            4,
            "phase4",
            {
                "include_prices": False,
                "include_metadata": False,
                "include_fundamentals": True,
                "include_dividends": False,
                "include_splits": False,
                "include_options": False,
            },
        ),
    ]
    for phase_number, phase_name, job_flags in rest_phase_configs:
        phase = phases[phase_number]
        if phase["status"] == "BLOCKED":
            continue
        job_request = AcquisitionJobCreateRequest(
            job_name=f"stock-campaign-{phase_name}-{request.start_date.isoformat()}-{request.end_date.isoformat()}",
            provider=request.provider,
            universe_name=request.universe_name,
            years=max(_campaign_years(request.start_date, request.end_date), 1),
            include_prices=job_flags["include_prices"],
            include_metadata=job_flags["include_metadata"],
            include_fundamentals=job_flags["include_fundamentals"],
            include_dividends=job_flags["include_dividends"],
            include_splits=job_flags["include_splits"],
            include_options=job_flags["include_options"],
            rate_limit_per_minute=int(settings.polygon_rate_limit_per_minute or 3),
            start_date=request.start_date,
            end_date=request.end_date,
            config_json=sanitize_json({"tickers": request_universe_tickers(request.universe_name)}),
        )
        job_report = create_acquisition_job(session, job_request)
        job_id = int(job_report["job"]["id"])
        try:
            run_report = run_acquisition_job(
                session,
                job_id,
                live=True,
                max_requests=request.max_rest_requests,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            phase["audit"] = {
                "created_job": job_report,
                "run_report": run_report,
            }
            phase["status"] = run_report["job"]["status"]
        except Exception as exc:  # pragma: no cover - defensive campaign guard
            phase["status"] = "FAILED"
            phase["audit"] = {
                "created_job": job_report,
                "error": str(exc),
            }

    phase5 = phases[5]
    phase5["audit"] = {
        "message": "Earnings / ratios REST is not yet wired into the acquisition runner.",
        "next_step": "Add provider support and task handlers before enabling this phase.",
    }
    if request.live:
        phase5["status"] = "BLOCKED"

    plan["summary"] = {
        **plan["summary"],
        "completed_phases": sum(1 for phase in phases if phase["status"] == "COMPLETED"),
        "partial_phases": sum(1 for phase in phases if phase["status"] == "PARTIAL"),
        "failed_phases": sum(1 for phase in phases if phase["status"] == "FAILED"),
        "blocked_phases": sum(1 for phase in phases if phase["status"] == "BLOCKED"),
        "live": True,
    }
    return plan


def request_universe_tickers(universe_name: str) -> list[str]:
    from app.acquisition.jobs import get_campaign_universe

    return get_campaign_universe(universe_name, {})


def _campaign_years(start_date: date | None, end_date: date | None) -> int:
    if start_date is None or end_date is None:
        return 1
    delta = max((end_date - start_date).days, 1)
    return max(int(round(delta / 365.0)), 1)


def _estimate_rest_phase(
    *,
    provider: str,
    tickers: list[str],
    job_flags: dict[str, bool],
    rate_limit_per_minute: int,
) -> dict[str, Any]:
    from app.acquisition.jobs import _polygon_task_request_weight

    task_types: list[str] = []
    if job_flags["include_prices"]:
        task_types.append("DAILY_PRICES")
    if job_flags["include_metadata"]:
        task_types.append("TICKER_METADATA")
    if job_flags["include_fundamentals"]:
        task_types.append("FUNDAMENTALS")
    if job_flags["include_dividends"]:
        task_types.append("DIVIDENDS")
    if job_flags["include_splits"]:
        task_types.append("SPLITS")
    if job_flags["include_options"]:
        task_types.append("OPTIONS_CONTRACTS")

    estimated_api_calls = sum(_polygon_task_request_weight(task_type) for task_type in task_types) * len(tickers)
    estimated_rows = len(tickers) * max(len(task_types), 1)
    return {
        "provider": provider,
        "tickers": len(tickers),
        "estimated_api_calls": estimated_api_calls,
        "estimated_rows": estimated_rows,
        "rate_limit_per_minute": rate_limit_per_minute,
        "task_types": task_types,
    }


def load_stock_campaign_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Campaign config must be a mapping: {path}")
    return _normalize_campaign_config(raw, source_path=path)


def _normalize_campaign_config(raw: dict[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    phases = raw.get("phases") or []
    if not isinstance(phases, list) or not phases:
        raise ValueError("Campaign config must define a non-empty phases list.")
    normalized_phases: list[dict[str, Any]] = []
    seen_phases: set[int] = set()
    for entry in phases:
        if not isinstance(entry, dict):
            raise ValueError("Campaign phases must be mappings.")
        phase_number = int(entry.get("phase"))
        if phase_number in seen_phases:
            raise ValueError(f"Duplicate campaign phase number: {phase_number}")
        seen_phases.add(phase_number)
        normalized_phases.append(
            {
                **entry,
                "phase": phase_number,
                "name": str(entry.get("name") or f"phase-{phase_number}"),
                "type": str(entry.get("type") or entry.get("kind") or "rest"),
                "description": str(entry.get("description") or ""),
                "implemented": bool(entry.get("implemented", True)),
                "start_date": _normalize_campaign_date(entry.get("start_date")),
                "end_date": _normalize_campaign_date(entry.get("end_date")),
                "job_flags": dict(entry.get("job_flags") or {}),
                "datasets": list(entry.get("datasets") or []),
                "tickers": list(entry.get("tickers") or []),
            }
        )
    normalized_phases.sort(key=lambda row: row["phase"])
    return {
        "campaign_name": str(raw.get("campaign_name") or "stock_historical_campaign"),
        "provider": str(raw.get("provider") or "polygon"),
        "universe_name": str(raw.get("universe_name") or STOCK_RESEARCH_CORE),
        "market": str(raw.get("market") or "US"),
        "description": str(raw.get("description") or ""),
        "staging_dir": raw.get("staging_dir"),
        "start_date": _normalize_campaign_date(raw.get("start_date")) or date.today(),
        "end_date": _normalize_campaign_date(raw.get("end_date")) or date.today(),
        "phases": normalized_phases,
        "source_path": str(source_path) if source_path else None,
    }


def _normalize_campaign_date(value: Any) -> date | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, date):
        return value
    value_str = str(value).strip().lower()
    if value_str in {"current", "current-date", "today"}:
        return date.today()
    return date.fromisoformat(str(value))


def _campaign_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _phase_job_flags(phase_def: dict[str, Any]) -> dict[str, bool]:
    job_flags = dict(phase_def.get("job_flags") or {})
    if job_flags:
        return {
            "include_prices": bool(job_flags.get("include_prices", False)),
            "include_metadata": bool(job_flags.get("include_metadata", False)),
            "include_fundamentals": bool(job_flags.get("include_fundamentals", False)),
            "include_dividends": bool(job_flags.get("include_dividends", False)),
            "include_splits": bool(job_flags.get("include_splits", False)),
            "include_options": bool(job_flags.get("include_options", False)),
        }
    datasets = {str(item).strip().lower() for item in phase_def.get("datasets") or []}
    return {
        "include_prices": "daily_prices" in datasets or "prices" in datasets,
        "include_metadata": "security_reference" in datasets or "ticker_metadata" in datasets,
        "include_fundamentals": "financial_statements" in datasets or "fundamentals" in datasets or "ratios" in datasets,
        "include_dividends": "dividends" in datasets,
        "include_splits": "splits" in datasets,
        "include_options": "options" in datasets or "options_contracts" in datasets,
    }


def _readiness_phase_report() -> dict[str, Any]:
    return build_acquisition_readiness_report()


def _has_massive_flat_file_credentials(settings: Any) -> bool:
    return bool(settings.polygon_flat_file_access_key_id and settings.polygon_flat_file_secret_access_key)


def _resolve_existing_path(path: Path) -> Path | None:
    candidate = path.expanduser()
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate if candidate.exists() else None


def _disk_free_bytes(path: Path) -> int | None:
    resolved = _resolve_existing_path(path)
    if resolved is None:
        return None
    try:
        return int(shutil.disk_usage(resolved).free)
    except OSError:
        return None


def _postgres_data_path(settings: Any) -> Path | None:
    for candidate in (
        getattr(settings, "postgres_data_dir", None),
        os.getenv("POSTGRES_DATA_DIR"),
        os.getenv("PGDATA"),
    ):
        if candidate:
            return Path(candidate)
    return None


def _phase_1_disk_space_check(*, staging_dir: str | Path, min_free_bytes: int, settings: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blocker: str | None = None

    staging_path = Path(staging_dir)
    staging_free = _disk_free_bytes(staging_path)
    if staging_free is None:
        checks.append(
            {
                "check": "staging free space",
                "path": str(staging_path),
                "status": "WARN",
                "detail": "Unable to determine free space for staging path.",
            }
        )
    else:
        staging_status = "PASS" if staging_free >= int(min_free_bytes) else "FAIL"
        checks.append(
            {
                "check": "staging free space",
                "path": str(staging_path),
                "status": staging_status,
                "free_bytes": staging_free,
                "minimum_free_bytes": int(min_free_bytes),
                "detail": f"{staging_free} free bytes available.",
            }
        )
        if staging_status == "FAIL":
            blocker = f"Staging path free space {staging_free} bytes is below min_free_bytes {min_free_bytes}."

    postgres_path = _postgres_data_path(settings)
    if postgres_path is None:
        checks.append(
            {
                "check": "postgres data free space",
                "path": None,
                "status": "SKIP",
                "detail": "Postgres data path is not detectable in this environment.",
            }
        )
    else:
        postgres_free = _disk_free_bytes(postgres_path)
        if postgres_free is None:
            checks.append(
                {
                    "check": "postgres data free space",
                    "path": str(postgres_path),
                    "status": "WARN",
                    "detail": "Unable to determine free space for Postgres data path.",
                }
            )
        else:
            postgres_status = "PASS" if postgres_free >= int(min_free_bytes) else "FAIL"
            checks.append(
                {
                    "check": "postgres data free space",
                    "path": str(postgres_path),
                    "status": postgres_status,
                    "free_bytes": postgres_free,
                    "minimum_free_bytes": int(min_free_bytes),
                    "detail": f"{postgres_free} free bytes available.",
                }
            )
            if postgres_status == "FAIL" and blocker is None:
                blocker = f"Postgres data path free space {postgres_free} bytes is below min_free_bytes {min_free_bytes}."

    return {
        "checks": checks,
        "blocker": blocker,
        "min_free_bytes": int(min_free_bytes),
        "staging_path": str(staging_path),
        "postgres_data_path": str(postgres_path) if postgres_path is not None else None,
    }


def _persist_campaign_plan(
    session: Session,
    config: dict[str, Any],
    plan: dict[str, Any],
) -> CampaignRun:
    config_hash = _campaign_config_hash(config)
    campaign = session.exec(
        select(CampaignRun).where(
            CampaignRun.campaign_name == config["campaign_name"],
            CampaignRun.config_hash == config_hash,
        )
    ).first()
    if campaign is None:
        campaign = CampaignRun(
            campaign_name=config["campaign_name"],
            config_path=config.get("source_path"),
            config_hash=config_hash,
            provider=config["provider"],
            universe_name=config["universe_name"],
            market=config["market"],
            status="PLANNED",
            live=bool(plan["campaign"]["live"]),
            config_json=sanitize_json(config),
            audit_json=sanitize_json({"summary": plan.get("summary", {}), "warnings": plan.get("warnings", [])}),
            warning_json=sanitize_json({"warnings": plan.get("warnings", [])}),
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
    else:
        campaign.config_path = config.get("source_path")
        campaign.provider = config["provider"]
        campaign.universe_name = config["universe_name"]
        campaign.market = config["market"]
        campaign.config_json = sanitize_json(config)
        campaign.updated_at = datetime.now()
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

    _sync_phase_rows(session, campaign, config, plan)
    return campaign


def _sync_phase_rows(session: Session, campaign: CampaignRun, config: dict[str, Any], plan: dict[str, Any]) -> None:
    for phase_report in plan.get("phases", []):
        phase_number = int(phase_report["phase"])
        phase_row = session.exec(
            select(CampaignPhaseRun).where(
                CampaignPhaseRun.campaign_id == campaign.id,
                CampaignPhaseRun.phase_number == phase_number,
            )
        ).first()
        phase_def = next((item for item in config["phases"] if int(item["phase"]) == phase_number), None)
        if phase_def is None:
            continue
        payload = {
            "campaign_id": campaign.id or 0,
            "phase_number": phase_number,
            "phase_name": phase_report["name"],
            "phase_type": phase_def["type"],
            "status": phase_report["status"],
            "mode": phase_report["mode"],
            "description": phase_report.get("description"),
            "config_json": sanitize_json(phase_def),
            "estimate_json": sanitize_json(phase_report.get("estimate", {})),
            "audit_json": sanitize_json(phase_report.get("audit", {})),
            "blocker": phase_report.get("blocker"),
        }
        if phase_row is None:
            phase_row = CampaignPhaseRun(**payload)
            session.add(phase_row)
        else:
            if phase_row.status in {"PLANNED", "READY", "WARN"}:
                for key, value in payload.items():
                    setattr(phase_row, key, value)
            else:
                phase_row.phase_name = phase_report["name"]
                phase_row.phase_type = phase_def["type"]
                phase_row.description = phase_report.get("description")
                phase_row.config_json = sanitize_json(phase_def)
                if phase_row.status in {"FAILED", "BLOCKED", "PARTIAL", "COMPLETED", "SKIPPED"}:
                    phase_row.estimate_json = phase_row.estimate_json or phase_report.get("estimate", {})
            phase_row.updated_at = datetime.now()
            session.add(phase_row)
    session.commit()


def _campaign_phase_report(phase_row: CampaignPhaseRun) -> dict[str, Any]:
    return {
        "phase": phase_row.phase_number,
        "name": phase_row.phase_name,
        "type": phase_row.phase_type,
        "status": phase_row.status,
        "mode": phase_row.mode,
        "description": phase_row.description,
        "blocker": phase_row.blocker,
        "acquisition_job_id": phase_row.acquisition_job_id,
        "rows_imported": phase_row.rows_imported,
        "files_total": phase_row.files_total,
        "files_downloaded": phase_row.files_downloaded,
        "files_ingested": phase_row.files_ingested,
        "files_normalized": phase_row.files_normalized,
        "files_skipped": phase_row.files_skipped,
        "files_failed": phase_row.files_failed,
        "estimate": phase_row.estimate_json,
        "audit": phase_row.audit_json,
        "started_at": phase_row.started_at,
        "completed_at": phase_row.completed_at,
        "created_at": phase_row.created_at,
        "updated_at": phase_row.updated_at,
    }


def _campaign_report(session: Session, campaign: CampaignRun) -> dict[str, Any]:
    phase_rows = list(
        session.exec(
            select(CampaignPhaseRun).where(CampaignPhaseRun.campaign_id == campaign.id).order_by(CampaignPhaseRun.phase_number)
        )
    )
    counts = Counter(row.status for row in phase_rows)
    return {
        "campaign": {
            "id": campaign.id,
            "campaign_name": campaign.campaign_name,
            "config_path": campaign.config_path,
            "config_hash": campaign.config_hash,
            "provider": campaign.provider,
            "universe_name": campaign.universe_name,
            "market": campaign.market,
            "status": campaign.status,
            "live": campaign.live,
            "current_phase": campaign.current_phase,
            "config_json": campaign.config_json,
            "audit_json": campaign.audit_json,
            "warning_json": campaign.warning_json,
            "error_message": campaign.error_message,
            "started_at": campaign.started_at,
            "completed_at": campaign.completed_at,
            "created_at": campaign.created_at,
            "updated_at": campaign.updated_at,
        },
        "phases": [_campaign_phase_report(row) for row in phase_rows],
        "summary": {
            "phase_count": len(phase_rows),
            "planned_phases": counts.get("PLANNED", 0),
            "ready_phases": counts.get("READY", 0),
            "completed_phases": counts.get("COMPLETED", 0),
            "partial_phases": counts.get("PARTIAL", 0),
            "blocked_phases": counts.get("BLOCKED", 0),
            "failed_phases": counts.get("FAILED", 0),
            "skipped_phases": counts.get("SKIPPED", 0),
        },
    }


def plan_stock_campaign(session: Session, config_path: str | Path) -> dict[str, Any]:
    config = load_stock_campaign_config(config_path)
    plan = build_campaign_plan_from_config(
        config,
        live=False,
    )
    campaign = _persist_campaign_plan(
        session,
        config,
        plan,
    )
    return {
        "campaign_id": campaign.id,
        "config_path": str(Path(config_path)),
        **plan,
    }


def run_stock_campaign_phase(
    session: Session,
    config_path: str | Path,
    *,
    phase: int,
    live: bool,
    max_files: int | None = None,
    max_bytes: int | None = None,
    max_requests: int | None = None,
    min_free_bytes: int | None = None,
    force_reingest: bool = False,
) -> dict[str, Any]:
    config = load_stock_campaign_config(config_path)
    plan = build_campaign_plan_from_config(
        config,
        live=live,
        max_files=max_files,
        max_bytes=max_bytes,
        max_requests=max_requests,
        min_free_bytes=min_free_bytes,
    )
    campaign = _persist_campaign_plan(session, config, plan)
    phase_row = session.exec(
        select(CampaignPhaseRun).where(
            CampaignPhaseRun.campaign_id == campaign.id,
            CampaignPhaseRun.phase_number == phase,
        )
    ).first()
    if phase_row is None:
        raise LookupError(f"Campaign phase not found: {phase}")

    if phase_row.status == "COMPLETED" and not force_reingest:
        return {
            "campaign_id": campaign.id,
            "phase": _campaign_phase_report(phase_row),
            "campaign": _campaign_report(session, campaign)["campaign"],
        }

    previous_failed = session.exec(
        select(CampaignPhaseRun).where(
            CampaignPhaseRun.campaign_id == campaign.id,
            CampaignPhaseRun.phase_number < phase,
            CampaignPhaseRun.status.in_(["FAILED", "BLOCKED"]),
        ).order_by(CampaignPhaseRun.phase_number)
    ).first()
    if previous_failed is not None:
        phase_row.status = "BLOCKED"
        phase_row.blocker = f"Previous phase {previous_failed.phase_number} is {previous_failed.status.lower()}."
        phase_row.audit_json = sanitize_json({"blocker": phase_row.blocker})
        phase_row.updated_at = datetime.now()
        campaign.status = "BLOCKED"
        campaign.current_phase = phase
        campaign.audit_json = sanitize_json({"blocked_phase": phase, "blocker": phase_row.blocker})
        campaign.updated_at = datetime.now()
        session.add(phase_row)
        session.add(campaign)
        session.commit()
        raise ValueError(phase_row.blocker)

    result = _run_stock_campaign_phase_impl(
        session,
        campaign,
        phase_row,
        config,
        live=live,
        max_files=max_files,
        max_bytes=max_bytes,
        max_requests=max_requests,
        min_free_bytes=min_free_bytes,
        force_reingest=force_reingest,
    )
    return {
        "campaign_id": campaign.id,
        "phase": result,
        "campaign": _campaign_report(session, campaign)["campaign"],
    }


def campaign_status_report(session: Session, campaign_id: int) -> dict[str, Any]:
    campaign = session.get(CampaignRun, campaign_id)
    if campaign is None:
        raise LookupError(f"Campaign not found: {campaign_id}")
    return _campaign_report(session, campaign)


def campaign_audit_report(session: Session, campaign_id: int) -> dict[str, Any]:
    report = campaign_status_report(session, campaign_id)
    phase_rows = list(
        session.exec(
            select(CampaignPhaseRun).where(CampaignPhaseRun.campaign_id == campaign_id).order_by(CampaignPhaseRun.phase_number)
        )
    )
    report["phase_audits"] = [
        {
            "phase": row.phase_number,
            "name": row.phase_name,
            "status": row.status,
            "counts": {
                "rows_imported": row.rows_imported,
                "files_total": row.files_total,
                "files_downloaded": row.files_downloaded,
                "files_ingested": row.files_ingested,
                "files_normalized": row.files_normalized,
                "files_skipped": row.files_skipped,
                "files_failed": row.files_failed,
            },
            "estimate": row.estimate_json,
            "audit": row.audit_json,
            "blocker": row.blocker,
            "acquisition_job_id": row.acquisition_job_id,
        }
        for row in phase_rows
    ]
    return report


def build_campaign_plan_from_config(
    config: dict[str, Any],
    *,
    live: bool = False,
    max_files: int | None = None,
    max_bytes: int | None = None,
    max_requests: int | None = None,
    min_free_bytes: int | None = None,
    readiness_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    phases: list[dict[str, Any]] = []
    warnings: list[str] = []
    rest_request_total = 0

    for phase_def in config["phases"]:
        phase_number = int(phase_def["phase"])
        phase_name = phase_def["name"]
        phase_type = phase_def["type"]
        description = phase_def.get("description", "")

        if phase_type == "readiness":
            audit = readiness_audit or _readiness_phase_report()
            status = "PLANNED"
            if live:
                summary = audit.get("summary", {})
                if isinstance(summary, dict) and int(summary.get("fail", 0) or 0) > 0:
                    status = "BLOCKED"
                elif isinstance(summary, dict) and int(summary.get("warn", 0) or 0) > 0:
                    status = "WARN"
                else:
                    status = "READY"
            phases.append(
                {
                    "phase": phase_number,
                    "name": phase_name,
                    "status": status,
                    "mode": "diagnostic",
                    "description": description,
                    "audit": audit,
                    "estimate": {},
                    "blocker": None,
                }
            )
            continue

        if phase_type == "flat_files":
            start_date = phase_def.get("start_date") or config["start_date"]
            end_date = phase_def.get("end_date") or config["end_date"]
            estimate = estimate_flat_file_plan(
                provider=config["provider"],
                dataset=str(phase_def.get("dataset") or "stocks_daily"),
                market=config["market"],
                start_date=start_date,
                end_date=end_date,
                staging_dir=config.get("staging_dir"),
            )
            blocker: str | None = None
            status = "PLANNED"
            disk_audit: dict[str, Any] | None = None
            if live:
                if config["provider"].lower() != "polygon":
                    blocker = "Stock campaign flat files currently target Polygon/Massive only."
                elif not _has_massive_flat_file_credentials(settings):
                    blocker = "Massive S3 flat-file credentials are missing."
                else:
                    disk_audit = _phase_1_disk_space_check(
                        staging_dir=config.get("staging_dir") or settings.flat_file_staging_dir,
                        min_free_bytes=int(min_free_bytes or DEFAULT_MIN_FREE_BYTES),
                        settings=settings,
                    )
                    if disk_audit["blocker"]:
                        blocker = str(disk_audit["blocker"])
                if blocker is None and max_files is None:
                    blocker = "Live phase 1 requires --max-files."
                elif blocker is None and max_bytes is None:
                    blocker = "Live phase 1 requires --max-bytes."
                elif blocker is None and int(estimate["estimated_files"]) > int(max_files):
                    blocker = f"Estimated files {estimate['estimated_files']} exceed max_files {max_files}."
                elif blocker is None and int(float(estimate["estimated_download_size_mb"]) * 1024 * 1024) > int(max_bytes):
                    blocker = f"Estimated bytes exceed max_bytes {max_bytes}."
                else:
                    status = "READY"
            phases.append(
                {
                    "phase": phase_number,
                    "name": phase_name,
                    "status": "BLOCKED" if blocker else status,
                    "mode": "flat_files",
                    "description": description,
                    "estimate": estimate,
                    "audit": {"estimate": estimate, "blocker": blocker, "disk": disk_audit},
                    "blocker": blocker,
                }
            )
            if live and blocker:
                warnings.append(blocker)
            continue

        if phase_type == "rest":
            job_flags = _phase_job_flags(phase_def)
            tickers = list(phase_def.get("tickers") or request_universe_tickers(config["universe_name"]))
            estimate = _estimate_rest_phase(
                provider=config["provider"],
                tickers=tickers,
                job_flags=job_flags,
                rate_limit_per_minute=max(int(settings.polygon_rate_limit_per_minute or 3), 1),
            )
            rest_request_total += int(estimate["estimated_api_calls"])
            blocker = None
            status = "PLANNED"
            if live:
                if config["provider"].lower() != "polygon":
                    blocker = "REST campaign phases currently target Polygon only."
                elif not phase_def.get("implemented", True):
                    blocker = "This phase is scaffolded but not yet implemented."
                elif max_requests is None:
                    blocker = "Live REST phases require --max-requests."
                elif int(estimate["estimated_api_calls"]) > int(max_requests):
                    blocker = f"Estimated requests {estimate['estimated_api_calls']} exceed max_requests {max_requests}."
                else:
                    status = "READY"
            phases.append(
                {
                    "phase": phase_number,
                    "name": phase_name,
                    "status": "BLOCKED" if blocker else status,
                    "mode": "rest",
                    "description": description,
                    "estimate": estimate,
                    "audit": {"estimate": estimate, "blocker": blocker},
                    "job_flags": job_flags,
                    "blocker": blocker,
                }
            )
            if live and blocker:
                warnings.append(blocker)
            continue

        phases.append(
            {
                "phase": phase_number,
                "name": phase_name,
                "status": "PLANNED" if not live else "BLOCKED",
                "mode": phase_type,
                "description": description,
                "estimate": {},
                "audit": {"message": f"Unsupported campaign phase type: {phase_type}"},
                "blocker": f"Unsupported campaign phase type: {phase_type}",
            }
        )

    if live and max_requests is not None and rest_request_total > int(max_requests):
        warnings.append(f"Planned REST requests {rest_request_total} exceed max_requests {max_requests}.")

    summary = {
        "phase_count": len(phases),
        "plannable_phases": sum(1 for phase in phases if phase["status"] in {"PLANNED", "READY", "WARN"}),
        "blocked_phases": sum(1 for phase in phases if phase["status"] == "BLOCKED"),
        "ready_phases": sum(1 for phase in phases if phase["status"] == "READY"),
        "live": live,
    }
    return {
        "campaign": {
            "campaign_name": config["campaign_name"],
            "provider": config["provider"],
            "universe_name": config["universe_name"],
            "market": config["market"],
            "live": live,
            "force_reingest": False,
            "start_date": config["start_date"].isoformat(),
            "end_date": config["end_date"].isoformat(),
            "max_flat_files": max_files,
            "max_rest_requests": max_requests,
            "max_total_requests": max_requests,
        },
        "phases": phases,
        "warnings": warnings,
        "summary": summary,
    }


def _run_stock_campaign_phase_impl(
    session: Session,
    campaign: CampaignRun,
    phase_row: CampaignPhaseRun,
    config: dict[str, Any],
    *,
    live: bool,
    max_files: int | None,
    max_bytes: int | None,
    max_requests: int | None,
    min_free_bytes: int | None,
    force_reingest: bool,
) -> dict[str, Any]:
    phase_def = next((item for item in config["phases"] if int(item["phase"]) == phase_row.phase_number), None)
    if phase_def is None:
        raise LookupError(f"Campaign phase not found: {phase_row.phase_number}")

    if phase_row.phase_number == 0:
        audit = _readiness_phase_report()
        phase_row.status = "COMPLETED" if not live or int(audit.get("summary", {}).get("fail", 0) or 0) == 0 else "BLOCKED"
        phase_row.audit_json = sanitize_json(audit)
        phase_row.started_at = phase_row.started_at or datetime.now()
        phase_row.completed_at = datetime.now()
        phase_row.updated_at = datetime.now()
        campaign.current_phase = 0
        campaign.status = _campaign_status_from_phase_rows(session, campaign.id or 0)
        campaign.audit_json = sanitize_json({"latest_phase": 0, "summary": audit.get("summary", {})})
        campaign.started_at = campaign.started_at or datetime.now()
        campaign.updated_at = datetime.now()
        session.add(phase_row)
        session.add(campaign)
        session.commit()
        return _campaign_phase_report(phase_row)

    if phase_row.phase_type == "flat_files":
        settings = get_settings()
        start_date = phase_def.get("start_date") or config["start_date"]
        end_date = phase_def.get("end_date") or config["end_date"]
        estimate = estimate_flat_file_plan(
            provider=config["provider"],
            dataset=str(phase_def.get("dataset") or "stocks_daily"),
            market=config["market"],
            start_date=start_date,
            end_date=end_date,
            staging_dir=config.get("staging_dir"),
        )
        phase_row.estimate_json = estimate
        if not live:
            phase_row.status = "PLANNED"
            phase_row.audit_json = sanitize_json({"estimate": estimate, "message": "Dry run only; no network calls were made."})
            phase_row.updated_at = datetime.now()
            campaign.current_phase = phase_row.phase_number
            campaign.status = _campaign_status_from_phase_rows(session, campaign.id or 0)
            campaign.audit_json = sanitize_json({"latest_phase": phase_row.phase_number, "summary": estimate})
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            return _campaign_phase_report(phase_row)

        if not _has_massive_flat_file_credentials(settings):
            blocker = "Massive S3 flat-file credentials are missing."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)
        if max_files is None:
            blocker = "Live phase 1 requires --max-files."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)
        if max_bytes is None:
            blocker = "Live phase 1 requires --max-bytes."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)
        if int(estimate["estimated_files"]) > int(max_files):
            blocker = f"Estimated files {estimate['estimated_files']} exceed max_files {max_files}."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)
        if int(float(estimate["estimated_download_size_mb"]) * 1024 * 1024) > int(max_bytes):
            blocker = f"Estimated bytes exceed max_bytes {max_bytes}."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)

        disk_audit = _phase_1_disk_space_check(
            staging_dir=config.get("staging_dir") or settings.flat_file_staging_dir,
            min_free_bytes=int(min_free_bytes or DEFAULT_MIN_FREE_BYTES),
            settings=settings,
        )
        if disk_audit["blocker"]:
            blocker = str(disk_audit["blocker"])
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "disk": disk_audit, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker, "disk": disk_audit})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)

        provider = PolygonFlatFileProvider(
            access_key_id=settings.polygon_flat_file_access_key_id,
            secret_access_key=settings.polygon_flat_file_secret_access_key,
            endpoint_url=settings.polygon_flat_file_endpoint,
            bucket_name=settings.polygon_flat_file_bucket,
            region=settings.polygon_flat_file_region,
        )
        service = FlatFileImportService(session, provider, Path(config.get("staging_dir") or settings.flat_file_staging_dir))
        result = service.run(
            str(phase_def.get("dataset") or "stocks_daily"),
            start_date=start_date,
            end_date=end_date,
            market=config["market"],
            force=force_reingest,
        )
        phase_row.audit_json = sanitize_json(result)
        phase_row.rows_imported = sum(int(item.get("rows_imported", 0)) for item in result.get("manifests", []))
        phase_row.files_total = int(result.get("files_total", 0))
        phase_row.files_downloaded = int(result.get("files_downloaded", 0))
        phase_row.files_ingested = int(result.get("files_ingested", 0))
        phase_row.files_normalized = int(result.get("files_normalized", 0))
        phase_row.files_skipped = int(result.get("files_skipped", 0))
        phase_row.files_failed = int(result.get("files_failed", 0))
        phase_row.status = "FAILED" if phase_row.files_failed and not phase_row.files_normalized else ("PARTIAL" if phase_row.files_failed else "COMPLETED")
        phase_row.started_at = phase_row.started_at or datetime.now()
        phase_row.completed_at = datetime.now()
        phase_row.updated_at = datetime.now()
        campaign.current_phase = phase_row.phase_number
        campaign.status = _campaign_status_from_phase_rows(session, campaign.id or 0)
        campaign.started_at = campaign.started_at or datetime.now()
        campaign.completed_at = None if campaign.status in {"PLANNED", "RUNNING", "BLOCKED", "FAILED"} else datetime.now()
        campaign.audit_json = sanitize_json({"latest_phase": phase_row.phase_number, "summary": result})
        campaign.updated_at = datetime.now()
        session.add(phase_row)
        session.add(campaign)
        session.commit()
        return _campaign_phase_report(phase_row)

    if phase_row.phase_type == "rest":
        job_flags = _phase_job_flags(phase_def)
        tickers = list(phase_def.get("tickers") or request_universe_tickers(config["universe_name"]))
        estimate = _estimate_rest_phase(
            provider=config["provider"],
            tickers=tickers,
            job_flags=job_flags,
            rate_limit_per_minute=max(int(get_settings().polygon_rate_limit_per_minute or 3), 1),
        )
        phase_row.estimate_json = estimate
        if not live:
            phase_row.status = "PLANNED"
            phase_row.audit_json = sanitize_json({"estimate": estimate, "message": "Dry run only; no network calls were made."})
            phase_row.updated_at = datetime.now()
            campaign.current_phase = phase_row.phase_number
            campaign.status = _campaign_status_from_phase_rows(session, campaign.id or 0)
            campaign.audit_json = sanitize_json({"latest_phase": phase_row.phase_number, "summary": estimate})
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            return _campaign_phase_report(phase_row)
        if not phase_def.get("implemented", True):
            blocker = "This phase is scaffolded but not yet implemented."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)
        if max_requests is None:
            blocker = "Live REST phases require --max-requests."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)
        if int(estimate["estimated_api_calls"]) > int(max_requests):
            blocker = f"Estimated requests {estimate['estimated_api_calls']} exceed max_requests {max_requests}."
            phase_row.status = "BLOCKED"
            phase_row.blocker = blocker
            phase_row.audit_json = sanitize_json({"estimate": estimate, "blocker": blocker})
            phase_row.updated_at = datetime.now()
            campaign.status = "BLOCKED"
            campaign.current_phase = phase_row.phase_number
            campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
            campaign.updated_at = datetime.now()
            session.add(phase_row)
            session.add(campaign)
            session.commit()
            raise ValueError(blocker)

        job_request = AcquisitionJobCreateRequest(
            job_name=f"{campaign.campaign_name}-phase-{phase_row.phase_number}-{campaign.id}",
            provider=config["provider"],
            universe_name=config["universe_name"],
            years=max(_campaign_years(config["start_date"], config["end_date"]), 1),
            include_prices=job_flags["include_prices"],
            include_metadata=job_flags["include_metadata"],
            include_fundamentals=job_flags["include_fundamentals"],
            include_dividends=job_flags["include_dividends"],
            include_splits=job_flags["include_splits"],
            include_options=job_flags["include_options"],
            rate_limit_per_minute=int(get_settings().polygon_rate_limit_per_minute or 3),
            start_date=config["start_date"],
            end_date=config["end_date"],
            config_json=sanitize_json({"tickers": tickers}),
        )
        if phase_row.acquisition_job_id is None:
            job_report = create_acquisition_job(session, job_request)
            phase_row.acquisition_job_id = int(job_report["job"]["id"])
        else:
            job_report = {"job": {"id": phase_row.acquisition_job_id}}
        run_report = run_acquisition_job(
            session,
            int(phase_row.acquisition_job_id or job_report["job"]["id"]),
            live=True,
            max_requests=max_requests,
            start_date=config["start_date"],
            end_date=config["end_date"],
        )
        phase_row.audit_json = sanitize_json({"created_job": job_report, "run_report": run_report})
        phase_row.rows_imported = sum(int(task.get("rows_imported", 0)) for task in run_report.get("tasks", []))
        task_counts = run_report.get("task_counts", {})
        phase_row.files_total = int(run_report.get("task_total", 0))
        phase_row.files_downloaded = int(task_counts.get("COMPLETED", 0))
        phase_row.files_ingested = int(task_counts.get("COMPLETED", 0))
        phase_row.files_normalized = int(task_counts.get("COMPLETED", 0))
        phase_row.files_skipped = int(task_counts.get("SKIPPED", 0))
        phase_row.files_failed = int(task_counts.get("FAILED", 0))
        phase_row.status = str(run_report["job"].get("status") or "COMPLETED")
        phase_row.started_at = phase_row.started_at or datetime.now()
        phase_row.completed_at = datetime.now()
        phase_row.updated_at = datetime.now()
        campaign.current_phase = phase_row.phase_number
        campaign.status = _campaign_status_from_phase_rows(session, campaign.id or 0)
        campaign.started_at = campaign.started_at or datetime.now()
        campaign.completed_at = None if campaign.status in {"PLANNED", "RUNNING", "BLOCKED", "FAILED"} else datetime.now()
        campaign.audit_json = sanitize_json({"latest_phase": phase_row.phase_number, "summary": run_report})
        campaign.updated_at = datetime.now()
        session.add(phase_row)
        session.add(campaign)
        session.commit()
        return _campaign_phase_report(phase_row)

    blocker = "Earnings / ratios phase is scaffolded but not implemented."
    phase_row.status = "BLOCKED"
    phase_row.blocker = blocker
    phase_row.audit_json = sanitize_json({"message": blocker})
    phase_row.updated_at = datetime.now()
    campaign.status = "BLOCKED"
    campaign.current_phase = phase_row.phase_number
    campaign.audit_json = sanitize_json({"blocked_phase": phase_row.phase_number, "blocker": blocker})
    campaign.updated_at = datetime.now()
    session.add(phase_row)
    session.add(campaign)
    session.commit()
    raise ValueError(blocker)


def _campaign_status_from_phase_rows(session: Session, campaign_id: int) -> str:
    phase_rows = list(
        session.exec(select(CampaignPhaseRun).where(CampaignPhaseRun.campaign_id == campaign_id))
    )
    if not phase_rows:
        return "PLANNED"
    statuses = [row.status for row in phase_rows]
    if "FAILED" in statuses:
        return "FAILED"
    if "BLOCKED" in statuses:
        return "PARTIAL" if any(status in {"COMPLETED", "PARTIAL"} for status in statuses) else "BLOCKED"
    if any(status in {"PLANNED", "READY", "WARN", "RUNNING"} for status in statuses):
        return "RUNNING" if any(status in {"COMPLETED", "PARTIAL", "SKIPPED"} for status in statuses) else "PLANNED"
    if any(status in {"COMPLETED", "PARTIAL", "SKIPPED"} for status in statuses):
        return "COMPLETED"
    return "PLANNED"
