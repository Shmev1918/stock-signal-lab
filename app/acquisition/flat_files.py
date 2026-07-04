from __future__ import annotations

import gzip
import csv
import json
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.acquisition.flat_file_catalog import business_days_between, get_dataset_spec
from app.db.models import DailyPrice, FlatFileManifest, FlatFileQualityEvent, RawPolygonStockDailyBar, Security, StockDailyPrice
from app.providers.flat_file_provider import FlatFileDescriptor, FlatFileProvider


@dataclass(frozen=True)
class FlatFileImportRequest:
    provider: str
    dataset: str
    market: str
    start_date: date
    end_date: date
    staging_dir: Path
    force: bool = False


@dataclass(frozen=True)
class StockDailyFlatFileImportResult:
    manifest: dict[str, Any]
    row_count: int
    raw_inserted_count: int
    canonical_upsert_count: int
    quality_events_created: int
    warnings: list[str]
    errors: list[str]


def estimate_flat_file_plan(
    *,
    provider: str,
    dataset: str,
    market: str,
    start_date: date,
    end_date: date,
    staging_dir: str | Path | None = None,
) -> dict[str, Any]:
    spec = get_dataset_spec(dataset)
    file_count = business_days_between(start_date, end_date) if spec.cadence == "daily" else 0
    compressed_size_bytes = int(file_count * spec.estimated_compressed_size_mb * 1024 * 1024)
    uncompressed_size_bytes = int(file_count * spec.estimated_uncompressed_size_mb * 1024 * 1024)
    estimated_rows = file_count * spec.estimated_rows_per_file
    estimated_disk_usage_gb = round((compressed_size_bytes + uncompressed_size_bytes) / (1024**3) * 1.2, 2)
    estimated_runtime_minutes = round(file_count * spec.estimated_runtime_seconds_per_file / 60.0, 1)
    warnings: list[str] = []
    if provider == "polygon":
        warnings.append("Polygon phase 1 planning is heuristic-only; no network calls are made.")
    if dataset.startswith("options"):
        warnings.append("Options scope should remain narrow in phase 1.")
    return {
        "provider": provider,
        "dataset": dataset,
        "market": market.upper(),
        "staging_dir": str(staging_dir) if staging_dir else None,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "estimated_files": file_count,
        "estimated_download_size_mb": round(compressed_size_bytes / 1024**2, 2),
        "estimated_postgresql_rows": estimated_rows,
        "estimated_disk_usage_gb": estimated_disk_usage_gb,
        "estimated_runtime_minutes": estimated_runtime_minutes,
        "warnings": warnings,
        "dataset_description": spec.description,
    }


class FlatFileImportService:
    def __init__(self, session: Session, provider: FlatFileProvider, staging_dir: str | Path) -> None:
        self.session = session
        self.provider = provider
        self.staging_dir = Path(staging_dir)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def ensure_manifests(self, descriptors: list[FlatFileDescriptor]) -> list[FlatFileManifest]:
        manifests: list[FlatFileManifest] = []
        for descriptor in descriptors:
            manifest = self.session.exec(
                select(FlatFileManifest).where(FlatFileManifest.remote_path == descriptor.remote_path)
            ).first()
            if manifest is None:
                manifest = FlatFileManifest(
                    provider=descriptor.provider,
                    dataset=descriptor.dataset,
                    market=descriptor.market,
                    file_date=descriptor.file_date,
                    remote_path=descriptor.remote_path,
                    checksum=descriptor.checksum,
                    compressed_size=descriptor.compressed_size,
                    uncompressed_size=descriptor.uncompressed_size,
                )
                self.session.add(manifest)
                self.session.commit()
                self.session.refresh(manifest)
            manifests.append(manifest)
        return manifests

    def run(self, dataset: str, *, start_date: date, end_date: date, market: str = "US", force: bool = False) -> dict[str, Any]:
        descriptors = self.provider.list_available_files(dataset, start_date=start_date, end_date=end_date, market=market)
        manifests = self.ensure_manifests(descriptors)
        summary = {
            "provider": self.provider.provider_name,
            "dataset": dataset,
            "market": market.upper(),
            "files_total": len(descriptors),
            "files_downloaded": 0,
            "files_ingested": 0,
            "files_normalized": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "warnings": [],
            "errors": [],
            "manifests": [],
        }

        for descriptor, manifest in zip(descriptors, manifests, strict=True):
            manifest_row = self.session.get(FlatFileManifest, manifest.id or 0)
            if manifest_row is None:
                continue
            if not force and manifest_row.normalize_status == "COMPLETED":
                summary["files_skipped"] += 1
                summary["manifests"].append(manifest_row.model_dump())
                continue

            try:
                staged_path = self._ensure_local_file(descriptor, manifest_row, force=force)
                rows_imported = self._ingest_daily_prices(staged_path, manifest_row, descriptor.provider)
                manifest_row.ingest_status = "COMPLETED"
                manifest_row.normalize_status = "COMPLETED"
                manifest_row.ingested_at = datetime.now()
                manifest_row.normalized_at = datetime.now()
                manifest_row.error_message = None
                self.session.add(manifest_row)
                self.session.commit()
                summary["files_downloaded"] += 1
                summary["files_ingested"] += 1
                summary["files_normalized"] += 1
                summary["manifests"].append(
                    {
                        **manifest_row.model_dump(),
                        "rows_imported": rows_imported,
                    }
                )
            except Exception as exc:
                manifest_row.error_message = str(exc)
                if manifest_row.download_status != "COMPLETED":
                    manifest_row.download_status = "FAILED"
                if manifest_row.ingest_status != "COMPLETED":
                    manifest_row.ingest_status = "FAILED"
                if manifest_row.normalize_status != "COMPLETED":
                    manifest_row.normalize_status = "FAILED"
                self.session.add(manifest_row)
                self.session.commit()
                summary["files_failed"] += 1
                summary["errors"].append(
                    {
                        "remote_path": descriptor.remote_path,
                        "error": str(exc),
                    }
                )

        return summary

    def resume(self, dataset: str, *, start_date: date, end_date: date, market: str = "US") -> dict[str, Any]:
        return self.run(dataset, start_date=start_date, end_date=end_date, market=market, force=False)

    def checkpoint(self, dataset: str, *, start_date: date, end_date: date, market: str = "US") -> dict[str, Any]:
        descriptors = self.provider.list_available_files(dataset, start_date=start_date, end_date=end_date, market=market)
        manifests = self.ensure_manifests(descriptors)
        completed = sum(1 for manifest in manifests if manifest.normalize_status == "COMPLETED")
        return {
            "provider": self.provider.provider_name,
            "dataset": dataset,
            "market": market.upper(),
            "files_total": len(manifests),
            "files_completed": completed,
            "files_remaining": len(manifests) - completed,
        }

    def import_stock_daily_file(
        self,
        path: str | Path,
        *,
        provider: str,
        dataset: str,
        market: str = "US",
        expected_checksum: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Flat-file source not found: {file_path}")
        spec = get_dataset_spec(dataset)
        if spec.dataset != "stocks_daily":
            raise LookupError(f"Canonical landing importer currently supports stocks_daily only: {dataset}")

        checksum = _sha256_file(file_path)
        if expected_checksum and expected_checksum != checksum:
            raise ValueError(f"Checksum mismatch for {file_path}")

        manifest = self.session.exec(
            select(FlatFileManifest).where(FlatFileManifest.remote_path == file_path.as_posix())
        ).first()
        if manifest is None:
            manifest = FlatFileManifest(
                provider=provider,
                dataset=dataset,
                market=market.upper(),
                file_date=_infer_file_date(file_path),
                remote_path=file_path.as_posix(),
                local_path=file_path.as_posix(),
                checksum=checksum,
                compressed_size=file_path.stat().st_size,
                uncompressed_size=file_path.stat().st_size,
            )
            self.session.add(manifest)
            self.session.commit()
            self.session.refresh(manifest)
        elif manifest.checksum and manifest.checksum != checksum:
            raise ValueError(f"Checksum mismatch for {file_path}")
        else:
            manifest.checksum = checksum
            manifest.compressed_size = file_path.stat().st_size
            manifest.uncompressed_size = file_path.stat().st_size
            manifest.local_path = file_path.as_posix()
            self.session.add(manifest)
            self.session.commit()

        if manifest.normalize_status == "COMPLETED" and not force:
            return {
                "provider": provider,
                "dataset": dataset,
                "market": market.upper(),
                "manifest": manifest.model_dump(),
                "row_count": 0,
                "raw_inserted_count": 0,
                "canonical_upsert_count": 0,
                "quality_events_created": 0,
                "warnings": ["Manifest already completed; import skipped."],
                "errors": [],
            }

        self._replace_quality_events(manifest.id or 0)
        rows = _read_daily_flat_file_rows(file_path)
        validated_rows: list[dict[str, Any]] = []
        quality_events: list[dict[str, Any]] = []
        for row_number, row in enumerate(rows, start=1):
            normalized, row_events = _validate_daily_row(row, row_number=row_number, manifest_id=manifest.id or 0)
            quality_events.extend(row_events)
            if normalized is not None:
                validated_rows.append(normalized)

        if not validated_rows and rows:
            manifest.download_status = "COMPLETED"
            manifest.ingest_status = "FAILED"
            manifest.normalize_status = "FAILED"
            manifest.error_message = "No valid rows were available for normalization."
            self.session.add(manifest)
            self.session.commit()
            for event in quality_events:
                self.session.add(FlatFileQualityEvent(**event))
            self.session.commit()
            return {
                "provider": provider,
                "dataset": dataset,
                "market": market.upper(),
                "manifest": manifest.model_dump(),
                "row_count": len(rows),
                "raw_inserted_count": 0,
                "canonical_upsert_count": 0,
                "quality_events_created": len(quality_events),
                "warnings": [],
                "errors": ["No valid rows were available for normalization."],
            }

        for event in quality_events:
            self.session.add(FlatFileQualityEvent(**event))
        self.session.commit()

        raw_inserted = self._load_raw_landing_rows(manifest.id or 0, validated_rows)
        canonical_upserted = self._normalize_daily_bars(manifest.id or 0, provider)

        manifest.download_status = "COMPLETED"
        manifest.ingest_status = "COMPLETED"
        manifest.normalize_status = "COMPLETED"
        manifest.downloaded_at = datetime.now()
        manifest.ingested_at = datetime.now()
        manifest.normalized_at = datetime.now()
        manifest.error_message = None
        self.session.add(manifest)
        self.session.commit()

        warnings = [event["message"] for event in quality_events if event["severity"] == "WARN"]
        errors = [event["message"] for event in quality_events if event["severity"] == "ERROR"]
        return {
            "provider": provider,
            "dataset": dataset,
            "market": market.upper(),
            "manifest": manifest.model_dump(),
            "row_count": len(rows),
            "raw_inserted_count": raw_inserted,
            "canonical_upsert_count": canonical_upserted,
            "quality_events_created": len(quality_events),
            "warnings": warnings,
            "errors": errors,
        }

    def _ensure_local_file(self, descriptor: FlatFileDescriptor, manifest: FlatFileManifest, *, force: bool) -> Path:
        if not force and manifest.local_path:
            local_path = Path(manifest.local_path)
            if local_path.exists():
                if not self.provider.verify(local_path, manifest.checksum):
                    raise ValueError(f"Checksum mismatch for {descriptor.remote_path}")
                if manifest.download_status != "COMPLETED":
                    manifest.download_status = "COMPLETED"
                    manifest.downloaded_at = datetime.now()
                    self.session.add(manifest)
                    self.session.commit()
                return local_path

        downloaded_path = self.provider.download(descriptor, self.staging_dir)
        if not self.provider.verify(downloaded_path, descriptor.checksum):
            raise ValueError(f"Checksum mismatch for {descriptor.remote_path}")
        staged_path = self.provider.stage(downloaded_path, self.staging_dir)
        manifest.local_path = str(staged_path)
        manifest.checksum = descriptor.checksum
        manifest.compressed_size = descriptor.compressed_size
        manifest.uncompressed_size = descriptor.uncompressed_size
        manifest.download_status = "COMPLETED"
        manifest.downloaded_at = datetime.now()
        self.session.add(manifest)
        self.session.commit()
        return staged_path

    def _ingest_daily_prices(self, staged_path: Path, manifest: FlatFileManifest, provider_name: str) -> int:
        with _open_text_file(staged_path) as handle:
            reader = csv.DictReader(handle)
            required = {"ticker", "price_date", "close"}
            if not required <= set(reader.fieldnames or []):
                raise ValueError(f"Missing required columns in {staged_path.name}")
            rows = list(reader)

        imported = 0
        for row in rows:
            ticker = str(row["ticker"]).strip().upper()
            price_date = date.fromisoformat(str(row["price_date"]))
            source = str(row.get("source") or f"{provider_name}:{manifest.dataset}")
            existing = self.session.exec(
                select(DailyPrice).where(
                    DailyPrice.ticker == ticker,
                    DailyPrice.price_date == price_date,
                    DailyPrice.source == source,
                )
            ).first()
            payload = {
                "ticker": ticker,
                "price_date": price_date,
                "open": _optional_float(row.get("open")),
                "high": _optional_float(row.get("high")),
                "low": _optional_float(row.get("low")),
                "close": float(row["close"]),
                "adj_close": _optional_float(row.get("adj_close")),
                "volume": _optional_int(row.get("volume")),
                "source": source,
            }
            if existing is None:
                self.session.add(DailyPrice(**payload))
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
                self.session.add(existing)
            imported += 1

        self.session.commit()
        manifest.ingest_status = "COMPLETED"
        manifest.normalize_status = "COMPLETED"
        manifest.ingested_at = datetime.now()
        manifest.normalized_at = datetime.now()
        manifest.error_message = None
        self.session.add(manifest)
        self.session.commit()
        return imported

    def _replace_quality_events(self, manifest_id: int) -> None:
        existing = list(self.session.exec(select(FlatFileQualityEvent).where(FlatFileQualityEvent.source_manifest_id == manifest_id)))
        for row in existing:
            self.session.delete(row)
        self.session.commit()

    def _upsert_security(self, provider_name: str, symbol: str, price_date: date) -> Security:
        existing = self.session.exec(
            select(Security).where(Security.provider == provider_name, Security.symbol == symbol)
        ).first()
        now = datetime.now()
        if existing is None:
            security = Security(
                symbol=symbol,
                provider=provider_name,
                asset_type="equity",
                first_seen_date=price_date,
                last_seen_date=price_date,
                created_at=now,
                updated_at=now,
            )
            self.session.add(security)
            self.session.flush()
            return security

        first_seen = existing.first_seen_date or price_date
        last_seen = existing.last_seen_date or price_date
        if price_date < first_seen:
            first_seen = price_date
        if price_date > last_seen:
            last_seen = price_date
        existing.asset_type = existing.asset_type or "equity"
        existing.first_seen_date = first_seen
        existing.last_seen_date = last_seen
        existing.updated_at = now
        self.session.add(existing)
        self.session.flush()
        return existing

    def _load_raw_landing_rows(self, manifest_id: int, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        engine = self.session.get_bind()
        if engine is not None and getattr(engine.dialect, "name", "") == "postgresql":
            return self._copy_raw_rows_postgres(manifest_id, rows)
        return self._load_raw_rows_sqlalchemy(manifest_id, rows)

    def _copy_raw_rows_postgres(self, manifest_id: int, rows: list[dict[str, Any]]) -> int:
        header = [
            "source_manifest_id",
            "row_number",
            "ticker",
            "price_date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "source",
            "raw_row",
        ]
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False) as temp_handle:
            temp_path = Path(temp_handle.name)
            writer = csv.DictWriter(temp_handle, fieldnames=header)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "source_manifest_id": manifest_id,
                        "row_number": row["row_number"],
                        "ticker": row["ticker"],
                        "price_date": row["price_date"].isoformat(),
                        "open": row["open"] if row["open"] is not None else "",
                        "high": row["high"] if row["high"] is not None else "",
                        "low": row["low"] if row["low"] is not None else "",
                        "close": row["close"] if row["close"] is not None else "",
                        "adj_close": row["adj_close"] if row["adj_close"] is not None else "",
                        "volume": row["volume"] if row["volume"] is not None else "",
                        "source": row["source"],
                        "raw_row": json.dumps(row["raw_row"]),
                    }
                )
        try:
            bind = self.session.get_bind()
            raw_connection = bind.raw_connection() if bind is not None and hasattr(bind, "raw_connection") else None
            if raw_connection is None:  # pragma: no cover - defensive
                return self._load_raw_rows_sqlalchemy(manifest_id, rows)
            try:
                with raw_connection.cursor() as cursor:
                    copy_sql = (
                        "COPY raw_polygon_stock_daily_bars "
                        "(source_manifest_id, row_number, ticker, price_date, open, high, low, close, adj_close, volume, source, raw_row) "
                        "FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
                    )
                    with cursor.copy(copy_sql) as copy:
                        copy.write(temp_path.read_text(encoding="utf-8"))
                raw_connection.commit()
            except Exception:
                raw_connection.rollback()
                raise
            finally:
                raw_connection.close()
        finally:
            temp_path.unlink(missing_ok=True)
        return len(rows)

    def _load_raw_rows_sqlalchemy(self, manifest_id: int, rows: list[dict[str, Any]]) -> int:
        for row in rows:
            existing = self.session.exec(
                select(RawPolygonStockDailyBar).where(
                    RawPolygonStockDailyBar.source_manifest_id == manifest_id,
                    RawPolygonStockDailyBar.row_number == row["row_number"],
                )
            ).first()
            payload = {
                "source_manifest_id": manifest_id,
                "row_number": row["row_number"],
                "ticker": row["ticker"],
                "price_date": row["price_date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "adj_close": row["adj_close"],
                "volume": row["volume"],
                "source": row["source"],
                "raw_row": row["raw_row"],
            }
            if existing is None:
                self.session.add(RawPolygonStockDailyBar(**payload))
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
                self.session.add(existing)
        self.session.commit()
        return len(rows)

    def _normalize_daily_bars(self, manifest_id: int, provider_name: str) -> int:
        raw_rows = list(
            self.session.exec(
                select(RawPolygonStockDailyBar).where(RawPolygonStockDailyBar.source_manifest_id == manifest_id)
            )
        )
        upserted = 0
        security_cache: dict[str, Security] = {}
        for raw_row in raw_rows:
            if raw_row.ticker is None or raw_row.price_date is None or raw_row.close is None:
                continue
            security_key = f"{provider_name}:{raw_row.ticker}"
            security = security_cache.get(security_key)
            if security is None:
                security = self._upsert_security(provider_name, raw_row.ticker, raw_row.price_date)
                security_cache[security_key] = security
            existing = self.session.exec(
                select(StockDailyPrice).where(
                    StockDailyPrice.source_manifest_id == manifest_id,
                    StockDailyPrice.security_id == security.id,
                    StockDailyPrice.price_date == raw_row.price_date,
                )
            ).first()
            payload = {
                "source_manifest_id": manifest_id,
                "security_id": security.id,
                "symbol": raw_row.ticker,
                "ticker": raw_row.ticker,
                "price_date": raw_row.price_date,
                "open": raw_row.open,
                "high": raw_row.high,
                "low": raw_row.low,
                "close": raw_row.close,
                "adj_close": raw_row.adj_close,
                "volume": raw_row.volume,
                "source": raw_row.source,
            }
            if existing is None:
                self.session.add(StockDailyPrice(**payload))
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
                self.session.add(existing)
            upserted += 1
        self.session.commit()
        return upserted


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(float(value))


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _infer_file_date(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None


def _read_daily_flat_file_rows(path: Path) -> list[dict[str, Any]]:
    with _open_text_file(path) as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Missing header row in {path.name}")
        return list(reader)


def _open_text_file(path: Path):
    if path.suffix == ".gz" or path.name.endswith(".csv.gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _validate_daily_row(row: dict[str, Any], *, row_number: int, manifest_id: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        events.append(_quality_event(manifest_id, row_number, "ERROR", "missing_ticker", "Missing ticker.", row))
        return None, events
    try:
        price_date = date.fromisoformat(str(row.get("price_date") or ""))
    except ValueError:
        events.append(_quality_event(manifest_id, row_number, "ERROR", "invalid_date", "Invalid price date.", row))
        return None, events

    open_value = _optional_float(row.get("open"))
    high_value = _optional_float(row.get("high"))
    low_value = _optional_float(row.get("low"))
    close_value = _optional_float(row.get("close"))
    adj_close_value = _optional_float(row.get("adj_close"))
    volume_value = _optional_int(row.get("volume"))

    numeric_values = {
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "adj_close": adj_close_value,
    }
    if any(value is not None and value < 0 for value in numeric_values.values()):
        events.append(_quality_event(manifest_id, row_number, "ERROR", "negative_price", "Negative price detected.", row))
        return None, events
    if high_value is not None and low_value is not None and high_value < low_value:
        events.append(_quality_event(manifest_id, row_number, "ERROR", "high_below_low", "High is below low.", row))
        return None, events
    if volume_value is not None and volume_value <= 0:
        events.append(_quality_event(manifest_id, row_number, "WARN", "non_positive_volume", "Volume is zero or negative.", row))

    normalized = {
        "row_number": row_number,
        "ticker": ticker,
        "price_date": price_date,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "adj_close": adj_close_value,
        "volume": volume_value,
        "source": str(row.get("source") or "sample"),
        "raw_row": row,
    }
    return normalized, events


def _quality_event(
    manifest_id: int,
    row_number: int,
    severity: str,
    issue_code: str,
    message: str,
    raw_row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_manifest_id": manifest_id,
        "row_number": row_number,
        "severity": severity,
        "issue_code": issue_code,
        "message": message,
        "raw_row": raw_row,
    }
