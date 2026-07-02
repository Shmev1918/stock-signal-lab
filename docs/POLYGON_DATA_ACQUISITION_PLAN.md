# Polygon/Massive Data Acquisition Plan

## Executive Summary

Recommendation: **yes for stocks, limited for options**.

One paid month of Polygon/Massive is realistic for building a substantial local stock archive in PostgreSQL if we use the bulk/flat-file path first and keep REST for metadata and gaps. It is **not** a clean one-month path to a full historical options-chain archive across the market. Options are practical only for a narrow research universe.

The right acquisition posture is:

1. Use flat files for bulk historical stock data.
2. Use REST for reference data, fundamentals, corporate actions, and targeted gap-filling.
3. Use options data only for a small underlying universe unless later evidence justifies a larger archive.

## What the Official Docs Suggest

### Stocks

Official docs show:

- Flat files are compressed CSVs designed for bulk historical research and backtesting.
- Stock flat files include daily aggregates, historical trades, and historical quotes.
- Stock flat files are unadjusted by default; adjusted prices require REST `adjusted=true` or manual split adjustment.
- Stock REST includes dividends, splits, ticker metadata, financial statements, ratios, news, and market/reference endpoints.
- The pricing page advertises a paid stock tier with unlimited API calls and 10 years of historical data.
- Free REST access is rate-limited.

### Options

Official docs show:

- Options flat files exist for historical trades, quotes, and aggregated market data.
- Options REST includes contract reference metadata, current chain snapshots, contract snapshots, quotes, trades, and aggregates.
- The chain snapshot endpoint is a current snapshot, not a documented historical chain archive.
- Options quotes and trades have plan-dependent historical depth.
- Options are materially larger and more fragmented than stocks.

## Official Answer to the Core Question

### Stocks

**Yes.** One paid month is enough to acquire a useful stock archive for a local research platform, especially if we focus on daily bars, corporate actions, reference metadata, and a representative stock universe.

### Options

**Limited.** One paid month is enough for a small, deliberate options research core, but not enough for a comfortable full-market historical options archive with complete chain reconstruction unless the scope is narrow and the ingestion workflow is already built and tested.

## Acquisition Strategy Comparison

### 1. REST API Ingestion

Best for:

- reference metadata
- dividends and splits
- financial statements and ratios
- targeted gap-filling
- smoke testing and validation

Pros:

- straightforward to implement
- easy to filter by ticker and date
- good for small incremental syncs

Cons:

- too slow for large bulk archives
- rate limits still matter
- expensive in request count compared with bulk files

### 2. Flat File Ingestion

Best for:

- bulk historical stock archives
- bulk historical options archives
- reproducible backfills
- offline retries and resumability

Pros:

- fastest way to move large historical volumes
- better for one-month campaign
- fewer API calls
- easier to checkpoint by file/date partition

Cons:

- more importer work upfront
- needs careful normalization
- large download/storage volume

### 3. Hybrid Ingestion

Best for:

- the actual v1 acquisition plan

Recommended pattern:

- flat files for bulk historical bars/trades/quotes
- REST for ticker metadata, corporate actions, fundamentals, ratios, and validation
- REST or targeted file pulls for gaps

Pros:

- fastest path to a durable archive
- better resilience
- less dependence on request limits

Cons:

- slightly more complex than REST-only
- requires a canonical schema and checkpointing

## Recommended Acquisition Scope

### Stock Historical Core

Recommended scope:

- all U.S. stocks if the plan and runtime allow it
- otherwise S&P 500 or Russell 1000 as the first archival pass
- daily OHLCV as the minimum historical product
- adjusted pricing via splits/dividends normalization
- corporate actions
- ticker/reference metadata
- financials and ratios for the research universe

Suggested stock datasets/endpoints:

- flat files:
  - daily aggregates
  - historical trades
  - historical quotes
- REST:
  - ticker metadata/reference
  - dividends
  - splits
  - financial statements
  - ratios
  - news

### Options Research Core

Start with a narrow universe:

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

Recommended scope:

- contract reference metadata
- historical trades and quotes where available
- historical aggregates where available
- open interest, implied volatility, and greeks for current snapshots
- current snapshots stored daily going forward if historical chain snapshots are not available

Do **not** attempt full-market historical options chain reconstruction in the first paid month.

## Exact Datasets / Endpoints to Use

### Stocks

Bulk files:

- `us_stocks_sip/day_aggs_v1`
- `us_stocks_sip/trades_v1`
- `us_stocks_sip/quotes_v1`

REST:

- `/v3/reference/tickers`
- `/v3/reference/dividends`
- `/stocks/v1/splits`
- `/stocks/financials/v1/income-statements`
- `/stocks/financials/v1/balance-sheets`
- `/stocks/financials/v1/cash-flow-statements`
- `/stocks/financials/v1/ratios`
- `/rest/stocks/news`

### Options

Bulk files:

- `us_options_opra/day_aggs_v1`
- `us_options_opra/minute_aggs_v1`
- `us_options_opra/trades_v1`
- `us_options_opra/quotes_v1`

REST:

- `/v3/reference/options/contracts`
- `/v3/snapshot/options/{underlying}`
- `/v3/snapshot/options/{underlying}/{optionContract}`
- `/v3/quotes/{optionsTicker}`
- `/v3/trades/{optionsTicker}`
- `/v2/aggs/ticker/{optionsTicker}/range/{multiplier}/{timespan}/{from}/{to}`

## REST vs Flat Files vs Hybrid

### REST Only

Use only for:

- smoke testing
- metadata
- small experiments

Not recommended for the archive build.

### Flat Files Only

Use for:

- bulk archival capture
- historical bars/trades/quotes

Not enough by itself for clean canonical enrichment.

### Hybrid

Use for:

- the main archive build

This is the recommended path.

## Rough Estimates

These are approximate and depend on universe size and retention window.

### Stocks

If we target 1,000 to 5,000 symbols and 10 years of daily bars:

- daily bar rows: roughly 2.5 million to 12.5 million
- trades/quotes rows: much larger if included broadly
- storage: low tens of GB for daily bars; far higher if trades/quotes are fully retained
- runtime: hours to days depending on bandwidth and file count

If we target a much larger U.S. equity universe:

- daily bar rows: tens of millions
- storage and cleanup requirements rise quickly

### Options

For 10 underlyings over multiple years:

- contract reference rows: manageable
- chain snapshot rows: large but still feasible if limited to a small universe
- historical trades/quotes/minute bars: extremely large if every contract is included
- storage: can move into tens to hundreds of GB quickly
- runtime: sensitive to file count, contract universe, and retries

## Unknowns / Risks

- Some endpoint history limits are plan-dependent.
- Chain snapshot endpoints are documented as current snapshots, not historical archives.
- "Unlimited API calls" still comes with plan access limits and history depth limits on some endpoints.
- Options data volume can explode if scope is not tightly constrained.
- REST-only options acquisition is not a realistic archive plan.

## Pre-Purchase Checklist

- [ ] Polygon/Massive free tier works in this environment
- [ ] API key configuration works
- [ ] Rate limiting is understood and tested
- [ ] Provider call logging works
- [ ] Raw payload storage works
- [ ] Canonical normalization works
- [ ] Checkpointing works
- [ ] Resume/retry works
- [ ] Acquisition estimator works
- [ ] Test stock import succeeds for AAPL
- [ ] Test stock import succeeds for SPY
- [ ] Test options import succeeds for SPY on the target tier
- [ ] Local storage is available
- [ ] Backup strategy is defined

## Go / No-Go Recommendation

**Go for stocks.**

**Conditional go for options only if the scope stays narrow.**

Do not buy a paid month unless:

1. the free tier smoke test works,
2. the importer can resume from checkpoints,
3. the canonical schema is ready,
4. the raw payload storage path is working,
5. the stock archive scope is clear,
6. the options scope is explicitly limited.

If the goal is a full historical options archive for the whole market, this is **not** the right one-month purchase plan.
