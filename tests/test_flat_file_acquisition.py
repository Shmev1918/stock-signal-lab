from __future__ import annotations

from datetime import date
import gzip
from pathlib import Path

from sqlmodel import Session, select

from app.acquisition.flat_files import FlatFileImportService, estimate_flat_file_plan
from app.acquisition.reports import inspect_flat_file_manifest, list_flat_file_manifests
from app.db.models import DailyPrice, FlatFileManifest, FlatFileQualityEvent, RawPolygonStockDailyBar, Security, StockDailyPrice
from app.db.session import engine
from app.providers.flat_file_provider import LocalFlatFileProvider


SAMPLE_ROOT = Path(__file__).parent / "data" / "flat_files" / "sample"


def _make_service(session: Session, tmp_path: Path) -> FlatFileImportService:
    provider = LocalFlatFileProvider(SAMPLE_ROOT)
    staging_dir = tmp_path / "staging"
    return FlatFileImportService(session, provider, staging_dir)


def test_flat_file_manifest_creation_and_resume(tmp_path) -> None:
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        report = service.run("stocks_daily", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        assert report["files_total"] == 2
        assert report["files_downloaded"] == 2
        assert report["files_ingested"] == 2
        assert report["files_normalized"] == 2

        manifests = list(session.exec(select(FlatFileManifest).order_by(FlatFileManifest.file_date)))
        assert len(manifests) == 2
        assert all(manifest.normalize_status == "COMPLETED" for manifest in manifests)
        prices = list(session.exec(select(DailyPrice).where(DailyPrice.source == "sample_flat_file")))
        assert len(prices) == 6

        resume = service.resume("stocks_daily", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        assert resume["files_skipped"] == 2
        assert resume["files_failed"] == 0
        manifests_after = list(session.exec(select(FlatFileManifest)))
        assert len(manifests_after) == 2


def test_duplicate_detection_does_not_create_duplicate_manifests(tmp_path) -> None:
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        descriptors = service.provider.list_available_files(
            "stocks_daily",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        first = service.ensure_manifests(descriptors)
        second = service.ensure_manifests(descriptors)
        assert len(first) == 2
        assert len(second) == 2
        manifests = list(session.exec(select(FlatFileManifest)))
        assert len(manifests) == 2


def test_checksum_mismatch_records_failure(tmp_path) -> None:
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        sample_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2024-01-02.csv"
        service.import_stock_daily_file(
            sample_file,
            provider="sample",
            dataset="stocks_daily",
        )
        manifest = session.exec(select(FlatFileManifest).where(FlatFileManifest.remote_path == sample_file.as_posix())).first()
        assert manifest is not None
        assert manifest.normalize_status == "COMPLETED"

        try:
            service.import_stock_daily_file(
                sample_file,
                provider="sample",
                dataset="stocks_daily",
                expected_checksum="bad-checksum",
                force=True,
            )
        except ValueError as exc:
            assert "Checksum mismatch" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("Expected checksum mismatch to block import")

        manifest_row = session.exec(
            select(FlatFileManifest).where(FlatFileManifest.remote_path == sample_file.as_posix())
        ).first()
        assert manifest_row is not None
        assert manifest_row.normalize_status == "COMPLETED"


def test_import_flat_file_successful_raw_load_and_canonical_normalization(tmp_path) -> None:
    sample_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2024-01-02.csv"
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        result = service.import_stock_daily_file(
            sample_file,
            provider="sample",
            dataset="stocks_daily",
            market="US",
        )
        assert result["row_count"] == 3
        assert result["raw_inserted_count"] == 3
        assert result["canonical_upsert_count"] == 3
        assert result["quality_events_created"] == 0

        manifest = session.exec(select(FlatFileManifest).where(FlatFileManifest.remote_path == sample_file.as_posix())).first()
        assert manifest is not None
        assert manifest.normalize_status == "COMPLETED"

        raw_rows = list(session.exec(select(RawPolygonStockDailyBar).where(RawPolygonStockDailyBar.source_manifest_id == manifest.id)))
        canonical_rows = list(session.exec(select(StockDailyPrice).where(StockDailyPrice.source_manifest_id == manifest.id)))
        securities = list(session.exec(select(Security).order_by(Security.symbol)))
        assert len(raw_rows) == 3
        assert len(canonical_rows) == 3
        assert len(securities) == 3
        assert all(row.security_id is not None for row in canonical_rows)
        aapl_security = session.exec(select(Security).where(Security.provider == "sample", Security.symbol == "AAPL")).first()
        assert aapl_security is not None
        assert aapl_security.first_seen_date == date(2024, 1, 2)
        assert aapl_security.last_seen_date == date(2024, 1, 2)
        for row in canonical_rows:
            security = session.get(Security, row.security_id or 0)
            assert security is not None
            assert security.symbol == row.symbol
            assert security.provider == "sample"


def test_duplicate_rerun_does_not_duplicate(tmp_path) -> None:
    sample_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2024-01-02.csv"
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        first = service.import_stock_daily_file(sample_file, provider="sample", dataset="stocks_daily")
        second = service.import_stock_daily_file(sample_file, provider="sample", dataset="stocks_daily", force=True)
        manifest = session.exec(select(FlatFileManifest).where(FlatFileManifest.remote_path == sample_file.as_posix())).first()
        assert manifest is not None
        raw_rows = list(session.exec(select(RawPolygonStockDailyBar).where(RawPolygonStockDailyBar.source_manifest_id == manifest.id)))
        canonical_rows = list(session.exec(select(StockDailyPrice).where(StockDailyPrice.source_manifest_id == manifest.id)))
        securities = list(session.exec(select(Security)))
        assert first["raw_inserted_count"] == 3
        assert second["raw_inserted_count"] == 3
        assert len(raw_rows) == 3
        assert len(canonical_rows) == 3
        assert len(securities) == 3


def test_new_ticker_updates_security_seen_dates(tmp_path) -> None:
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        first_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2024-01-02.csv"
        second_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2026-01-05.csv"

        service.import_stock_daily_file(first_file, provider="sample", dataset="stocks_daily")
        service.import_stock_daily_file(second_file, provider="sample", dataset="stocks_daily")

        securities = list(session.exec(select(Security).order_by(Security.symbol)))
        assert len(securities) == 4

        aapl_security = session.exec(select(Security).where(Security.provider == "sample", Security.symbol == "AAPL")).first()
        assert aapl_security is not None
        assert aapl_security.first_seen_date == date(2024, 1, 2)
        assert aapl_security.last_seen_date == date(2026, 1, 5)

        nvda_security = session.exec(select(Security).where(Security.provider == "sample", Security.symbol == "NVDA")).first()
        assert nvda_security is not None
        assert nvda_security.first_seen_date == date(2026, 1, 5)
        assert nvda_security.last_seen_date == date(2026, 1, 5)


def test_inspect_flat_file_clean_file(tmp_path) -> None:
    sample_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2024-01-02.csv"
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        service.import_stock_daily_file(sample_file, provider="sample", dataset="stocks_daily")
        manifest = session.exec(select(FlatFileManifest).where(FlatFileManifest.remote_path == sample_file.as_posix())).first()
        assert manifest is not None

        report = inspect_flat_file_manifest(session, manifest.id or 0)
        assert report["manifest_status"] == "COMPLETED"
        assert report["checksum_status"] == "MATCH"
        assert report["raw_row_count"] == 3
        assert report["canonical_row_count"] == 3
        assert report["quality_events_count"] == 0
        assert report["warning_count"] == 0
        assert report["error_count"] == 0
        assert report["securities_created"] == 3
        assert report["securities_updated"] == 0
        assert report["duplicate_rows_skipped"] == 0


def test_inspect_flat_file_with_warnings(tmp_path) -> None:
    warning_path = tmp_path / "warning.csv"
    warning_path.write_text(
        "\n".join(
            [
                "ticker,price_date,open,high,low,close,adj_close,volume,source",
                "AAPL,2024-01-02,185.0,187.0,184.5,186.3,186.3,80000000,sample_flat_file",
                "MSFT,2024-01-02,370.0,373.0,368.8,372.1,372.1,0,sample_flat_file",
            ]
        ),
        encoding="utf-8",
    )
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        service.import_stock_daily_file(warning_path, provider="sample", dataset="stocks_daily")
        manifest = session.exec(select(FlatFileManifest).where(FlatFileManifest.remote_path == warning_path.as_posix())).first()
        assert manifest is not None

        report = inspect_flat_file_manifest(session, manifest.id or 0)
        assert report["warning_count"] == 1
        assert report["error_count"] == 0
        assert report["quality_events_count"] == 1
        assert report["manifest_status"] == "COMPLETED"
        assert report["sample_quality_events"][0]["issue_code"] == "non_positive_volume"


def test_inspect_flat_file_with_errors(tmp_path) -> None:
    error_path = tmp_path / "error.csv"
    error_path.write_text(
        "\n".join(
            [
                "ticker,price_date,open,high,low,close,adj_close,volume,source",
                ",2024-01-02,185.0,187.0,184.5,186.3,186.3,80000000,sample_flat_file",
                "SPY,2024-13-02,470.0,472.5,468.9,471.8,471.8,65000000,sample_flat_file",
            ]
        ),
        encoding="utf-8",
    )
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        service.import_stock_daily_file(error_path, provider="sample", dataset="stocks_daily")
        manifest = session.exec(select(FlatFileManifest).where(FlatFileManifest.remote_path == error_path.as_posix())).first()
        assert manifest is not None

        report = inspect_flat_file_manifest(session, manifest.id or 0)
        assert report["error_count"] >= 1
        assert report["quality_events_count"] >= 1
        assert report["manifest_status"] == "FAILED"


def test_list_flat_files_returns_manifests(tmp_path) -> None:
    sample_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2024-01-02.csv"
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        service.import_stock_daily_file(sample_file, provider="sample", dataset="stocks_daily")
        manifests = list_flat_file_manifests(session, provider="sample", dataset="stocks_daily")
        assert len(manifests) == 1
        assert manifests[0]["provider"] == "sample"
        assert manifests[0]["dataset"] == "stocks_daily"


def test_import_gzipped_flat_file_success(tmp_path) -> None:
    sample_file = SAMPLE_ROOT / "stocks_daily" / "US" / "2024-01-02.csv"
    gz_path = tmp_path / "2026-06-25.csv.gz"
    gz_path.write_bytes(gzip.compress(sample_file.read_bytes()))
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        result = service.import_stock_daily_file(gz_path, provider="polygon", dataset="stocks_daily")
        assert result["row_count"] == 3
        assert result["raw_inserted_count"] == 3
        assert result["canonical_upsert_count"] == 3


def test_malformed_row_creates_quality_event(tmp_path) -> None:
    malformed_path = tmp_path / "malformed.csv"
    malformed_path.write_text(
        "\n".join(
            [
                "ticker,price_date,open,high,low,close,adj_close,volume,source",
                "AAPL,2024-01-02,185.0,187.0,184.5,186.3,186.3,80000000,sample_flat_file",
                ",2024-01-02,370.0,373.0,368.8,372.1,372.1,45000000,sample_flat_file",
                "SPY,2024-01-02,470.0,472.5,468.9,471.8,471.8,0,sample_flat_file",
            ]
        ),
        encoding="utf-8",
    )
    with Session(engine) as session:
        service = _make_service(session, tmp_path)
        result = service.import_stock_daily_file(malformed_path, provider="sample", dataset="stocks_daily")
        manifest = session.exec(select(FlatFileManifest).where(FlatFileManifest.remote_path == malformed_path.as_posix())).first()
        assert manifest is not None
        events = list(session.exec(select(FlatFileQualityEvent).where(FlatFileQualityEvent.source_manifest_id == manifest.id)))
        assert len(events) == 2
        assert result["quality_events_created"] == 2
        assert any(event.issue_code == "missing_ticker" for event in events)
        assert any(event.issue_code == "non_positive_volume" for event in events)
        raw_rows = list(session.exec(select(RawPolygonStockDailyBar).where(RawPolygonStockDailyBar.source_manifest_id == manifest.id)))
        canonical_rows = list(session.exec(select(StockDailyPrice).where(StockDailyPrice.source_manifest_id == manifest.id)))
        assert len(raw_rows) == 2
        assert len(canonical_rows) == 2


def test_dry_run_estimates() -> None:
    plan = estimate_flat_file_plan(
        provider="polygon",
        dataset="stocks_daily",
        market="US",
        start_date=date(1995, 1, 1),
        end_date=date(1995, 1, 31),
    )
    assert plan["estimated_files"] > 0
    assert plan["estimated_download_size_mb"] > 0
    assert plan["estimated_postgresql_rows"] > 0
    assert plan["estimated_disk_usage_gb"] > 0
    assert plan["estimated_runtime_minutes"] > 0
