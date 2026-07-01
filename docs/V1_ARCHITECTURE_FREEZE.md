# V1 Architecture Freeze

Version 1 of the platform architecture is considered complete.

The completed architecture is:

provider abstraction
-> ingestion
-> Postgres
-> signals
-> strategies
-> scores
-> rankings
-> journal
-> evaluation
-> CLI / frontend

This means the core platform plumbing is no longer the main focus.

Future work should focus on:

- data quality
- signal quality
- experiment framework
- ML research
- hypothesis testing

The goal from this point forward is to improve the quality of the analysis, not to keep expanding the platform surface area.
