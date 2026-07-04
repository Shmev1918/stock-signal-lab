from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import socket
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel, Session

import app.acquisition.jobs as acquisition_jobs
from app.acquisition import checkpoints as acquisition_checkpoints
from app.acquisition.flat_files import estimate_flat_file_plan
from app.acquisition.flat_files import FlatFileImportService
from app.acquisition import raw_payloads as acquisition_raw_payloads
from app.acquisition.reports import inspect_flat_file_manifest, list_flat_file_manifests
from app.db.session import engine, init_db
from app.acquisition.estimates import estimate_acquisition
from app.acquisition.campaign import (
    StockCampaignRequest,
    campaign_audit_report,
    campaign_status_report,
    plan_stock_campaign,
    run_stock_campaign_phase,
    run_stock_only_campaign,
)
from app.acquisition.jobs import (
    AcquisitionJobCreateRequest,
    create_acquisition_job,
    get_acquisition_job,
    pause_acquisition_job,
    retry_failed_tasks,
    resume_acquisition_job,
    run_acquisition_job,
)
from app.config import get_settings
from app.experiments.runner import ExperimentRequest, get_experiment_summary, list_experiments, run_experiment
from app.services.health_service import get_health_details
from app.services.diagnostics_service import get_distribution_diagnostics
from app.services.signal_diagnostics_service import get_signal_diagnostics
from app.services.analysis_service import build_strategy_rankings
from app.services.decision_service import get_decision_evaluation
from app.services.score_evaluation_service import get_score_evaluation
from app.services.watchlist_service import refresh_watchlist_workflow, watchlist_status_payload
from app.providers.polygon_provider import PolygonMarketDataProvider


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=_json_default, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-signal-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    refresh = subparsers.add_parser("refresh-watchlist", help="Refresh watchlist data, signals, and scores.")
    refresh.add_argument("--strategies", default="balanced,conservative_quality,value_recovery")
    refresh.add_argument("--force-reingest", action="store_true")
    refresh.add_argument("--provider", default=None)

    rankings = subparsers.add_parser("rankings", help="Print strategy rankings for the watchlist.")
    rankings.add_argument("--strategy", default="balanced")
    rankings.add_argument("--limit", type=int, default=25)
    rankings.add_argument("--include-signals", action="store_true")

    evaluate_scores = subparsers.add_parser("evaluate-scores", help="Evaluate stored scores over a horizon.")
    evaluate_scores.add_argument("--horizon", type=int, default=90)
    evaluate_scores.add_argument("--strategy-name", default=None)

    evaluate_decisions = subparsers.add_parser("evaluate-decisions", help="Evaluate human decisions over a horizon.")
    evaluate_decisions.add_argument("--horizon", type=int, default=90)
    evaluate_decisions.add_argument("--strategy-name", default=None)

    run_experiment_cmd = subparsers.add_parser("run-experiment", help="Run an experiment against stored scores and prices.")
    run_experiment_cmd.add_argument("--name", required=True)
    run_experiment_cmd.add_argument(
        "--experiment-type",
        required=True,
        choices=["strategy_score_threshold", "recommendation_outcome", "risk_category_outcome", "signal_threshold"],
    )
    run_experiment_cmd.add_argument("--strategy-name", default=None)
    run_experiment_cmd.add_argument("--horizon-days", type=int, default=90)
    run_experiment_cmd.add_argument("--benchmark-ticker", default="SPY")
    run_experiment_cmd.add_argument("--start-date", required=True)
    run_experiment_cmd.add_argument("--end-date", required=True)
    run_experiment_cmd.add_argument("--description", default=None)
    run_experiment_cmd.add_argument("--filters-json", default="{}")

    list_experiments_cmd = subparsers.add_parser("list-experiments", help="List stored experiments.")
    list_experiments_cmd.add_argument("--limit", type=int, default=None)

    experiment_summary_cmd = subparsers.add_parser("experiment-summary", help="Show a summary for one experiment.")
    experiment_summary_cmd.add_argument("--id", type=int, required=True)

    diagnostics = subparsers.add_parser("diagnostics-distributions", help="Show score and signal distributions.")
    diagnostics.add_argument("--strategy-name", default=None)
    diagnostics.add_argument("--signal-name", default=None)
    diagnostics.add_argument("--signal-category", default=None)

    signal_diagnostics = subparsers.add_parser("diagnostics-signals", help="Trace signal inputs and fallbacks for one ticker.")
    signal_diagnostics.add_argument("--ticker", required=True)
    signal_diagnostics.add_argument("--as-of-date", default=None)

    acquisition = subparsers.add_parser("acquisition", help="Manage acquisition jobs.")
    acquisition_subparsers = acquisition.add_subparsers(dest="acquisition_command", required=True)

    create_job = acquisition_subparsers.add_parser("create-job", help="Create an acquisition job.")
    create_job.add_argument("--job-name", required=True)
    create_job.add_argument("--provider", default="polygon")
    create_job.add_argument("--universe-name", default="STOCK_RESEARCH_CORE")
    create_job.add_argument("--years", type=int, default=None)
    create_job.add_argument("--include-prices", action=argparse.BooleanOptionalAction, default=True)
    create_job.add_argument("--include-metadata", action=argparse.BooleanOptionalAction, default=False)
    create_job.add_argument("--include-fundamentals", action=argparse.BooleanOptionalAction, default=True)
    create_job.add_argument("--include-dividends", action=argparse.BooleanOptionalAction, default=True)
    create_job.add_argument("--include-splits", action=argparse.BooleanOptionalAction, default=True)
    create_job.add_argument("--include-options", action=argparse.BooleanOptionalAction, default=False)
    create_job.add_argument("--rate-limit-per-minute", type=int, default=None)
    create_job.add_argument("--start-date", default=None)
    create_job.add_argument("--end-date", default=None)
    create_job.add_argument("--config-json", default="{}")

    run_job = acquisition_subparsers.add_parser("run-job", help="Run an acquisition job.")
    run_job.add_argument("job_id", type=int)
    run_job.add_argument("--force", action="store_true")
    run_job.add_argument("--live", action="store_true")
    run_job.add_argument("--max-requests", type=int, default=None)
    run_job.add_argument("--start-date", default=None)
    run_job.add_argument("--end-date", default=None)

    status_job = acquisition_subparsers.add_parser("status", help="Show acquisition job status.")
    status_job.add_argument("job_id", type=int)

    retry_failed = acquisition_subparsers.add_parser("retry-failed", help="Retry failed acquisition tasks.")
    retry_failed.add_argument("job_id", type=int)

    pause_job = acquisition_subparsers.add_parser("pause", help="Pause an acquisition job.")
    pause_job.add_argument("job_id", type=int)

    resume_job = acquisition_subparsers.add_parser("resume", help="Resume an acquisition job.")
    resume_job.add_argument("job_id", type=int)

    estimate_job = acquisition_subparsers.add_parser("estimate", help="Estimate an acquisition campaign.")
    estimate_job.add_argument("--provider", default="polygon")
    estimate_job.add_argument("--universe-name", default="STOCK_RESEARCH_CORE")
    estimate_job.add_argument("--years", type=int, default=2)
    estimate_job.add_argument("--include-prices", action=argparse.BooleanOptionalAction, default=True)
    estimate_job.add_argument("--include-fundamentals", action=argparse.BooleanOptionalAction, default=True)
    estimate_job.add_argument("--include-options", action=argparse.BooleanOptionalAction, default=False)
    estimate_job.add_argument("--rate-limit-per-minute", type=int, default=3)
    estimate_job.add_argument("--config-json", default="{}")

    plan_job = acquisition_subparsers.add_parser("plan", help="Estimate a flat-file acquisition campaign.")
    plan_job.add_argument("--provider", default="polygon")
    plan_job.add_argument("--dataset", required=True)
    plan_job.add_argument("--market", default="US")
    plan_job.add_argument("--start-date", required=True)
    plan_job.add_argument("--end-date", required=True)
    plan_job.add_argument("--staging-dir", default=None)

    campaign_job = acquisition_subparsers.add_parser("campaign", help="Run the resumable stock-historical campaign.")
    campaign_subparsers = campaign_job.add_subparsers(dest="campaign_command", required=True)

    campaign_plan = campaign_subparsers.add_parser("plan", help="Load a campaign YAML file and print the phase plan.")
    campaign_plan.add_argument("--config", required=True)

    campaign_run = campaign_subparsers.add_parser("run", help="Run one phase of a stock-historical campaign.")
    campaign_run.add_argument("--config", required=True)
    campaign_run.add_argument("--phase", type=int, required=True)
    campaign_run.add_argument("--live", action="store_true")
    campaign_run.add_argument("--force-reingest", action="store_true")
    campaign_run.add_argument("--max-files", type=int, default=None)
    campaign_run.add_argument("--max-flat-files", type=int, default=None)
    campaign_run.add_argument("--max-bytes", type=int, default=None)
    campaign_run.add_argument("--max-requests", type=int, default=None)
    campaign_run.add_argument("--min-free-bytes", type=int, default=int(1.5 * 1024**4))

    campaign_status = campaign_subparsers.add_parser("status", help="Show persisted campaign status.")
    campaign_status.add_argument("--campaign-id", type=int, required=True)

    campaign_audit = campaign_subparsers.add_parser("audit", help="Show persisted campaign audit details.")
    campaign_audit.add_argument("--campaign-id", type=int, required=True)

    import_flat = acquisition_subparsers.add_parser("import-flat-file", help="Import one flat file into landing/canonical tables.")
    import_flat.add_argument("--provider", default="sample")
    import_flat.add_argument("--dataset", required=True)
    import_flat.add_argument("--market", default="US")
    import_flat.add_argument("--path", required=True)
    import_flat.add_argument("--expected-checksum", default=None)
    import_flat.add_argument("--force", action="store_true")
    import_flat.add_argument("--staging-dir", default=None)

    list_flat_files = acquisition_subparsers.add_parser("list-flat-files", help="List imported flat-file manifests.")
    list_flat_files.add_argument("--provider", default=None)
    list_flat_files.add_argument("--dataset", default=None)
    list_flat_files.add_argument("--market", default=None)

    inspect_flat_file = acquisition_subparsers.add_parser("inspect-flat-file", help="Inspect one imported flat-file manifest.")
    inspect_flat_file.add_argument("--manifest-id", type=int, required=True)

    acquisition_subparsers.add_parser(
        "readiness-report",
        help="Show acquisition readiness checks without calling Polygon.",
    ).add_argument("--json", action="store_true", help="Emit JSON for automation instead of a table.")
    acquisition_subparsers.choices["readiness-report"].add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if any readiness check is WARN or FAIL.",
    )

    subparsers.add_parser("health", help="Show database and model health details.")
    subparsers.add_parser("status", help="Show watchlist status and data sources.")
    polygon = subparsers.add_parser("polygon", help="Polygon helper commands.")
    polygon_subparsers = polygon.add_subparsers(dest="polygon_command", required=True)
    polygon_smoke = polygon_subparsers.add_parser("smoke-test", help="Smoke test Polygon endpoints without a large import.")
    polygon_smoke.add_argument("--ticker", default="AAPL")

    deprecated_polygon_smoke = subparsers.add_parser(
        "polygon-smoke-test",
        help="Smoke test Polygon endpoints without a large import. Deprecated alias for 'polygon smoke-test'.",
    )
    deprecated_polygon_smoke.add_argument("--ticker", default="AAPL")
    return parser


def _run_refresh_watchlist(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return refresh_watchlist_workflow(
        session,
        strategies=args.strategies,
        force_reingest=args.force_reingest,
        provider_name=args.provider,
    )


def _run_rankings(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return {
        "rankings": build_strategy_rankings(
            session,
            strategy_names=[args.strategy] if args.strategy else None,
            limit=args.limit,
            include_signals=args.include_signals,
        )
    }


def _run_evaluate_scores(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return get_score_evaluation(
        session,
        horizon_days=args.horizon,
        strategy_name=args.strategy_name,
    )


def _run_evaluate_decisions(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return get_decision_evaluation(
        session,
        horizon_days=args.horizon,
        strategy_name=args.strategy_name,
    )


def _run_status(session: Session, _: argparse.Namespace) -> list[dict[str, object]]:
    return watchlist_status_payload(session)


def _run_health(session: Session, _: argparse.Namespace) -> dict[str, object]:
    return get_health_details(session)


def _run_experiment(session: Session, args: argparse.Namespace) -> dict[str, object]:
    filters = json.loads(args.filters_json or "{}")
    request = ExperimentRequest(
        name=args.name,
        description=args.description,
        experiment_type=args.experiment_type,
        strategy_name=args.strategy_name,
        horizon_days=args.horizon_days,
        benchmark_ticker=args.benchmark_ticker,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        filters=filters,
    )
    return run_experiment(session, request)


def _run_list_experiments(session: Session, args: argparse.Namespace) -> list[dict[str, object]]:
    experiments = list_experiments(session)
    if args.limit is not None:
        return experiments[: args.limit]
    return experiments


def _run_experiment_summary(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return get_experiment_summary(session, args.id)


def _run_diagnostics_distributions(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return get_distribution_diagnostics(
        session,
        strategy_name=args.strategy_name,
        signal_name=args.signal_name,
        signal_category=args.signal_category,
    )


def _run_diagnostics_signals(session: Session, args: argparse.Namespace) -> dict[str, object]:
    as_of_date = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    return get_signal_diagnostics(session, args.ticker, as_of_date=as_of_date)


def _run_polygon_smoke_test(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    provider = PolygonMarketDataProvider(
        api_key=settings.polygon_api_key,
        mode=settings.polygon_mode,
        rate_limit_per_minute=settings.polygon_rate_limit_per_minute,
    )
    checks = provider.smoke_checks(args.ticker)
    return {
        "provider": "polygon",
        "api_key_detected": bool(settings.polygon_api_key),
        "mode": settings.polygon_mode,
        "checks": [
            {
                "name": check.name,
                "endpoint": check.endpoint,
                "ticker": check.ticker,
                "status": getattr(check, "status", "PASS" if getattr(check, "success", False) else "FAIL"),
                "success": getattr(check, "success", getattr(check, "status", "FAIL") == "PASS"),
                "status_code": getattr(check, "status_code", None),
                "error": getattr(check, "error", None),
                "cause": getattr(check, "cause", "UNKNOWN"),
                "rate_limited": getattr(check, "rate_limited", False),
            }
            for check in checks
        ],
    }


def _run_acquisition_create_job(session: Session, args: argparse.Namespace) -> dict[str, object]:
    config_json = json.loads(args.config_json or "{}")
    request = AcquisitionJobCreateRequest(
        job_name=args.job_name,
        provider=args.provider,
        universe_name=args.universe_name,
        years=args.years if args.years is not None else get_settings().polygon_historical_years,
        include_prices=args.include_prices,
        include_metadata=args.include_metadata,
        include_fundamentals=args.include_fundamentals,
        include_dividends=args.include_dividends,
        include_splits=args.include_splits,
        include_options=args.include_options,
        rate_limit_per_minute=(
            args.rate_limit_per_minute
            if args.rate_limit_per_minute is not None
            else get_settings().polygon_rate_limit_per_minute
        ),
        start_date=date.fromisoformat(args.start_date) if args.start_date else None,
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
        config_json=config_json,
    )
    return create_acquisition_job(session, request)


def _run_acquisition_job(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return run_acquisition_job(
        session,
        args.job_id,
        force=args.force,
        live=args.live,
        max_requests=args.max_requests,
        start_date=date.fromisoformat(args.start_date) if args.start_date else None,
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
    )


def _run_acquisition_status(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return get_acquisition_job(session, args.job_id)


def _run_acquisition_pause(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return pause_acquisition_job(session, args.job_id)


def _run_acquisition_resume(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return resume_acquisition_job(session, args.job_id)


def _run_acquisition_retry_failed(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return retry_failed_tasks(session, args.job_id)


def _run_acquisition_estimate(args: argparse.Namespace) -> dict[str, object]:
    return estimate_acquisition(
        provider=args.provider,
        universe_name=args.universe_name,
        years=args.years,
        include_prices=args.include_prices,
        include_fundamentals=args.include_fundamentals,
        include_options=args.include_options,
        rate_limit_per_minute=args.rate_limit_per_minute,
        config_json=json.loads(args.config_json or "{}"),
    )


def _run_acquisition_plan(args: argparse.Namespace) -> dict[str, object]:
    return estimate_flat_file_plan(
        provider=args.provider,
        dataset=args.dataset,
        market=args.market,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        staging_dir=args.staging_dir,
    )


def _run_acquisition_campaign(session: Session, args: argparse.Namespace) -> dict[str, object]:
    if getattr(args, "campaign_command", None) == "plan":
        return _run_acquisition_campaign_plan(session, args)
    if getattr(args, "campaign_command", None) == "run":
        return _run_acquisition_campaign_run(session, args)
    if getattr(args, "campaign_command", None) == "status":
        return _run_acquisition_campaign_status(session, args)
    if getattr(args, "campaign_command", None) == "audit":
        return _run_acquisition_campaign_audit(session, args)

    if args.live and args.max_flat_files is None:
        raise ValueError("Live stock campaign requires --max-flat-files")
    if args.live and args.max_rest_requests is None:
        raise ValueError("Live stock campaign requires --max-rest-requests")
    request = StockCampaignRequest(
        provider=args.provider,
        universe_name=args.universe_name,
        market=args.market,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        live=args.live,
        force_reingest=args.force_reingest,
        staging_dir=args.staging_dir,
        max_flat_files=args.max_flat_files,
        max_rest_requests=args.max_rest_requests,
        max_total_requests=args.max_total_requests,
    )
    return run_stock_only_campaign(session, request)


def _run_acquisition_campaign_plan(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return plan_stock_campaign(session, args.config)


def _run_acquisition_campaign_run(session: Session, args: argparse.Namespace) -> dict[str, object]:
    max_files = args.max_files if args.max_files is not None else args.max_flat_files
    if args.live and args.phase == 1 and max_files is None:
        raise ValueError("Live phase 1 requires --max-files")
    if args.live and args.phase == 1 and args.max_bytes is None:
        raise ValueError("Live phase 1 requires --max-bytes")
    if args.live and args.phase in {2, 3, 4} and args.max_requests is None:
        raise ValueError("Live REST phases require --max-requests")
    return run_stock_campaign_phase(
        session,
        args.config,
        phase=args.phase,
        live=args.live,
        max_files=max_files,
        max_bytes=args.max_bytes,
        max_requests=args.max_requests,
        min_free_bytes=args.min_free_bytes,
        force_reingest=args.force_reingest,
    )


def _run_acquisition_campaign_status(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return campaign_status_report(session, args.campaign_id)


def _run_acquisition_campaign_audit(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return campaign_audit_report(session, args.campaign_id)


def _run_acquisition_import_flat_file(session: Session, args: argparse.Namespace) -> dict[str, object]:
    from app.providers.flat_file_provider import LocalFlatFileProvider

    settings = get_settings()
    staging_dir = args.staging_dir or settings.flat_file_staging_dir
    service = FlatFileImportService(session, LocalFlatFileProvider(Path(args.path).parent), staging_dir)
    return service.import_stock_daily_file(
        args.path,
        provider=args.provider,
        dataset=args.dataset,
        market=args.market,
        expected_checksum=args.expected_checksum,
        force=args.force,
    )


def _run_acquisition_list_flat_files(session: Session, args: argparse.Namespace) -> list[dict[str, object]]:
    return list_flat_file_manifests(session, provider=args.provider, dataset=args.dataset, market=args.market)


def _run_acquisition_inspect_flat_file(session: Session, args: argparse.Namespace) -> dict[str, object]:
    return inspect_flat_file_manifest(session, args.manifest_id)


def _readiness_check(check: str, status: str, detail: str) -> dict[str, str]:
    return {"check": check, "status": status, "detail": detail}


def _redact_database_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def _database_connection_diagnostics(database_url: str) -> dict[str, object]:
    parsed = make_url(database_url)
    backend = parsed.get_backend_name()
    hostname = parsed.host
    port = parsed.port
    resolved = False
    tcp_connected = False
    sql_connected = False
    hostname_error: str | None = None
    tcp_error: str | None = None
    sql_error: str | None = None

    if hostname:
        try:
            socket.getaddrinfo(hostname, port or 5432, type=socket.SOCK_STREAM)
            resolved = True
        except socket.gaierror as exc:
            hostname_error = str(exc)
    else:
        hostname_error = "No hostname configured in database URL."

    if hostname and resolved:
        try:
            with socket.create_connection((hostname, int(port or 5432)), timeout=3):
                tcp_connected = True
        except OSError as exc:
            tcp_error = str(exc)

    try:
        engine_kwargs: dict[str, object] = {"pool_pre_ping": False, "poolclass": None}
        if backend != "sqlite":
            engine_kwargs["connect_args"] = {"connect_timeout": 3}
        sql_engine = create_engine(database_url, **engine_kwargs)
        with sql_engine.connect() as connection:
            connection.execute(text("SELECT 1")).first()
        sql_connected = True
    except Exception as exc:  # pragma: no cover - database availability depends on environment
        sql_error = str(exc)

    return {
        "configured_database_url": _redact_database_url(database_url),
        "hostname": hostname,
        "port": port,
        "hostname_resolves": resolved,
        "hostname_error": hostname_error,
        "tcp_connection_succeeds": tcp_connected,
        "tcp_error": tcp_error,
        "sql_connection_succeeds": sql_connected,
        "sql_error": sql_error,
    }


def _alembic_readiness_detail(connection) -> dict[str, object]:
    settings = get_settings()
    head_revisions: list[str] = []
    current_revisions: list[str] = []
    migration_context = MigrationContext.configure(connection)
    current_revisions = list(migration_context.get_current_heads())
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    from alembic.script import ScriptDirectory

    head_revisions = list(ScriptDirectory.from_config(alembic_cfg).get_heads())
    return {
        "current": current_revisions,
        "head": head_revisions,
    }


def _run_acquisition_readiness_report(_: Session | None, __: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    database = _database_connection_diagnostics(settings.database_url)
    checks: list[dict[str, str]] = []

    checks.append(
        _readiness_check(
            "database hostname resolves",
            "PASS" if database["hostname_resolves"] else "FAIL",
            "Hostname resolved successfully." if database["hostname_resolves"] else str(database.get("hostname_error") or "Hostname did not resolve."),
        )
    )
    checks.append(
        _readiness_check(
            "database TCP connection succeeds",
            "PASS" if database["tcp_connection_succeeds"] else "FAIL",
            "TCP connection succeeded." if database["tcp_connection_succeeds"] else str(database.get("tcp_error") or "TCP connection failed."),
        )
    )
    checks.append(
        _readiness_check(
            "database SQL connection succeeds",
            "PASS" if database["sql_connection_succeeds"] else "FAIL",
            "SQL connection succeeded." if database["sql_connection_succeeds"] else str(database.get("sql_error") or "SQL connection failed."),
        )
    )

    sql_connected = bool(database["sql_connection_succeeds"])
    try:
        if sql_connected:
            parsed = make_url(settings.database_url)
            engine_kwargs: dict[str, object] = {"pool_pre_ping": False, "poolclass": None}
            if parsed.get_backend_name() != "sqlite":
                engine_kwargs["connect_args"] = {"connect_timeout": 3}
            sql_engine = create_engine(settings.database_url, **engine_kwargs)
            with sql_engine.connect() as connection:
                alembic_status = _alembic_readiness_detail(connection)
                current = alembic_status["current"]
                head = alembic_status["head"]
                if not head:
                    checks.append(_readiness_check("alembic current/head status", "FAIL", "No Alembic heads were discovered."))
                elif not current:
                    checks.append(
                        _readiness_check(
                            "alembic current/head status",
                            "FAIL",
                            f"Database revision is empty; repository head is {', '.join(head)}.",
                        )
                    )
                elif set(current) == set(head):
                    checks.append(
                        _readiness_check(
                            "alembic current/head status",
                            "PASS",
                            f"Current revision(s) {', '.join(current)} match head(s) {', '.join(head)}.",
                        )
                    )
                elif set(current).issubset(set(head)):
                    checks.append(
                        _readiness_check(
                            "alembic current/head status",
                            "WARN",
                            f"Database revision(s) {', '.join(current)} are behind head(s) {', '.join(head)}.",
                        )
                    )
                else:
                    checks.append(
                        _readiness_check(
                            "alembic current/head status",
                            "FAIL",
                            f"Current revision(s) {', '.join(current)} diverge from head(s) {', '.join(head)}.",
                        )
                    )
        else:
            checks.append(
                _readiness_check(
                    "alembic current/head status",
                    "FAIL",
                    "SQL connection did not succeed, so Alembic current/head status could not be checked.",
                )
            )
    except Exception as exc:  # pragma: no cover - defensive report path
        checks.append(_readiness_check("alembic current/head status", "FAIL", f"Unable to inspect Alembic state: {exc!s}"))

    try:
        raw_payloads_enabled = all(hasattr(acquisition_raw_payloads, attr) for attr in ("store_raw_payload", "mark_payload_normalized"))
        if raw_payloads_enabled:
            checks.append(
                _readiness_check(
                    "raw payload storage enabled",
                    "PASS",
                    "Raw payload landing helpers are present in app/acquisition/raw_payloads.py.",
                )
            )
        else:
            checks.append(_readiness_check("raw payload storage enabled", "FAIL", "Raw payload helpers are missing."))
    except Exception as exc:  # pragma: no cover - defensive report path
        checks.append(_readiness_check("raw payload storage enabled", "FAIL", f"Unable to inspect raw payload storage: {exc!s}"))

    try:
        provider_calls_table = "provider_api_calls" in SQLModel.metadata.tables
        checks.append(
            _readiness_check(
                "provider call logging table exists",
                "PASS" if provider_calls_table else "FAIL",
                "provider_api_calls table is present." if provider_calls_table else "provider_api_calls table is missing.",
            )
        )
    except Exception as exc:  # pragma: no cover - defensive report path
        checks.append(
            _readiness_check(
                "provider call logging table exists",
                "FAIL",
                f"Unable to inspect provider_api_calls table: {exc!s}",
            )
        )

    try:
        checkpoint_table = "acquisition_tasks" in SQLModel.metadata.tables
        checkpoint_helpers = all(
            hasattr(acquisition_checkpoints, attr)
            for attr in ("task_is_runnable", "task_request_key", "task_was_completed", "task_date_window")
        )
        if checkpoint_table and checkpoint_helpers:
            checks.append(
                _readiness_check(
                    "acquisition checkpoint table exists",
                    "PASS",
                    "acquisition_tasks exists and checkpoint helper functions are available.",
                )
            )
        else:
            checks.append(
                _readiness_check(
                    "acquisition checkpoint table exists",
                    "FAIL",
                    "acquisition_tasks or checkpoint helpers are missing.",
                )
            )
    except Exception as exc:  # pragma: no cover - defensive report path
        checks.append(
            _readiness_check(
                "acquisition checkpoint table exists",
                "FAIL",
                f"Unable to inspect acquisition checkpoint state: {exc!s}",
            )
        )

    try:
        normalization_path = all(hasattr(acquisition_raw_payloads, attr) for attr in ("store_raw_payload", "mark_payload_normalized"))
        checks.append(
            _readiness_check(
                "normalization path exists",
                "PASS" if normalization_path else "FAIL",
                "Normalization helpers are importable." if normalization_path else "Normalization helpers are missing.",
            )
        )
    except Exception as exc:  # pragma: no cover - defensive report path
        checks.append(_readiness_check("normalization path exists", "FAIL", f"Unable to inspect normalization helpers: {exc!s}"))

    polygon_key_present = bool(settings.polygon_api_key)
    checks.append(
        _readiness_check(
            "Polygon key present but never printed",
            "PASS" if polygon_key_present else "WARN",
            "Polygon API key is configured." if polygon_key_present else "Polygon API key is not configured in the local environment.",
        )
    )

    if settings.polygon_rate_limit_per_minute and settings.polygon_rate_limit_per_minute > 0:
        checks.append(
            _readiness_check(
                "Polygon rate limit configured",
                "PASS",
                f"Polygon rate limit is set to {settings.polygon_rate_limit_per_minute} requests/minute.",
            )
        )
    else:
        checks.append(
            _readiness_check(
                "Polygon rate limit configured",
                "FAIL",
                "Polygon rate limit is not configured or is non-positive.",
            )
        )

    guardrails_enabled = hasattr(acquisition_jobs, "_validate_polygon_guardrails") and "max_requests" in acquisition_jobs.run_acquisition_job.__code__.co_varnames
    checks.append(
        _readiness_check(
            "live acquisition guardrails enabled",
            "PASS" if guardrails_enabled else "FAIL",
            "Polygon acquisition guardrails are present." if guardrails_enabled else "Polygon acquisition guardrails are missing.",
        )
    )

    docs_marker = Path(__file__).resolve().parents[1] / "docs" / "CHANGES_V2.md"
    docs_aq = Path(__file__).resolve().parents[1] / "docs" / "ACQUISITION_INFRASTRUCTURE.md"
    docs_ready = docs_marker.exists() and docs_aq.exists()
    docs_detail = "Validation marker and acquisition infrastructure docs are present." if docs_ready else "Missing validation marker or acquisition docs."
    checks.append(_readiness_check("tests passing marker/documentation", "PASS" if docs_ready else "WARN", docs_detail))

    counts = Counter(row["status"] for row in checks)
    summary = {
        "pass": counts.get("PASS", 0),
        "warn": counts.get("WARN", 0),
        "fail": counts.get("FAIL", 0),
    }
    return {
        "generated_at": datetime.now(),
        "database": database,
        "checks": checks,
        "summary": summary,
    }


def _print_readiness_report(payload: dict[str, object]) -> None:
    database = payload.get("database", {})
    if isinstance(database, dict):
        db_rows = [
            ("configured_database_url", str(database.get("configured_database_url", ""))),
            ("hostname", str(database.get("hostname", ""))),
            ("port", str(database.get("port", ""))),
            ("hostname_resolves", str(database.get("hostname_resolves", ""))),
            ("tcp_connection_succeeds", str(database.get("tcp_connection_succeeds", ""))),
            ("sql_connection_succeeds", str(database.get("sql_connection_succeeds", ""))),
        ]
        if database.get("hostname_error"):
            db_rows.append(("hostname_error", str(database.get("hostname_error", ""))))
        if database.get("tcp_error"):
            db_rows.append(("tcp_error", str(database.get("tcp_error", ""))))
        if database.get("sql_error"):
            db_rows.append(("sql_error", str(database.get("sql_error", ""))))
        print("DATABASE")
        db_col1 = max([len("FIELD")] + [len(row[0]) for row in db_rows]) if db_rows else len("FIELD")
        print(f"{'FIELD'.ljust(db_col1)}  VALUE")
        print(f"{'-' * db_col1}  {'-' * 80}")
        for field, value in db_rows:
            print(f"{field.ljust(db_col1)}  {value}")
        print()
    checks = payload.get("checks", [])
    if not isinstance(checks, list):  # pragma: no cover - defensive
        _print_json(payload)
        return
    rows = []
    for check in checks:
        if isinstance(check, dict):
            rows.append(
                (
                    str(check.get("check", "")),
                    str(check.get("status", "")),
                    str(check.get("detail", "")),
                )
            )
    col1 = max([len("CHECK")] + [len(row[0]) for row in rows]) if rows else len("CHECK")
    col2 = max([len("STATUS")] + [len(row[1]) for row in rows]) if rows else len("STATUS")
    print(f"{'CHECK'.ljust(col1)}  {'STATUS'.ljust(col2)}  DETAIL")
    print(f"{'-' * col1}  {'-' * col2}  {'-' * 80}")
    for check, status, detail in rows:
        print(f"{check.ljust(col1)}  {status.ljust(col2)}  {detail}")
    summary = payload.get("summary", {})
    if isinstance(summary, dict):
        print(
            f"\nSummary: PASS={summary.get('pass', 0)} WARN={summary.get('warn', 0)} FAIL={summary.get('fail', 0)}"
        )


def _readiness_exit_code(payload: dict[str, object], strict: bool) -> int:
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):  # pragma: no cover - defensive
        return 1 if strict else 0
    if strict and (summary.get("warn", 0) or summary.get("fail", 0)):
        return 1
    return 0


def _dispatch(session: Session, args: argparse.Namespace) -> Any:
    if args.command == "refresh-watchlist":
        return _run_refresh_watchlist(session, args)
    if args.command == "rankings":
        return _run_rankings(session, args)
    if args.command == "evaluate-scores":
        return _run_evaluate_scores(session, args)
    if args.command == "evaluate-decisions":
        return _run_evaluate_decisions(session, args)
    if args.command == "health":
        return _run_health(session, args)
    if args.command == "status":
        return _run_status(session, args)
    if args.command == "run-experiment":
        return _run_experiment(session, args)
    if args.command == "list-experiments":
        return _run_list_experiments(session, args)
    if args.command == "experiment-summary":
        return _run_experiment_summary(session, args)
    if args.command == "diagnostics-distributions":
        return _run_diagnostics_distributions(session, args)
    if args.command == "diagnostics-signals":
        return _run_diagnostics_signals(session, args)
    if args.command == "polygon":
        if args.polygon_command == "smoke-test":
            return _run_polygon_smoke_test(args)
        raise ValueError(f"Unknown polygon command: {args.polygon_command}")
    if args.command == "polygon-smoke-test":
        return _run_polygon_smoke_test(args)
    if args.command == "acquisition":
        if args.acquisition_command == "create-job":
            return _run_acquisition_create_job(session, args)
        if args.acquisition_command == "run-job":
            return _run_acquisition_job(session, args)
        if args.acquisition_command == "readiness-report":
            return _run_acquisition_readiness_report(args)
        if args.acquisition_command == "status":
            return _run_acquisition_status(session, args)
        if args.acquisition_command == "retry-failed":
            return _run_acquisition_retry_failed(session, args)
        if args.acquisition_command == "pause":
            return _run_acquisition_pause(session, args)
        if args.acquisition_command == "resume":
            return _run_acquisition_resume(session, args)
        if args.acquisition_command == "estimate":
            return _run_acquisition_estimate(args)
        if args.acquisition_command == "plan":
            return _run_acquisition_plan(args)
        if args.acquisition_command == "campaign":
            return _run_acquisition_campaign(session, args)
        if args.acquisition_command == "import-flat-file":
            return _run_acquisition_import_flat_file(session, args)
        if args.acquisition_command == "list-flat-files":
            return _run_acquisition_list_flat_files(session, args)
        if args.acquisition_command == "inspect-flat-file":
            return _run_acquisition_inspect_flat_file(session, args)
        raise ValueError(f"Unknown acquisition command: {args.acquisition_command}")
    raise ValueError(f"Unknown command: {args.command}")


@contextmanager
def _session_scope() -> Any:
    init_db()
    with Session(engine) as session:
        yield session


def main(argv: list[str] | None = None, session_scope: Callable[[], Any] = _session_scope) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "acquisition" and getattr(args, "acquisition_command", None) == "readiness-report":
        payload = _run_acquisition_readiness_report(None, args)
    else:
        with session_scope() as session:
            payload = _dispatch(session, args)
    if args.command == "acquisition" and getattr(args, "acquisition_command", None) == "readiness-report":
        if args.json:
            _print_json(payload)
        else:
            _print_readiness_report(payload)
        return _readiness_exit_code(payload, args.strict)
    else:
        _print_json(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
