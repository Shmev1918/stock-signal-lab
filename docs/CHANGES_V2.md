# Version 2

Date: 2026-07-01

## Major Features

- Experiment Engine v1
- Diagnostics layer
- Signal diagnostics
- Distribution diagnostics
- Bootstrap installer
- Local setup documentation
- Automatic refresh improvements
- Signal normalization fixes
- Real-data yfinance validation
- Research documentation updates
- Baseline experiment report
- Local dashboard polish

## Bug Fixes

- Flat signal normalization
- `free_cash_flow_positive` fallback handling
- SPY benchmark handling
- momentum alias mapping
- watchlist refresh reporting
- score date/history bug
- duplicate scoring issues
- score response now includes `scored_at`
- analysis history now includes `as_of_date`
- backend API import/lint issues
- history/export tests aligned with deduped historical score behavior

## Validation

- `ruff check app tests` passed
- `pytest -q` passed: `111 passed, 1 warning`
- Frontend build passed with Vite
- Live yfinance validation completed successfully
- App starts successfully after rebuild

## Known Limitations

- yfinance has partial fundamentals
- confidence model is still heuristic
- scoring thresholds are not yet empirically tuned
- experiment sample sizes are still relatively small
- watchlist universe is still small and survivorship-biased
- some signal threshold experiments remain sparse or inconclusive

## Next Research Priorities

- expand signal library
- larger stock universe
- feature registry
- hypothesis testing
- confidence model
- machine learning

