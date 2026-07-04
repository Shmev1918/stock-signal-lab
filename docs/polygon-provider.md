# Polygon Provider Notes

This document describes the current Polygon / Massive integration for Stock Signal Lab.

It is intentionally conservative.

## Scope

Polygon is used only by acquisition and provider code.

- experiments do not call Polygon
- ML does not call Polygon
- UI does not call Polygon

Historical research should be normalized into PostgreSQL first.

## Rate Limit Policy

- default: 3 requests per minute
- configurable via `POLYGON_RATE_LIMIT_PER_MINUTE`
- every Polygon REST call goes through the provider limiter
- requests are logged with endpoint, HTTP status, elapsed time, and whether the request was rate-limited

## Safe Smoke Test

Use the CLI smoke test for a tiny endpoint check:

```bash
python -m app.cli polygon smoke-test --ticker AAPL
python -m app.cli polygon smoke-test --ticker SPY
```

The smoke test only checks a small, safe set:

- AAPL daily aggregates
- SPY daily aggregates
- AAPL ticker details
- AAPL dividends
- AAPL splits
- SPY options snapshot if available

## Current Free-Tier Results

Observed free-tier behavior in this repo:

- daily aggregates: PASS
- ticker details: PASS
- dividends: PASS after using `/stocks/v1/dividends`
- splits: PASS after using `/stocks/v1/splits`
- options snapshot: may be plan restricted on the free tier

Plan-restricted endpoints are classified separately from endpoint bugs.

## Smoke Result Classification

Smoke results are reported as:

- PASS
- FAIL
- FORBIDDEN
- BAD_REQUEST
- SKIPPED

Each check also includes a cause:

- OK
- PLAN_RESTRICTED
- ENDPOINT_REQUEST_MISMATCH
- INVALID_KEY
- RATE_LIMITED
- NO_DATA
- UNKNOWN

## Dry-Run Acquisition

Before any live Polygon acquisition job can run, the system requires:

- `--live`
- `--max-requests`
- `--start-date`
- `--end-date`
- a positive configured rate limit
- an estimated request count that does not exceed the limit

That estimate is printed in the acquisition response before the job executes.

## REST vs Flat Files

Use REST for:

- metadata
- smoke testing
- validation
- incremental updates
- gap repair

Use flat files for:

- bulk historical imports
- large stock backfills
- high-volume options research data

Bulk historical acquisition should prefer flat files, not REST.

## Known Failures

- options snapshot may be forbidden on the current plan
- if an endpoint returns `BAD_REQUEST`, the request construction should be inspected before retrying
- if a response is `FORBIDDEN`, it is likely a plan access issue rather than a code bug

## Secrets

The API key must live in `.env` and remain uncommitted.
