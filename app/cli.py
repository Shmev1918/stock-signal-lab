from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from sqlmodel import Session

from app.db.session import engine, init_db
from app.acquisition.estimates import estimate_acquisition
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

    subparsers.add_parser("health", help="Show database and model health details.")
    subparsers.add_parser("status", help="Show watchlist status and data sources.")
    subparsers.add_parser("polygon-smoke-test", help="Smoke test Polygon endpoints without a large import.").add_argument(
        "--ticker", default="AAPL"
    )
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
                "success": check.success,
                "status_code": check.status_code,
                "error": check.error,
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
    return run_acquisition_job(session, args.job_id, force=args.force)


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
    if args.command == "polygon-smoke-test":
        return _run_polygon_smoke_test(args)
    if args.command == "acquisition":
        if args.acquisition_command == "create-job":
            return _run_acquisition_create_job(session, args)
        if args.acquisition_command == "run-job":
            return _run_acquisition_job(session, args)
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
    with session_scope() as session:
        payload = _dispatch(session, args)
    _print_json(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
