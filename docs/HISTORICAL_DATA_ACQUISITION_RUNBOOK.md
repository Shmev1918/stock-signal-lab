# Historical Data Acquisition Runbook

This is the operating guide for the one-time Polygon acquisition campaign.

It is intentionally short. The detailed planning lives in:

- [Historical Data Acquisition Campaign](HISTORICAL_DATA_ACQUISITION_CAMPAIGN.md)
- [Polygon Data Acquisition Plan](POLYGON_DATA_ACQUISITION_PLAN.md)
- [Data Provider Plan](DATA_PROVIDER_PLAN.md)
- [Options Research Plan](OPTIONS_RESEARCH_PLAN.md)
- [Roadmap](ROADMAP.md)

## Purpose

Use one paid Polygon / Massive month to acquire the historical dataset needed for Stock Signal Lab.

Do not buy the month until the acquisition infrastructure is green.

## Vendor Position

Primary vendor:

- Polygon / Massive

Why:

- one provider
- one auth system
- one schema
- flat files plus REST
- long-term support

Other providers remain secondary or future options, not the main acquisition path.

## Pre-Purchase Checklist

- [ ] Importer complete
- [ ] Checkpointing complete
- [ ] Resume complete
- [ ] Retry handling complete
- [ ] Raw payload storage complete
- [ ] Normalization complete
- [ ] Smoke tests pass
- [ ] Acquisition estimator complete
- [ ] Local storage sized for stock and options archives
- [ ] Backup strategy defined

Only after this checklist is green should the Polygon month begin.

## 30-Day Acquisition Plan

### Day 0

1. Buy one month.
2. Configure `POLYGON_API_KEY`.
3. Run the smoke test.
4. Create a tiny dry-run acquisition job.
5. Verify raw payloads, canonical rows, and reports.

### Days 1-30

1. Acquire continuously.
2. Prefer bulk/flat-file stock history where available.
3. Use REST for metadata, validation, incremental updates, and gap repair.
4. Keep options scope small.
5. Checkpoint after each stage.
6. Verify resume and retry behavior after every interruption.

### End of Month

1. Validate data completeness.
2. Back up PostgreSQL.
3. Export an archive.
4. Cancel or downgrade the subscription.

## Operational Commands

Smoke test:

```bash
python -m app.cli polygon-smoke-test --ticker AAPL
python -m app.cli polygon-smoke-test --ticker SPY
```

Create a dry-run acquisition job:

```bash
python -m app.cli acquisition create-job \
  --job-name polygon-dry-run \
  --provider polygon \
  --universe-name STOCK_RESEARCH_CORE \
  --years 1 \
  --include-prices \
  --include-fundamentals \
  --include-dividends \
  --include-splits \
  --no-include-options
```

Run a job:

```bash
python -m app.cli acquisition run-job <job_id>
```

Inspect job status:

```bash
python -m app.cli acquisition status <job_id>
```

Retry failures:

```bash
python -m app.cli acquisition retry-failed <job_id>
```

Estimate scope:

```bash
python -m app.cli acquisition estimate
```

## How Checkpointing Works

- completed tasks are preserved
- failed tasks remain visible
- retry resets failed tasks to pending
- reruns skip already completed work unless forced
- raw payloads remain stored even if normalization fails

## What QA Should Review

1. The acquisition plan itself.
2. The Polygon readiness layer.
3. The options research scope, which stays intentionally small.
4. The difference between a historical acquisition campaign and normal watchlist refresh.

## Guardrails

- Do not start the paid month before the pre-purchase checklist is green.
- Do not expand options to a full-market scope in v1.
- Do not let experimental imports bypass PostgreSQL.
- Do not discard raw provider payloads.
