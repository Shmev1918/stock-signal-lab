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
