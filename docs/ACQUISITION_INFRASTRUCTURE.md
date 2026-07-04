# Acquisition Infrastructure

This document describes the readiness layer for a future Polygon/Massive acquisition campaign.

The goal is not to import a large archive yet.
The goal is to make the archive campaign safe, resumable, and inspectable before money is spent.

## What This Layer Does

- creates acquisition jobs
- builds tasks from a research universe
- rate-limits provider calls
- stores raw provider payloads first
- normalizes supported payloads into canonical tables
- checkpoints task state in Postgres
- resumes safely after interruption
- records provider call metadata
- reports progress and failures

## What It Is Not

- not the normal watchlist refresh workflow
- not the scoring engine
- not the experiment engine
- not ML
- not a frontend feature

Only acquisition code should call external market-data providers.
Everything else should read from Postgres.

## Polygon Smoke Test

Use the CLI to check whether the Polygon API key and the most important endpoints are reachable:

```bash
python -m app.cli polygon-smoke-test --ticker AAPL
```

The smoke test reports:

- whether an API key was detected
- daily aggregates for the requested ticker
- daily aggregates for SPY
- ticker details
- dividends
- splits
- SPY options chain snapshot if accessible

The smoke test should be run before any paid acquisition campaign.

## Readiness Report

Use the readiness report to inspect the local acquisition environment without calling Polygon:

```bash
python -m app.cli acquisition readiness-report
```

Add `--json` for automation and `--strict` if you want a nonzero exit code when any check is WARN or FAIL.

### From Host

Run the command from your shell when you want to validate how the host environment sees the database URL.

If the configured database hostname is Docker-only, the report may show DNS or TCP failures on the host even when the stack is healthy inside containers.

### From Docker

Run the command inside the application container when you want to validate container-to-container connectivity:

```bash
docker compose exec app python -m app.cli acquisition readiness-report
```

This is the correct view when the database hostname is only resolvable inside Docker networking.

## Stock Campaign Runner

The stock-only campaign runner is documented in:

- [Polygon Stock Campaign Plan](POLYGON_STOCK_CAMPAIGN_PLAN.md)

The runner keeps the full acquisition order explicit:

1. readiness report
2. `stocks_daily` flat files
3. corporate actions REST
4. security reference REST
5. financial statements REST
6. earnings / ratios REST when implemented

Dry-run is the default. Live execution requires caps and stays blocked until the Massive S3 flat-file credentials exist.

## Create a Dry-Run Acquisition Job

Creating a job does not start provider calls.
It only creates the job record and tasks.

Example:

```bash
python -m app.cli acquisition create-job \
  --job-name polygon_core \
  --provider polygon \
  --universe-name STOCK_RESEARCH_CORE
```

Use `GET /acquisition/jobs/{id}` or `python -m app.cli acquisition status <id>` to inspect the task plan before running it.

## Run, Pause, Resume, Retry

```bash
python -m app.cli acquisition run-job <id>
python -m app.cli acquisition pause <id>
python -m app.cli acquisition resume <id>
python -m app.cli acquisition retry-failed <id>
```

Checkpoint behavior:

- completed tasks are left alone
- pending tasks continue
- failed tasks stay failed until retried
- forced runs can reprocess completed tasks when explicitly requested

## Why Raw Payloads Are Stored

The raw provider response is the evidence layer.
It is stored before normalization so that:

- failed normalization does not lose the original payload
- later parsing changes can be replayed
- provider behavior can be audited
- data provenance remains visible

## Why Paid Acquisition Waits

Do not start a paid Polygon/Massive month until all of this is green:

- smoke test passes
- acquisition job creation works
- checkpoint/resume works
- raw payload storage works
- canonical normalization works
- API and CLI reports are useful
- estimator output is believable
- tests pass

If this layer is not stable, a paid month will mostly buy uncertainty.
