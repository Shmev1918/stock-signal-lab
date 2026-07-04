from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import socket

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

import app.acquisition.checkpoints as acquisition_checkpoints
import app.acquisition.jobs as acquisition_jobs
import app.acquisition.raw_payloads as acquisition_raw_payloads
from app.config import get_settings


def redact_database_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def database_connection_diagnostics(database_url: str) -> dict[str, object]:
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
    except Exception as exc:  # pragma: no cover - environment-dependent
        sql_error = str(exc)

    return {
        "configured_database_url": redact_database_url(database_url),
        "hostname": hostname,
        "port": port,
        "hostname_resolves": resolved,
        "hostname_error": hostname_error,
        "tcp_connection_succeeds": tcp_connected,
        "tcp_error": tcp_error,
        "sql_connection_succeeds": sql_connected,
        "sql_error": sql_error,
    }


def alembic_readiness_detail(connection) -> dict[str, object]:
    settings = get_settings()
    migration_context = MigrationContext.configure(connection)
    current_revisions = list(migration_context.get_current_heads())
    alembic_cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    from alembic.script import ScriptDirectory

    head_revisions = list(ScriptDirectory.from_config(alembic_cfg).get_heads())
    return {"current": current_revisions, "head": head_revisions}


def _readiness_check(check: str, status: str, detail: str) -> dict[str, str]:
    return {"check": check, "status": status, "detail": detail}


def build_acquisition_readiness_report() -> dict[str, object]:
    settings = get_settings()
    database = database_connection_diagnostics(settings.database_url)
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
                alembic_status = alembic_readiness_detail(connection)
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

    docs_marker = Path(__file__).resolve().parents[2] / "docs" / "CHANGES_V2.md"
    docs_aq = Path(__file__).resolve().parents[2] / "docs" / "ACQUISITION_INFRASTRUCTURE.md"
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


def readiness_exit_code(payload: dict[str, object], strict: bool) -> int:
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):  # pragma: no cover - defensive
        return 1 if strict else 0
    if strict and (summary.get("warn", 0) or summary.get("fail", 0)):
        return 1
    return 0
