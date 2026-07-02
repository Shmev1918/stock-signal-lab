# Historical Data Acquisition Campaign

Version 1.0

## Mission

Acquire the highest-quality historical financial dataset practical for Stock Signal Lab.

This is expected to be a one-time or very infrequent acquisition campaign.

The objective is to build our own research database.

The objective is not to maintain a permanent expensive subscription.

## End State

At the conclusion of this campaign we own:

- Historical stock prices
- Historical fundamentals
- Financial statements
- Corporate actions
- Dividends
- Splits
- Reference metadata
- Historical options research data

stored inside PostgreSQL.

From that point forward:

- Only new market data is acquired.
- Historical experiments should never require downloading history again.

## Provider

Primary provider:

- Polygon / Massive

Reason:

- Single provider
- Single authentication system
- Single schema
- Long-term support
- Excellent documentation
- Flat file support
- REST support
- Broad market coverage

## Why Polygon

Other providers can provide pieces.

Polygon provides the cleanest long-term architecture.

Engineering simplicity has value.

Maintaining one provider is preferable to maintaining five.

## Subscription Strategy

Do not purchase until:

- importer complete
- checkpointing complete
- resume complete
- retries complete
- raw payload storage complete
- normalization complete
- smoke tests pass
- acquisition estimator complete

Then:

1. Purchase one month.
2. Treat the month as a data acquisition campaign.

## Acquisition Campaign Checklist

- [ ] Infrastructure complete
- [ ] Smoke tests pass
- [ ] Resume verified
- [ ] Checkpoint verified
- [ ] Storage verified
- [ ] Backup configured
- [ ] Polygon subscription purchased

Then:

1. Acquire continuously for 30 days.
2. Validate.
3. Backup database.
4. Export archive.
5. Cancel or downgrade subscription.

## Historical Data Targets

### Stocks

Target:

- Entire U.S. equity market if practical

Minimum acceptable:

- S&P 500

Preferred:

- Russell 1000

Ideal:

- Entire available U.S. market

Acquire:

- daily OHLCV
- adjusted prices
- corporate actions
- dividends
- splits
- financial statements
- ratios
- earnings
- ticker metadata
- news metadata if available

Target history:

- Maximum historical depth available under plan

### Options

Historical options are significantly larger.

The objective is not every option contract ever created.

Instead:

- acquire a research-quality options archive

Priority universe:

- SPY
- QQQ
- AAPL
- MSFT
- NVDA
- AMZN
- META
- GOOGL
- TSLA
- IWM

Acquire:

- contract metadata
- historical trades
- historical quotes
- daily aggregates
- open interest
- implied volatility
- Greeks when available

Store daily chain snapshots going forward.

Expand the universe over time.

## Acquisition Order

Every ticker:

1. Reference metadata
2. Historical prices
3. Corporate actions
4. Splits
5. Dividends
6. Financial statements
7. Ratios
8. Earnings
9. Options
10. Complete

Checkpoint after every stage.

## REST vs Flat Files

Flat files:

- bulk historical imports

REST:

- metadata
- validation
- incremental updates
- gap repair

Hybrid approach preferred.

## Data Pipeline

External provider
-> raw landing tables
-> canonical tables
-> signals
-> experiments
-> machine learning
-> predictions

## Raw Payload Policy

Every provider payload is stored.

Normalization never destroys source data.

Reason:

- future-proofing
- reproducibility
- debugging

## Machine Learning

ML consumes only PostgreSQL.

Never Polygon.

Never REST.

Never flat files.

Internet access should not be required for historical experiments.

## Estimated Storage

Stocks:

- 20-50 GB

Signals:

- 10-20 GB

Features:

- 5-15 GB

Experiments:

- less than 5 GB

Options:

- variable
- expect tens to hundreds of GB depending on scope

Storage is intentionally over-provisioned.

Storage is inexpensive.

Historical data is not.

## Timeline

Infrastructure:

- current focus

Paid month:

- historical acquisition

Future:

- nightly updates only

## Success Criteria

We consider the acquisition campaign successful when:

- Historical imports complete.
- Resume works.
- No duplicate data.
- Canonical schema validated.
- Experiments run entirely from PostgreSQL.
- ML trains entirely from PostgreSQL.
- Future daily updates become incremental only.

## Long-Term Philosophy

The codebase is replaceable.

The models are replaceable.

The UI is replaceable.

The historical research database is not.

The historical database is the primary asset of Stock Signal Lab.
