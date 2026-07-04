from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from app.acquisition.flat_file_catalog import business_days_between, get_dataset_spec


@dataclass(frozen=True)
class FlatFileDescriptor:
    provider: str
    dataset: str
    market: str
    file_date: date
    remote_path: str
    local_path: str | None = None
    checksum: str | None = None
    compressed_size: int | None = None
    uncompressed_size: int | None = None


@runtime_checkable
class FlatFileProvider(Protocol):
    provider_name: str

    def list_available_files(
        self,
        dataset: str,
        *,
        start_date: date,
        end_date: date,
        market: str = "US",
    ) -> list[FlatFileDescriptor]: ...

    def estimate_download(
        self,
        dataset: str,
        *,
        start_date: date,
        end_date: date,
        market: str = "US",
    ) -> dict[str, Any]: ...

    def download(self, descriptor: FlatFileDescriptor, staging_dir: Path) -> Path: ...

    def verify(self, local_path: Path, checksum: str | None) -> bool: ...

    def stage(self, local_path: Path, staging_dir: Path) -> Path: ...

    def checkpoint(self, state: dict[str, Any]) -> dict[str, Any]: ...

    def resume(self, state: dict[str, Any]) -> dict[str, Any]: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PolygonFlatFileProvider:
    provider_name = "polygon"

    def __init__(
        self,
        *,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str = "https://files.massive.com",
        bucket_name: str = "flatfiles",
        region: str = "us-east-1",
        timeout_seconds: int = 60,
    ) -> None:
        self.access_key_id = access_key_id or os.getenv("POLYGON_FLAT_FILE_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_access_key = (
            secret_access_key
            or os.getenv("POLYGON_FLAT_FILE_SECRET_ACCESS_KEY")
            or os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        self.endpoint_url = endpoint_url.rstrip("/")
        self.bucket_name = bucket_name
        self.region = region
        self.timeout_seconds = timeout_seconds

    def list_available_files(
        self,
        dataset: str,
        *,
        start_date: date,
        end_date: date,
        market: str = "US",
    ) -> list[FlatFileDescriptor]:
        spec = get_dataset_spec(dataset)
        if spec.cadence != "daily":
            raise LookupError(f"Polygon flat-file dataset not supported yet: {dataset}")
        key_prefix = self._dataset_key_prefix(dataset)
        current = start_date
        descriptors: list[FlatFileDescriptor] = []
        while current <= end_date:
            if current.weekday() < 5:
                remote_path = f"{key_prefix}/{current:%Y/%m}/{current.isoformat()}.csv.gz"
                descriptors.append(
                    FlatFileDescriptor(
                        provider=self.provider_name,
                        dataset=dataset,
                        market=market.upper(),
                        file_date=current,
                        remote_path=remote_path,
                        compressed_size=int(spec.estimated_compressed_size_mb * 1024 * 1024),
                        uncompressed_size=int(spec.estimated_uncompressed_size_mb * 1024 * 1024),
                    )
                )
            current = current + timedelta(days=1)
        return descriptors

    def estimate_download(
        self,
        dataset: str,
        *,
        start_date: date,
        end_date: date,
        market: str = "US",
    ) -> dict[str, Any]:
        spec = get_dataset_spec(dataset)
        files = business_days_between(start_date, end_date) if spec.cadence == "daily" else 0
        compressed_bytes = int(files * spec.estimated_compressed_size_mb * 1024 * 1024)
        uncompressed_bytes = int(files * spec.estimated_uncompressed_size_mb * 1024 * 1024)
        return {
            "provider": self.provider_name,
            "dataset": dataset,
            "market": market.upper(),
            "files": files,
            "estimated_download_size_bytes": compressed_bytes,
            "estimated_uncompressed_size_bytes": uncompressed_bytes,
            "estimated_rows": files * spec.estimated_rows_per_file,
            "estimated_runtime_minutes": round(files * spec.estimated_runtime_seconds_per_file / 60.0, 1),
            "warning": "Polygon flat-file provider in phase 1 is planning-only; no network calls are made.",
        }

    def download(self, descriptor: FlatFileDescriptor, staging_dir: Path) -> Path:
        self._ensure_credentials()
        if descriptor.dataset != "stocks_daily":
            raise LookupError(f"Polygon flat-file download only supports stocks_daily in phase 1: {descriptor.dataset}")
        destination = staging_dir / "downloads" / descriptor.remote_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._download_object(descriptor.remote_path, destination)
        metadata = self._head_object(descriptor.remote_path)
        if metadata:
            destination.with_suffix(destination.suffix + ".meta.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return destination

    def verify(self, local_path: Path, checksum: str | None) -> bool:
        if checksum:
            return sha256_file(local_path) == checksum
        metadata_path = local_path.with_suffix(local_path.suffix + ".meta.json")
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            expected = metadata.get("checksum_sha256") or metadata.get("etag")
            if expected and "-" not in str(expected):
                return sha256_file(local_path) == str(expected).strip('"')
        return True

    def stage(self, local_path: Path, staging_dir: Path) -> Path:
        try:
            relative_path = local_path.relative_to(staging_dir / "downloads")
        except ValueError:
            relative_path = Path(local_path.name)
        destination = staging_dir / "staged" / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        return destination

    def checkpoint(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"provider": self.provider_name, "state": state}

    def resume(self, state: dict[str, Any]) -> dict[str, Any]:
        return state

    def _ensure_credentials(self) -> None:
        if not self.access_key_id or not self.secret_access_key:
            raise RuntimeError(
                "Polygon/Massive flat-file S3 credentials are not configured. "
                "Set POLYGON_FLAT_FILE_ACCESS_KEY_ID and POLYGON_FLAT_FILE_SECRET_ACCESS_KEY."
            )

    def _dataset_key_prefix(self, dataset: str) -> str:
        if dataset == "stocks_daily":
            return "us_stocks_sip/day_aggs_v1"
        raise LookupError(f"Polygon flat-file download only supports stocks_daily in phase 1: {dataset}")

    def _object_key(self, remote_path: str) -> str:
        return remote_path.lstrip("/")

    def _object_url(self, remote_path: str) -> str:
        key = self._object_key(remote_path)
        return f"{self.endpoint_url}/{self.bucket_name}/{quote(key)}"

    def _head_object(self, remote_path: str) -> dict[str, Any]:
        request = self._signed_request("HEAD", remote_path)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return {
                    "status": getattr(response, "status", 200),
                    "content_length": response.headers.get("Content-Length"),
                    "etag": response.headers.get("ETag"),
                    "checksum_sha256": response.headers.get("x-amz-checksum-sha256"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except HTTPError as exc:
            if exc.code in {401, 403, 404}:
                raise
            raise

    def _download_object(self, remote_path: str, destination: Path) -> None:
        request = self._signed_request("GET", remote_path)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response, destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
        except HTTPError:
            raise

    def _signed_request(self, method: str, remote_path: str) -> Request:
        parsed = urlsplit(self.endpoint_url)
        host = parsed.netloc
        amz_datetime = datetime.now(timezone.utc)
        amz_date = amz_datetime.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = amz_datetime.strftime("%Y%m%d")
        canonical_uri = f"/{self.bucket_name}/{self._object_key(remote_path)}"
        canonical_querystring = ""
        payload_hash = hashlib.sha256(b"").hexdigest()
        canonical_headers = (
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_querystring,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                algorithm,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._get_signature_key(self.secret_access_key or "", date_stamp, self.region, "s3")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization_header = (
            f"{algorithm} Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return Request(
            self._object_url(remote_path),
            method=method,
            headers={
                "Host": host,
                "X-Amz-Date": amz_date,
                "X-Amz-Content-Sha256": payload_hash,
                "Authorization": authorization_header,
                "Accept": "application/octet-stream",
            },
        )

    @staticmethod
    def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
        def _sign(message: str | bytes, signing_key: bytes) -> bytes:
            if isinstance(message, str):
                message = message.encode("utf-8")
            return hmac.new(signing_key, message, hashlib.sha256).digest()

        k_date = _sign(date_stamp, ("AWS4" + key).encode("utf-8"))
        k_region = _sign(region_name, k_date)
        k_service = _sign(service_name, k_region)
        return _sign("aws4_request", k_service)


class LocalFlatFileProvider:
    provider_name = "local"

    def __init__(self, source_root: str | Path) -> None:
        self.source_root = Path(source_root)

    def _dataset_dir(self, dataset: str, market: str) -> Path:
        return self.source_root / dataset / market.upper()

    def list_available_files(
        self,
        dataset: str,
        *,
        start_date: date,
        end_date: date,
        market: str = "US",
    ) -> list[FlatFileDescriptor]:
        spec = get_dataset_spec(dataset)
        if spec.cadence != "daily":
            raise LookupError(f"Local flat-file dataset not supported yet: {dataset}")
        base = self._dataset_dir(dataset, market)
        if not base.exists():
            return []
        descriptors: list[FlatFileDescriptor] = []
        for path in sorted(base.glob("*.csv")):
            try:
                file_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if file_date < start_date or file_date > end_date:
                continue
            relative = path.relative_to(self.source_root).as_posix()
            checksum = sha256_file(path)
            size = path.stat().st_size
            descriptors.append(
                FlatFileDescriptor(
                    provider=self.provider_name,
                    dataset=dataset,
                    market=market.upper(),
                    file_date=file_date,
                    remote_path=relative,
                    checksum=checksum,
                    compressed_size=size,
                    uncompressed_size=size,
                )
            )
        return descriptors

    def estimate_download(
        self,
        dataset: str,
        *,
        start_date: date,
        end_date: date,
        market: str = "US",
    ) -> dict[str, Any]:
        files = self.list_available_files(dataset, start_date=start_date, end_date=end_date, market=market)
        compressed_size = sum(item.compressed_size or 0 for item in files)
        return {
            "provider": self.provider_name,
            "dataset": dataset,
            "market": market.upper(),
            "files": len(files),
            "estimated_download_size_bytes": compressed_size,
            "estimated_uncompressed_size_bytes": compressed_size,
            "estimated_rows": len(files) * 3,
            "estimated_runtime_minutes": round(max(len(files), 1) * 0.05, 1),
            "warning": None,
        }

    def download(self, descriptor: FlatFileDescriptor, staging_dir: Path) -> Path:
        source_path = self.source_root / descriptor.remote_path
        if not source_path.exists():
            raise FileNotFoundError(f"Flat-file source not found: {source_path}")
        destination = staging_dir / "downloads" / descriptor.remote_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return destination

    def verify(self, local_path: Path, checksum: str | None) -> bool:
        if checksum is None:
            return True
        return sha256_file(local_path) == checksum

    def stage(self, local_path: Path, staging_dir: Path) -> Path:
        try:
            relative_path = local_path.relative_to(staging_dir / "downloads")
        except ValueError:
            relative_path = Path(local_path.name)
        destination = staging_dir / "staged" / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        return destination

    def checkpoint(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"provider": self.provider_name, "state": state}

    def resume(self, state: dict[str, Any]) -> dict[str, Any]:
        return state
