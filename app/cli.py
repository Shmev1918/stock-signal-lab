from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from sqlmodel import Session

from app.db.session import engine, init_db
from app.experiments.runner import ExperimentRequest, get_experiment_by_id, get_experiment_summary, list_experiments, run_experiment
from app.services.health_service import get_health_details
from app.services.analysis_service import build_strategy_rankings
from app.services.decision_service import get_decision_evaluation
from app.services.score_evaluation_service import get_score_evaluation
from app.services.watchlist_service import refresh_watchlist_workflow, watchlist_status_payload


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

    subparsers.add_parser("health", help="Show database and model health details.")
    subparsers.add_parser("status", help="Show watchlist status and data sources.")
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
