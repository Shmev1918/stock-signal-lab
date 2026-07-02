from __future__ import annotations

import json
from contextlib import contextmanager

from app import cli


@contextmanager
def _fake_session_scope():
    yield object()


def test_cli_parses_refresh_watchlist() -> None:
    args = cli.build_parser().parse_args(
        ["refresh-watchlist", "--strategies", "balanced,conservative_quality", "--force-reingest", "--provider", "mock"]
    )
    assert args.command == "refresh-watchlist"
    assert args.strategies == "balanced,conservative_quality"
    assert args.force_reingest is True
    assert args.provider == "mock"


def test_cli_parses_health() -> None:
    args = cli.build_parser().parse_args(["health"])
    assert args.command == "health"


def test_cli_parses_diagnostics_distributions() -> None:
    args = cli.build_parser().parse_args(
        ["diagnostics-distributions", "--strategy-name", "balanced", "--signal-name", "volatility", "--signal-category", "RISK"]
    )
    assert args.command == "diagnostics-distributions"
    assert args.strategy_name == "balanced"
    assert args.signal_name == "volatility"
    assert args.signal_category == "RISK"


def test_cli_parses_diagnostics_signals() -> None:
    args = cli.build_parser().parse_args(["diagnostics-signals", "--ticker", "AAPL", "--as-of-date", "2026-01-01"])
    assert args.command == "diagnostics-signals"
    assert args.ticker == "AAPL"
    assert args.as_of_date == "2026-01-01"


def test_cli_parses_experiment_commands() -> None:
    run_args = cli.build_parser().parse_args(
        [
            "run-experiment",
            "--name",
            "balanced_high_opportunity_180d",
            "--experiment-type",
            "strategy_score_threshold",
            "--strategy-name",
            "balanced",
            "--horizon-days",
            "180",
            "--benchmark-ticker",
            "SPY",
            "--start-date",
            "2020-01-01",
            "--end-date",
            "2025-01-01",
            "--filters-json",
            '{"min_opportunity_score": 70}',
        ]
    )
    assert run_args.command == "run-experiment"
    assert run_args.name == "balanced_high_opportunity_180d"
    assert run_args.experiment_type == "strategy_score_threshold"
    assert run_args.strategy_name == "balanced"
    assert run_args.horizon_days == 180
    assert run_args.benchmark_ticker == "SPY"
    assert run_args.filters_json == '{"min_opportunity_score": 70}'

    list_args = cli.build_parser().parse_args(["list-experiments", "--limit", "10"])
    assert list_args.command == "list-experiments"
    assert list_args.limit == 10

    summary_args = cli.build_parser().parse_args(["experiment-summary", "--id", "12"])
    assert summary_args.command == "experiment-summary"
    assert summary_args.id == 12


def test_cli_refresh_watchlist_json_output(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _refresh_watchlist_workflow(session, **kwargs):
        captured.update(kwargs)
        return {
            "provider": kwargs["provider_name"],
            "tickers_processed": 1,
            "successes": [{"ticker": "AAPL"}],
            "failures": [],
            "strategies": kwargs["strategies"].split(","),
        }

    monkeypatch.setattr(cli, "refresh_watchlist_workflow", _refresh_watchlist_workflow)
    rc = cli.main(["refresh-watchlist", "--provider", "yfinance"], session_scope=_fake_session_scope)
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["provider"] == "yfinance"
    assert output["tickers_processed"] == 1
    assert output["successes"][0]["ticker"] == "AAPL"
    assert captured["provider_name"] == "yfinance"
    assert captured["force_reingest"] is False


def test_cli_rankings_and_evaluation_dispatch(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def _build_strategy_rankings(session, **kwargs):
        calls.append("rankings")
        assert kwargs["strategy_names"] == ["balanced"]
        assert kwargs["limit"] == 5
        return {"balanced": [{"ticker": "AAPL"}]}

    def _get_score_evaluation(session, **kwargs):
        calls.append("evaluate-scores")
        assert kwargs["horizon_days"] == 30
        return {"horizon": kwargs["horizon_days"], "count": 1}

    def _get_decision_evaluation(session, **kwargs):
        calls.append("evaluate-decisions")
        assert kwargs["horizon_days"] == 30
        return {"horizon": kwargs["horizon_days"], "count": 2}

    def _watchlist_status_payload(session):
        calls.append("status")
        return [{"ticker": "AAPL"}]

    monkeypatch.setattr(cli, "build_strategy_rankings", _build_strategy_rankings)
    monkeypatch.setattr(cli, "get_score_evaluation", _get_score_evaluation)
    monkeypatch.setattr(cli, "get_decision_evaluation", _get_decision_evaluation)
    monkeypatch.setattr(cli, "watchlist_status_payload", _watchlist_status_payload)

    assert cli.main(["rankings", "--strategy", "balanced", "--limit", "5"], session_scope=_fake_session_scope) == 0
    rankings = json.loads(capsys.readouterr().out)
    assert rankings["rankings"]["balanced"][0]["ticker"] == "AAPL"

    assert cli.main(["evaluate-scores", "--horizon", "30"], session_scope=_fake_session_scope) == 0
    scores = json.loads(capsys.readouterr().out)
    assert scores["horizon"] == 30

    assert cli.main(["evaluate-decisions", "--horizon", "30"], session_scope=_fake_session_scope) == 0
    decisions = json.loads(capsys.readouterr().out)
    assert decisions["count"] == 2

    assert cli.main(["status"], session_scope=_fake_session_scope) == 0
    status = json.loads(capsys.readouterr().out)
    assert status[0]["ticker"] == "AAPL"
    assert calls == ["rankings", "evaluate-scores", "evaluate-decisions", "status"]


def test_cli_health_json_output(monkeypatch, capsys) -> None:
    def _get_health_details(session):
        assert session is not None
        return {
            "status": "ok",
            "database_reachable": True,
            "active_provider": "mock",
            "default_scoring_strategy": "balanced",
            "scoring_model_version": "0.1.0",
            "signal_model_version": "0.1.0",
        }

    monkeypatch.setattr(cli, "get_health_details", _get_health_details)
    rc = cli.main(["health"], session_scope=_fake_session_scope)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["database_reachable"] is True
    assert payload["active_provider"] == "mock"


def test_cli_diagnostics_distributions_json_output(monkeypatch, capsys) -> None:
    def _get_distribution_diagnostics(session, **kwargs):
        assert kwargs["strategy_name"] == "balanced"
        assert kwargs["signal_name"] == "volatility"
        assert kwargs["signal_category"] == "RISK"
        return {
            "filters": kwargs,
            "scores": {"opportunity_score": {"count": 0}},
            "recommendations": {},
            "risk_categories": {},
            "signals": {},
            "signal_summary": {"always_0": [], "always_50": [], "always_100": [], "has_variation": []},
            "counts": {"score_rows": 0, "signal_rows": 0},
        }

    monkeypatch.setattr(cli, "get_distribution_diagnostics", _get_distribution_diagnostics)
    rc = cli.main(
        ["diagnostics-distributions", "--strategy-name", "balanced", "--signal-name", "volatility", "--signal-category", "RISK"],
        session_scope=_fake_session_scope,
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["filters"]["strategy_name"] == "balanced"
    assert payload["counts"]["score_rows"] == 0


def test_cli_diagnostics_signals_json_output(monkeypatch, capsys) -> None:
    def _get_signal_diagnostics(session, ticker, as_of_date=None):
        assert ticker == "AAPL"
        assert as_of_date is None
        return {
            "ticker": "AAPL",
            "as_of_date": "2026-01-01",
            "signals": [
                {
                    "signal_name": "volatility",
                    "signal_category": "RISK",
                    "input_values": {"price_inputs": {"price_count": 10}, "fundamental_inputs": None},
                    "raw_value": 0.2,
                    "normalized_score": 34.0,
                    "fallback_used": False,
                    "fallback_reason": None,
                    "source": "internal",
                }
            ],
        }

    monkeypatch.setattr(cli, "get_signal_diagnostics", _get_signal_diagnostics)
    rc = cli.main(["diagnostics-signals", "--ticker", "AAPL"], session_scope=_fake_session_scope)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ticker"] == "AAPL"
    assert payload["signals"][0]["signal_name"] == "volatility"


def test_cli_experiment_dispatch(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def _run_experiment(session, request):
        calls.append("run-experiment")
        assert request.name == "balanced_high_opportunity_180d"
        assert request.experiment_type == "strategy_score_threshold"
        assert request.strategy_name == "balanced"
        assert request.horizon_days == 180
        return {"id": 1, "name": request.name}

    def _list_experiments(session):
        calls.append("list-experiments")
        return [{"id": 1, "name": "balanced_high_opportunity_180d"}]

    def _get_experiment_summary(session, experiment_id):
        calls.append("experiment-summary")
        assert experiment_id == 1
        return {"experiment_id": experiment_id, "total_observations": 1}

    monkeypatch.setattr(cli, "run_experiment", _run_experiment)
    monkeypatch.setattr(cli, "list_experiments", _list_experiments)
    monkeypatch.setattr(cli, "get_experiment_summary", _get_experiment_summary)

    assert (
        cli.main(
            [
                "run-experiment",
                "--name",
                "balanced_high_opportunity_180d",
                "--experiment-type",
                "strategy_score_threshold",
                "--strategy-name",
                "balanced",
                "--horizon-days",
                "180",
                "--start-date",
                "2020-01-01",
                "--end-date",
                "2025-01-01",
            ],
            session_scope=_fake_session_scope,
        )
        == 0
    )
    run_output = json.loads(capsys.readouterr().out)
    assert run_output["id"] == 1

    assert cli.main(["list-experiments"], session_scope=_fake_session_scope) == 0
    list_output = json.loads(capsys.readouterr().out)
    assert list_output[0]["name"] == "balanced_high_opportunity_180d"

    assert cli.main(["experiment-summary", "--id", "1"], session_scope=_fake_session_scope) == 0
    summary_output = json.loads(capsys.readouterr().out)
    assert summary_output["experiment_id"] == 1

    assert calls == ["run-experiment", "list-experiments", "experiment-summary"]


def test_cli_parses_acquisition_commands() -> None:
    create_args = cli.build_parser().parse_args(
        [
            "acquisition",
            "create-job",
            "--job-name",
            "polygon_core",
            "--provider",
            "polygon",
            "--universe-name",
            "CUSTOM",
            "--config-json",
            '{"tickers":["AAPL"]}',
        ]
    )
    assert create_args.command == "acquisition"
    assert create_args.acquisition_command == "create-job"
    assert create_args.job_name == "polygon_core"
    assert create_args.provider == "polygon"
    assert create_args.universe_name == "CUSTOM"

    run_args = cli.build_parser().parse_args(["acquisition", "run-job", "12", "--force"])
    assert run_args.acquisition_command == "run-job"
    assert run_args.job_id == 12
    assert run_args.force is True

    estimate_args = cli.build_parser().parse_args(["acquisition", "estimate", "--years", "5"])
    assert estimate_args.acquisition_command == "estimate"
    assert estimate_args.years == 5


def test_cli_acquisition_dispatch(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def _create_acquisition_job(session, request):
        calls.append("create")
        assert request.job_name == "polygon_core"
        return {"job": {"id": 7, "job_name": request.job_name}}

    def _run_acquisition_job(session, job_id, force=False, provider=None):
        calls.append("run")
        assert job_id == 7
        assert force is True
        return {"job": {"id": job_id, "status": "COMPLETED"}}

    def _get_acquisition_job(session, job_id):
        calls.append("status")
        return {"job": {"id": job_id, "status": "COMPLETED"}}

    def _pause_acquisition_job(session, job_id):
        calls.append("pause")
        return {"job": {"id": job_id, "status": "PAUSED"}}

    def _resume_acquisition_job(session, job_id):
        calls.append("resume")
        return {"job": {"id": job_id, "status": "PENDING"}}

    def _retry_failed_tasks(session, job_id):
        calls.append("retry")
        return {"job": {"id": job_id, "status": "PENDING"}}

    def _estimate_acquisition(**kwargs):
        calls.append("estimate")
        return {"provider": kwargs["provider"], "estimated_api_calls": 12}

    class FakePolygonProvider:
        def __init__(self, *args, **kwargs):
            pass

        def smoke_checks(self, ticker):
            calls.append("smoke")
            return [
                type("Check", (), {"name": "daily_aggregates", "endpoint": "daily_aggregates", "ticker": ticker, "success": True, "status_code": 200, "error": None})()
            ]

    monkeypatch.setattr(cli, "create_acquisition_job", _create_acquisition_job)
    monkeypatch.setattr(cli, "run_acquisition_job", _run_acquisition_job)
    monkeypatch.setattr(cli, "get_acquisition_job", _get_acquisition_job)
    monkeypatch.setattr(cli, "pause_acquisition_job", _pause_acquisition_job)
    monkeypatch.setattr(cli, "resume_acquisition_job", _resume_acquisition_job)
    monkeypatch.setattr(cli, "retry_failed_tasks", _retry_failed_tasks)
    monkeypatch.setattr(cli, "estimate_acquisition", _estimate_acquisition)
    monkeypatch.setattr(cli, "PolygonMarketDataProvider", FakePolygonProvider)

    assert (
        cli.main(
            [
                "acquisition",
                "create-job",
                "--job-name",
                "polygon_core",
                "--provider",
                "polygon",
                "--config-json",
                '{"tickers":["AAPL"]}',
            ],
            session_scope=_fake_session_scope,
        )
        == 0
    )
    create_output = json.loads(capsys.readouterr().out)
    assert create_output["job"]["id"] == 7

    assert cli.main(["acquisition", "run-job", "7", "--force"], session_scope=_fake_session_scope) == 0
    run_output = json.loads(capsys.readouterr().out)
    assert run_output["job"]["status"] == "COMPLETED"

    assert cli.main(["acquisition", "status", "7"], session_scope=_fake_session_scope) == 0
    status_output = json.loads(capsys.readouterr().out)
    assert status_output["job"]["status"] == "COMPLETED"

    assert cli.main(["acquisition", "pause", "7"], session_scope=_fake_session_scope) == 0
    pause_output = json.loads(capsys.readouterr().out)
    assert pause_output["job"]["status"] == "PAUSED"

    assert cli.main(["acquisition", "resume", "7"], session_scope=_fake_session_scope) == 0
    resume_output = json.loads(capsys.readouterr().out)
    assert resume_output["job"]["status"] == "PENDING"

    assert cli.main(["acquisition", "retry-failed", "7"], session_scope=_fake_session_scope) == 0
    retry_output = json.loads(capsys.readouterr().out)
    assert retry_output["job"]["status"] == "PENDING"

    assert cli.main(["acquisition", "estimate", "--provider", "polygon"], session_scope=_fake_session_scope) == 0
    estimate_output = json.loads(capsys.readouterr().out)
    assert estimate_output["estimated_api_calls"] == 12

    assert cli.main(["polygon-smoke-test", "--ticker", "AAPL"], session_scope=_fake_session_scope) == 0
    smoke_output = json.loads(capsys.readouterr().out)
    assert smoke_output["provider"] == "polygon"
    assert smoke_output["checks"][0]["success"] is True
    assert calls == ["create", "run", "status", "pause", "resume", "retry", "estimate", "smoke"]
