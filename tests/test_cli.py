from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

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


def test_cli_parses_polygon_smoke_commands() -> None:
    nested = cli.build_parser().parse_args(["polygon", "smoke-test", "--ticker", "SPY"])
    assert nested.command == "polygon"
    assert nested.polygon_command == "smoke-test"
    assert nested.ticker == "SPY"

    alias = cli.build_parser().parse_args(["polygon-smoke-test", "--ticker", "AAPL"])
    assert alias.command == "polygon-smoke-test"
    assert alias.ticker == "AAPL"


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


def test_cli_parses_flat_file_audit_commands() -> None:
    list_args = cli.build_parser().parse_args(["acquisition", "list-flat-files", "--provider", "sample", "--dataset", "stocks_daily"])
    assert list_args.command == "acquisition"
    assert list_args.acquisition_command == "list-flat-files"
    assert list_args.provider == "sample"
    assert list_args.dataset == "stocks_daily"

    inspect_args = cli.build_parser().parse_args(["acquisition", "inspect-flat-file", "--manifest-id", "42"])
    assert inspect_args.command == "acquisition"
    assert inspect_args.acquisition_command == "inspect-flat-file"
    assert inspect_args.manifest_id == 42


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


def test_cli_acquisition_run_job_parses_live_guard_flags() -> None:
    args = cli.build_parser().parse_args(
        [
            "acquisition",
            "run-job",
            "7",
            "--force",
            "--live",
            "--max-requests",
            "5",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
        ]
    )
    assert args.command == "acquisition"
    assert args.acquisition_command == "run-job"
    assert args.live is True
    assert args.max_requests == 5
    assert args.start_date == "2026-01-01"
    assert args.end_date == "2026-01-31"


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


def test_cli_flat_file_audit_dispatch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "list_flat_file_manifests",
        lambda session, **kwargs: [{"id": 1, "provider": kwargs["provider"], "dataset": kwargs["dataset"], "market": kwargs["market"]}],
    )
    monkeypatch.setattr(
        cli,
        "inspect_flat_file_manifest",
        lambda session, manifest_id: {"manifest": {"id": manifest_id}, "manifest_status": "COMPLETED"},
    )

    rc = cli.main(["acquisition", "list-flat-files", "--provider", "sample", "--dataset", "stocks_daily"], session_scope=_fake_session_scope)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["provider"] == "sample"
    assert payload[0]["dataset"] == "stocks_daily"

    rc = cli.main(["acquisition", "inspect-flat-file", "--manifest-id", "7"], session_scope=_fake_session_scope)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["manifest"]["id"] == 7
    assert payload["manifest_status"] == "COMPLETED"


def test_cli_polygon_smoke_test_dispatch(monkeypatch, capsys) -> None:
    class _FakeCheck:
        def __init__(self, name, endpoint, ticker, status, http_status=None, error=None, cause="OK", rate_limited=False):
            self.name = name
            self.endpoint = endpoint
            self.ticker = ticker
            self.status = status
            self.http_status = http_status
            self.error = error
            self.cause = cause
            self.rate_limited = rate_limited

    class _FakeProvider:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def smoke_checks(self, ticker):
            assert ticker == "SPY"
            return [_FakeCheck("daily_aggregates", "/daily", "SPY", "PASS")]

    monkeypatch.setattr(cli, "PolygonMarketDataProvider", _FakeProvider)
    monkeypatch.setattr(cli, "get_settings", lambda: type("S", (), {"polygon_api_key": "key", "polygon_mode": "free", "polygon_rate_limit_per_minute": 3})())

    rc = cli.main(["polygon", "smoke-test", "--ticker", "SPY"], session_scope=_fake_session_scope)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "polygon"
    assert payload["checks"][0]["status"] == "PASS"


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

    plan_args = cli.build_parser().parse_args(
        [
            "acquisition",
            "plan",
            "--provider",
            "polygon",
            "--dataset",
            "stocks_daily",
            "--start-date",
            "1995-01-01",
            "--end-date",
            "2025-12-31",
        ]
    )
    assert plan_args.acquisition_command == "plan"
    assert plan_args.dataset == "stocks_daily"
    assert plan_args.start_date == "1995-01-01"

    campaign_plan_args = cli.build_parser().parse_args(
        [
            "acquisition",
            "campaign",
            "plan",
            "--config",
            "configs/stock_historical_campaign.yml",
        ]
    )
    assert campaign_plan_args.acquisition_command == "campaign"
    assert campaign_plan_args.campaign_command == "plan"
    assert campaign_plan_args.config.endswith("stock_historical_campaign.yml")

    campaign_run_args = cli.build_parser().parse_args(
        [
            "acquisition",
            "campaign",
            "run",
            "--config",
            "configs/stock_historical_campaign.yml",
            "--phase",
            "1",
            "--live",
            "--max-files",
            "10",
            "--max-bytes",
            "1000000000",
            "--min-free-bytes",
            "5000000000",
        ]
    )
    assert campaign_run_args.acquisition_command == "campaign"
    assert campaign_run_args.campaign_command == "run"
    assert campaign_run_args.phase == 1
    assert campaign_run_args.live is True
    assert campaign_run_args.max_files == 10
    assert campaign_run_args.max_bytes == 1000000000
    assert campaign_run_args.min_free_bytes == 5000000000

    campaign_status_args = cli.build_parser().parse_args(
        ["acquisition", "campaign", "status", "--campaign-id", "7"]
    )
    assert campaign_status_args.campaign_command == "status"
    assert campaign_status_args.campaign_id == 7

    campaign_audit_args = cli.build_parser().parse_args(
        ["acquisition", "campaign", "audit", "--campaign-id", "7"]
    )
    assert campaign_audit_args.campaign_command == "audit"
    assert campaign_audit_args.campaign_id == 7

    import_args = cli.build_parser().parse_args(
        [
            "acquisition",
            "import-flat-file",
            "--provider",
            "sample",
            "--dataset",
            "stocks_daily",
            "--path",
            "tests/data/flat_files/sample/stocks_daily/US/2024-01-02.csv",
        ]
    )
    assert import_args.acquisition_command == "import-flat-file"
    assert import_args.path.endswith("2024-01-02.csv")

    readiness_args = cli.build_parser().parse_args(["acquisition", "readiness-report"])
    assert readiness_args.acquisition_command == "readiness-report"


def test_cli_database_url_redaction_and_diagnostics(monkeypatch) -> None:
    class FakeConnection:
        def execute(self, *args, **kwargs):
            return self

        def first(self):
            return (1,)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(cli, "create_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(cli.socket, "getaddrinfo", lambda *args, **kwargs: [object()])
    monkeypatch.setattr(cli.socket, "create_connection", lambda *args, **kwargs: FakeConnection())

    payload = cli._database_connection_diagnostics("postgresql+psycopg://stock:secret@db:5432/stock_signal_lab")
    assert payload["configured_database_url"] == "postgresql+psycopg://stock:***@db:5432/stock_signal_lab"
    assert payload["hostname"] == "db"
    assert payload["port"] == 5432
    assert payload["hostname_resolves"] is True
    assert payload["tcp_connection_succeeds"] is True
    assert payload["sql_connection_succeeds"] is True


def test_cli_acquisition_readiness_strict_exit_behavior(monkeypatch, capsys) -> None:
    def _readiness_report(_session, _args):
        return {
            "database": {
                "configured_database_url": "postgresql+psycopg://stock:***@db:5432/stock_signal_lab",
                "hostname": "db",
                "port": 5432,
                "hostname_resolves": True,
                "tcp_connection_succeeds": True,
                "sql_connection_succeeds": False,
            },
            "checks": [{"check": "database connection", "status": "WARN", "detail": "sql unavailable"}],
            "summary": {"pass": 0, "warn": 1, "fail": 0},
        }

    monkeypatch.setattr(cli, "_run_acquisition_readiness_report", _readiness_report)
    assert cli.main(["acquisition", "readiness-report", "--json"], session_scope=_fake_session_scope) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["database"]["hostname"] == "db"

    assert cli.main(["acquisition", "readiness-report", "--json", "--strict"], session_scope=_fake_session_scope) == 1


def test_cli_acquisition_campaign_requires_caps_when_live() -> None:
    args = cli.build_parser().parse_args(
        [
            "acquisition",
            "campaign",
            "run",
            "--config",
            "configs/stock_historical_campaign.yml",
            "--phase",
            "1",
            "--live",
        ]
    )
    with pytest.raises(ValueError, match="--max-files"):
        cli._run_acquisition_campaign_run(object(), args)


def test_cli_acquisition_dispatch(monkeypatch, capsys) -> None:
    calls: list[str] = []

    def _create_acquisition_job(session, request):
        calls.append("create")
        assert request.job_name == "polygon_core"
        return {"job": {"id": 7, "job_name": request.job_name}}

    def _run_acquisition_job(session, job_id, force=False, provider=None, **kwargs):
        calls.append("run")
        assert job_id == 7
        assert force is True
        assert kwargs["live"] is False
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

    def _estimate_flat_file_plan(**kwargs):
        calls.append("plan")
        assert kwargs["dataset"] == "stocks_daily"
        assert kwargs["start_date"].isoformat() == "1995-01-01"
        return {"provider": kwargs["provider"], "estimated_files": 123}

    def _import_flat_file(session, args):
        calls.append("import-flat-file")
        assert args.path.endswith("2024-01-02.csv")
        return {
            "provider": args.provider,
            "dataset": args.dataset,
            "row_count": 3,
            "raw_inserted_count": 3,
            "canonical_upsert_count": 3,
            "quality_events_created": 0,
            "warnings": [],
            "errors": [],
        }

    def _plan_stock_campaign(session, config_path):
        calls.append("campaign-plan")
        assert str(config_path).endswith("stock_historical_campaign.yml")
        return {
            "campaign_id": 41,
            "config_path": str(config_path),
            "campaign": {"provider": "polygon"},
            "phases": [{"phase": 0, "status": "PLANNED"}],
            "warnings": [],
            "summary": {"phase_count": 1, "plannable_phases": 1, "blocked_phases": 0},
        }

    def _run_stock_campaign_phase(session, config_path, **kwargs):
        calls.append(f"campaign-run-{kwargs['phase']}")
        assert str(config_path).endswith("stock_historical_campaign.yml")
        return {"campaign_id": 41, "phase": {"phase": kwargs["phase"], "status": "COMPLETED"}, "campaign": {"id": 41}}

    def _campaign_status_report(session, campaign_id):
        calls.append("campaign-status")
        assert campaign_id == 41
        return {"campaign": {"id": campaign_id}, "phases": []}

    def _campaign_audit_report(session, campaign_id):
        calls.append("campaign-audit")
        assert campaign_id == 41
        return {"campaign": {"id": campaign_id}, "phase_audits": []}

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
    monkeypatch.setattr(cli, "estimate_flat_file_plan", _estimate_flat_file_plan)
    monkeypatch.setattr(cli, "_run_acquisition_import_flat_file", _import_flat_file)
    monkeypatch.setattr(cli, "plan_stock_campaign", _plan_stock_campaign)
    monkeypatch.setattr(cli, "run_stock_campaign_phase", _run_stock_campaign_phase)
    monkeypatch.setattr(cli, "campaign_status_report", _campaign_status_report)
    monkeypatch.setattr(cli, "campaign_audit_report", _campaign_audit_report)
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

    assert (
        cli.main(
            [
                "acquisition",
                "plan",
                "--provider",
                "polygon",
                "--dataset",
                "stocks_daily",
                "--start-date",
                "1995-01-01",
                "--end-date",
                "2025-12-31",
            ],
            session_scope=_fake_session_scope,
        )
        == 0
    )
    plan_output = json.loads(capsys.readouterr().out)
    assert plan_output["estimated_files"] == 123

    assert (
        cli.main(
            [
                "acquisition",
                "campaign",
                "plan",
                "--config",
                "configs/stock_historical_campaign.yml",
            ],
            session_scope=_fake_session_scope,
        )
        == 0
    )
    campaign_output = json.loads(capsys.readouterr().out)
    assert campaign_output["campaign_id"] == 41

    assert (
        cli.main(
            [
                "acquisition",
                "campaign",
                "run",
                "--config",
                "configs/stock_historical_campaign.yml",
                "--phase",
                "1",
                "--live",
                "--max-files",
                "10",
                "--max-bytes",
                "1000000000",
            ],
            session_scope=_fake_session_scope,
        )
        == 0
    )
    campaign_run_output = json.loads(capsys.readouterr().out)
    assert campaign_run_output["campaign_id"] == 41

    assert cli.main(["acquisition", "campaign", "status", "--campaign-id", "41"], session_scope=_fake_session_scope) == 0
    campaign_status_output = json.loads(capsys.readouterr().out)
    assert campaign_status_output["campaign"]["id"] == 41

    assert cli.main(["acquisition", "campaign", "audit", "--campaign-id", "41"], session_scope=_fake_session_scope) == 0
    campaign_audit_output = json.loads(capsys.readouterr().out)
    assert campaign_audit_output["campaign"]["id"] == 41

    assert (
        cli.main(
            [
                "acquisition",
                "import-flat-file",
                "--provider",
                "sample",
                "--dataset",
                "stocks_daily",
                "--path",
                "tests/data/flat_files/sample/stocks_daily/US/2024-01-02.csv",
            ],
            session_scope=_fake_session_scope,
        )
        == 0
    )
    import_output = json.loads(capsys.readouterr().out)
    assert import_output["raw_inserted_count"] == 3

    assert cli.main(["polygon", "smoke-test", "--ticker", "AAPL"], session_scope=_fake_session_scope) == 0
    smoke_output = json.loads(capsys.readouterr().out)
    assert smoke_output["provider"] == "polygon"
    assert smoke_output["checks"][0]["status"] == "PASS"
    assert calls == [
        "create",
        "run",
        "status",
        "pause",
        "resume",
        "retry",
        "estimate",
        "plan",
        "campaign-plan",
        "campaign-run-1",
        "campaign-status",
        "campaign-audit",
        "import-flat-file",
        "smoke",
    ]


def test_cli_acquisition_readiness_report_prints_table(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _readiness_report(session, args):
        captured["session"] = session
        captured["args"] = args
        return {
            "checks": [
                {"check": "database connection", "status": "PASS", "detail": "ok"},
                {"check": "Polygon key present but never printed", "status": "WARN", "detail": "missing"},
            ],
            "summary": {"pass": 1, "warn": 1, "fail": 0},
        }

    monkeypatch.setattr(cli, "_run_acquisition_readiness_report", _readiness_report)
    rc = cli.main(["acquisition", "readiness-report"], session_scope=_fake_session_scope)
    assert rc == 0
    output = capsys.readouterr().out
    assert "CHECK" in output
    assert "database connection" in output
    assert "PASS" in output
    assert "WARN" in output
    assert "Summary: PASS=1 WARN=1 FAIL=0" in output
    assert "session" in captured
