# Future Features

This document keeps the next research branches visible without mixing them into the current v2 equity research stack.

## Congressional Trading Intelligence

This is a future alternative-data branch, not a trading accusation system.

The goal is empirical:

- ingest public congressional trade disclosures
- normalize and store raw disclosures
- generate disclosure-safe signals
- run historical experiments on disclosure dates only
- evaluate whether public disclosure has predictive value after it becomes known

Core rule:

- use `disclosure_date`, not `transaction_date`, in experiments and historical scoring
- never allow pre-disclosure information leakage

Key research questions:

- Do disclosed congressional buys outperform SPY after 90, 180, or 365 days?
- Are congressional sells less predictive than buys?
- Do bipartisan disclosures behave differently from one-party activity?
- Do historically predictive politicians exist at all, and if so, how confident is that result?

Suggested implementation shape:

- provider abstraction for congressional disclosure sources
- normalized politician and trade tables
- disclosure-safe signals
- politician performance ranking
- experiment integration
- statistical UI later, if the data proves useful

This branch should remain empirical and non-accusatory.

## Stock Options Research Track

This is a separate future branch for options analytics.

The purpose is to extend the same research engine to a different instrument class without turning the project into a trading bot.

Possible options-research questions:

- Do certain option flow patterns predict future equity moves?
- Do implied volatility and IV rank help with timing?
- Which expirations and deltas are most informative?
- Can options data improve event-driven research around earnings?

Likely future capabilities:

- options chain ingestion
- expiration and strike normalization
- implied volatility and IV rank
- Greeks-aware feature snapshots
- options-specific backtesting
- strategy comparisons for covered calls, cash-secured puts, and spreads

Like the equity engine, the options branch should stay:

- local-first
- explainable
- benchmark-aware
- empirical
- free-first when possible

See also: [Options Research Plan](OPTIONS_RESEARCH_PLAN.md)
