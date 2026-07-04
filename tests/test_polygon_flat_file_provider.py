from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.providers.flat_file_provider import FlatFileDescriptor, PolygonFlatFileProvider


def test_polygon_flat_file_paths_match_docs() -> None:
    provider = PolygonFlatFileProvider(access_key_id="dummy", secret_access_key="dummy")
    descriptors = provider.list_available_files(
        "stocks_daily",
        start_date=date(2026, 6, 24),
        end_date=date(2026, 6, 26),
    )
    assert [item.remote_path for item in descriptors] == [
        "us_stocks_sip/day_aggs_v1/2026/06/2026-06-24.csv.gz",
        "us_stocks_sip/day_aggs_v1/2026/06/2026-06-25.csv.gz",
        "us_stocks_sip/day_aggs_v1/2026/06/2026-06-26.csv.gz",
    ]


def test_polygon_download_blocks_without_s3_credentials(tmp_path: Path) -> None:
    provider = PolygonFlatFileProvider()
    descriptor = FlatFileDescriptor(
        provider="polygon",
        dataset="stocks_daily",
        market="US",
        file_date=date(2026, 6, 25),
        remote_path="us_stocks_sip/day_aggs_v1/2026/06/2026-06-25.csv.gz",
    )
    with pytest.raises(RuntimeError, match="flat-file S3 credentials are not configured"):
        provider.download(descriptor, tmp_path)
