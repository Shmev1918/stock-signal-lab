from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.db.models import AcquisitionJob, AcquisitionTask, FlatFileManifest, FlatFileQualityEvent, RawPolygonStockDailyBar, Security, StockDailyPrice


def list_flat_file_manifests(
    session: Session,
    *,
    provider: str | None = None,
    dataset: str | None = None,
    market: str | None = None,
) -> list[dict[str, Any]]:
    statement = select(FlatFileManifest).order_by(FlatFileManifest.created_at.desc(), FlatFileManifest.id.desc())
    if provider:
        statement = statement.where(FlatFileManifest.provider == provider)
    if dataset:
        statement = statement.where(FlatFileManifest.dataset == dataset)
    if market:
        statement = statement.where(FlatFileManifest.market == market.upper())
    manifests = list(session.exec(statement))
    return [
        {
            "id": manifest.id,
            "provider": manifest.provider,
            "dataset": manifest.dataset,
            "market": manifest.market,
            "file_date": manifest.file_date,
            "remote_path": manifest.remote_path,
            "local_path": manifest.local_path,
            "checksum": manifest.checksum,
            "download_status": manifest.download_status,
            "ingest_status": manifest.ingest_status,
            "normalize_status": manifest.normalize_status,
            "downloaded_at": manifest.downloaded_at,
            "ingested_at": manifest.ingested_at,
            "normalized_at": manifest.normalized_at,
            "error_message": manifest.error_message,
        }
        for manifest in manifests
    ]


def inspect_flat_file_manifest(session: Session, manifest_id: int) -> dict[str, Any]:
    manifest = session.get(FlatFileManifest, manifest_id)
    if manifest is None:
        raise LookupError(f"Flat-file manifest not found: {manifest_id}")

    raw_rows = list(session.exec(select(RawPolygonStockDailyBar).where(RawPolygonStockDailyBar.source_manifest_id == manifest_id)))
    canonical_rows = list(session.exec(select(StockDailyPrice).where(StockDailyPrice.source_manifest_id == manifest_id)))
    events = list(session.exec(select(FlatFileQualityEvent).where(FlatFileQualityEvent.source_manifest_id == manifest_id)))
    warnings = [event for event in events if event.severity == "WARN"]
    errors = [event for event in events if event.severity == "ERROR"]
    duplicate_rows_skipped = _count_duplicate_rows(raw_rows)
    checksum_status = _checksum_status(manifest)
    canonical_symbols = sorted({row.symbol for row in canonical_rows if row.symbol})
    effective_file_date = _effective_file_date(manifest.file_date, raw_rows, canonical_rows)
    securities = list(
        session.exec(
            select(Security).where(
                Security.provider == manifest.provider,
                Security.symbol.in_(canonical_symbols) if canonical_symbols else True,
            )
        )
    )
    securities_created = 0
    securities_updated = 0
    for security in securities:
        if effective_file_date is None:
            continue
        if security.first_seen_date == effective_file_date and security.last_seen_date == effective_file_date:
            securities_created += 1
        elif security.last_seen_date == effective_file_date and security.first_seen_date is not None and security.first_seen_date < effective_file_date:
            securities_updated += 1

    return {
        "manifest": manifest.model_dump(),
        "manifest_status": manifest.normalize_status,
        "checksum_status": checksum_status,
        "raw_row_count": len(raw_rows),
        "canonical_row_count": len(canonical_rows),
        "quality_events_count": len(events),
        "warning_count": len(warnings),
        "error_count": len(errors),
        "duplicate_rows_skipped": duplicate_rows_skipped,
        "securities_created": securities_created,
        "securities_updated": securities_updated,
        "sample_quality_events": [event.model_dump() for event in events[:5]],
    }


def build_job_report(session: Session, job_id: int) -> dict[str, Any]:
    job = session.get(AcquisitionJob, job_id)
    if job is None:
        raise LookupError(f"Acquisition job not found: {job_id}")
    tasks = list(session.exec(select(AcquisitionTask).where(AcquisitionTask.job_id == job_id)))
    counts = Counter(task.status for task in tasks)
    failures = [
        {
            "task_id": task.id,
            "task_type": task.task_type,
            "ticker": task.ticker,
            "status": task.status,
            "last_error": task.last_error,
            "rows_imported": task.rows_imported,
        }
        for task in tasks
        if task.status == "FAILED"
    ]
    progress = round((counts.get("COMPLETED", 0) + counts.get("SKIPPED", 0)) / max(len(tasks), 1) * 100.0, 1)
    return {
        "job": job.model_dump(),
        "task_total": len(tasks),
        "task_counts": dict(counts),
        "progress_percent": progress,
        "failed_tasks": failures,
        "tasks": [task.model_dump() for task in tasks],
    }


def _checksum_status(manifest: FlatFileManifest) -> str:
    if not manifest.checksum:
        return "UNKNOWN"
    if not manifest.local_path:
        return "MISSING_LOCAL_FILE"
    try:
        from pathlib import Path

        path = Path(manifest.local_path)
        if not path.exists():
            return "MISSING_LOCAL_FILE"
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "MATCH" if digest.hexdigest() == manifest.checksum else "MISMATCH"
    except Exception:  # pragma: no cover - defensive
        return "UNKNOWN"


def _effective_file_date(
    manifest_file_date: date | None,
    raw_rows: list[RawPolygonStockDailyBar],
    canonical_rows: list[StockDailyPrice],
) -> date | None:
    if manifest_file_date is not None:
        return manifest_file_date
    candidate_dates = [row.price_date for row in canonical_rows if row.price_date is not None]
    if candidate_dates:
        return min(candidate_dates)
    candidate_dates = [row.price_date for row in raw_rows if row.price_date is not None]
    if candidate_dates:
        return min(candidate_dates)
    return None


def _count_duplicate_rows(raw_rows: list[RawPolygonStockDailyBar]) -> int:
    seen: set[tuple[str | None, date | None]] = set()
    duplicates = 0
    for row in raw_rows:
        key = (row.ticker, row.price_date)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates
