from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class FlatFileDatasetSpec:
    dataset: str
    description: str
    cadence: str
    estimated_rows_per_file: int
    estimated_compressed_size_mb: float
    estimated_uncompressed_size_mb: float
    estimated_runtime_seconds_per_file: float


DATASET_SPECS: dict[str, FlatFileDatasetSpec] = {
    "stocks_daily": FlatFileDatasetSpec(
        dataset="stocks_daily",
        description="Daily stock bars archive",
        cadence="daily",
        estimated_rows_per_file=8_000,
        estimated_compressed_size_mb=18.0,
        estimated_uncompressed_size_mb=110.0,
        estimated_runtime_seconds_per_file=2.5,
    ),
    "options_daily": FlatFileDatasetSpec(
        dataset="options_daily",
        description="Daily options research archive",
        cadence="daily",
        estimated_rows_per_file=50_000,
        estimated_compressed_size_mb=120.0,
        estimated_uncompressed_size_mb=650.0,
        estimated_runtime_seconds_per_file=3.5,
    ),
}


def get_dataset_spec(dataset: str) -> FlatFileDatasetSpec:
    try:
        return DATASET_SPECS[dataset]
    except KeyError as exc:  # pragma: no cover - defensive catalog access
        raise LookupError(f"Unknown flat-file dataset: {dataset}") from exc


def business_days_between(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        return 0
    total = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            total += 1
        current += timedelta(days=1)
    return total
