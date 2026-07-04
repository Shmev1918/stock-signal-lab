# Polygon Stock Campaign Plan

This document is the operational plan for the stock-only Polygon / Massive acquisition campaign.

It answers the question: how does Polygon data get into PostgreSQL?

## Default Posture

- dry-run by default
- live execution requires `--live`
- live execution requires caps
- no bulk flat-file downloads unless valid Massive S3 credentials exist
- no options in this phase

## Campaign Phases

### Phase 0 - Readiness Report

Check local environment readiness without calling Polygon:

- database connectivity
- Alembic head/current status
- raw payload storage helpers
- provider call logging table
- checkpoint table
- normalization path
- Polygon key presence
- rate limit configuration
- live guardrails
- documentation / validation markers

### Phase 1 - `stocks_daily` Flat Files

Bulk historical stock bars come from Massive flat files:

1. Download the file to staging.
2. Verify checksum when available.
3. Store the file in a local staging directory.
4. Load the file into `raw_polygon_stock_daily_bars`.
5. Normalize raw rows into `stock_daily_prices`.
6. Upsert `securities`.
7. Preserve raw payload evidence in the manifest and quality tables.

Flat-file files follow the documented path structure:

`us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz`

The current runner blocks this phase until Massive S3 credentials are available.

### Phase 2 - Corporate Actions REST

Use Polygon REST for:

- dividends
- splits

Flow:

1. Call the Polygon endpoint.
2. Record provider call metadata.
3. Store raw JSON payloads first.
4. Normalize into canonical dividend and split tables.
5. Audit task outcomes and failures.

### Phase 3 - Security Reference REST

Use Polygon REST for ticker and security metadata.

Flow:

1. Call Polygon reference endpoints.
2. Store raw payloads.
3. Normalize to security/reference rows.
4. Update first/last seen dates.

### Phase 4 - Financial Statements REST

Use Polygon REST for financial statement and fundamentals coverage.

Flow:

1. Call fundamentals / financial statement endpoints.
2. Store raw payloads.
3. Normalize into canonical fundamentals tables.
4. Mark partial data clearly when only some fields exist.

### Phase 5 - Earnings / Ratios REST

This phase is planned but not yet wired into the runner.

The runner keeps it visible so the acquisition roadmap stays explicit.

## Database Landing Path

The canonical path is:

External provider
→ raw payload / staging
→ landing tables
→ canonical tables in PostgreSQL

For stock daily bars:

`flat file -> staging -> raw_polygon_stock_daily_bars -> stock_daily_prices -> securities`

For REST data:

`Polygon REST -> provider call log / raw payloads -> canonical tables`

## Live Guardrails

The live campaign runner must require:

- `--live`
- `--max-flat-files`
- `--max-rest-requests`
- start and end dates

The runner prints an audit after each phase.

## Operational Commands

Dry-run:

```bash
python -m app.cli acquisition campaign plan \
  --config configs/stock_historical_campaign.yml
```

Live:

```bash
python -m app.cli acquisition campaign run \
  --config configs/stock_historical_campaign.yml \
  --phase 1 \
  --live \
  --max-files 5000 \
  --max-bytes 1000000000 \
  --min-free-bytes 1649267441664
```

The default `--min-free-bytes` threshold is 1.5 TiB. Lower it only if you understand the disk risk.

## Full Download Strategy

The stock-only acquisition campaign should be run in this order:

1. readiness
2. flat-file stock archive
3. corporate actions REST
4. security reference REST
5. financial statements REST
6. earnings / ratios REST when the importer is ready

Use `campaign status` and `campaign audit` to inspect the persisted campaign state:

```bash
python -m app.cli acquisition campaign status --campaign-id <id>
python -m app.cli acquisition campaign audit --campaign-id <id>
```

That sequence keeps the archive reproducible and reduces request pressure.
