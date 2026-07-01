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
