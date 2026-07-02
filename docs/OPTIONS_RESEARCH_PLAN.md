# Options Research Plan

This is a future research branch, not an implementation plan for v2.

The goal is to extend Stock Signal Lab to stock options without exploding scope.

## Why Options Are Different

Options are not just another ticker feed.

They add:

- contract explosion
- expiration and strike dimensions
- bid/ask spreads
- liquidity constraints
- Greeks
- implied volatility
- higher leverage and higher risk
- higher data cost

That makes options research a separate track from the equity signal engine.

## Recommended Initial Universe

Start small.

Suggested underlyings:

- MAG7
- SPY
- QQQ

Optional later:

- PLTR
- SOFI
- RIVN

Scope rule:

- fewer than 10 underlyings in v1
- do not ingest full-market options chains

## Candidate Providers

Research later:

- Polygon
- Tradier
- Finnhub
- ThetaData
- Intrinio
- Cboe options data
- yfinance as limited / experimental only

Provider evaluation criteria:

- data depth
- quote freshness
- chain history
- Greeks availability
- implied volatility availability
- rate limits
- licensing and terms
- total cost

## Initial Tables To Consider Later

- `option_chains`
- `option_contracts`
- `option_quotes`
- `option_greeks`
- `option_signals`
- `option_experiments`

## Initial Signals

- `put_call_volume_ratio`
- `put_call_open_interest_ratio`
- `unusual_call_volume`
- `unusual_put_volume`
- `iv_rank`
- `iv_percentile`
- `expected_move`
- `liquidity_score`
- `bid_ask_spread_score`
- `covered_call_candidate`
- `cash_secured_put_candidate`

## Risk Controls

- never recommend naked options
- avoid illiquid contracts
- warn on wide spreads
- prefer educational / research posture
- no automated trading

## Experiment Ideas

- high call volume vs next 30d stock return
- high put volume vs next 30d stock return
- IV rank vs future realized volatility
- covered-call candidate returns
- cash-secured-put candidate returns
- unusual options activity plus strong fundamentals

## Implementation Order

Phase 1: documentation
Phase 2: provider research
Phase 3: mock options provider
Phase 4: schema
Phase 5: small-universe ingestion
Phase 6: option signals
Phase 7: experiments
Phase 8: UI

## Core Scope Rule

Options should stay small at first.

- fewer than 10 underlyings
- no full-market chain ingestion in v1
- no automated trading
- no silent leverage assumptions
- no production promises until research proves value

## Success Criteria

The options branch should be able to answer empirical questions like:

- Do options signals add predictive value beyond equity signals?
- Which option measures are stable enough to trust?
- Are the resulting outcomes better than random or benchmark baselines?
