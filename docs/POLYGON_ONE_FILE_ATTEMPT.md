# Polygon One-File Attempt

This run was limited to researching and wiring the one-file Polygon/Massive flat-file path for `stocks_daily`.

## Verified directory structure

The official Massive flat-file docs show the stocks day-aggregate dataset under:

```text
us_stocks_sip/day_aggs_v1
```

Daily files are published in a year/month/day layout:

```text
us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz
```

Example from the docs:

```text
us_stocks_sip/day_aggs_v1/2026/06/2026-06-25.csv.gz
```

## Authentication model

The flat-file quickstart requires:

- an active Massive subscription with flat-file access
- an S3 Access Key ID
- an S3 Secret Access Key
- endpoint: `https://files.massive.com`
- bucket: `flatfiles`

The local repository `.env` only contains the Polygon REST API key. It does **not** contain flat-file S3 credentials.

## What was implemented

- `PolygonFlatFileProvider` now knows the real `stocks_daily` S3 key layout.
- The downloader uses S3 SigV4 signing against `https://files.massive.com/flatfiles/...`.
- Download verification supports checksum metadata when available.
- Staging still routes through the existing acquisition pipeline.

## Attempt outcome

Attempted file:

```text
us_stocks_sip/day_aggs_v1/2026/06/2026-06-25.csv.gz
```

The attempt stopped before any network call because the required S3 credentials were not configured locally.

Observed block:

```text
RuntimeError: Polygon/Massive flat-file S3 credentials are not configured. Set POLYGON_FLAT_FILE_ACCESS_KEY_ID and POLYGON_FLAT_FILE_SECRET_ACCESS_KEY.
```

## Assumptions

- `stocks_daily` maps to the Massive stocks day aggregates dataset.
- The bucket path is path-style S3 under `files.massive.com/flatfiles/...`.
- `us-east-1` is a reasonable default signing region for the S3-compatible endpoint.
- No retries beyond a single attempt were used.
- No historical backfill was attempted.
- No options data was requested.

## Current stop point

Flat-file access is blocked at credential provisioning, not at importer logic.

To proceed, the environment needs the Massive S3 access key pair from the Massive dashboard.
