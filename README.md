# stock-signal-lab

Personal investment decision-support tool for one user.

This repo is intentionally simple:

- local watchlist
- provider abstraction
- Postgres cache
- first-class stored signal layer
- scoring dimensions
- explainable recommendations
- backtesting scaffold

Not included:

- auth
- teams
- billing
- subscriptions
- public deployment assumptions

## Stack

- Python
- FastAPI
- Postgres
- SQLModel / SQLAlchemy
- Alembic
- pytest
- Ruff
- Docker Compose
- yfinance is optional for local market-data pulls

## Current Architecture

```text
provider → ingestion → Postgres → signals → strategies → scores → rankings → journal → evaluation
```

## Project Docs

- [Vision](docs/VISION.md)
- [Roadmap](docs/ROADMAP.md)
- [Analytics](docs/ANALYTICS.md)
- [Decisions](docs/DECISIONS.md)
- [Hypotheses](docs/HYPOTHESES.md)
- [V1 Architecture Freeze](docs/V1_ARCHITECTURE_FREEZE.md)
- [Research Phase](docs/RESEARCH_PHASE.md)
- [Data Provider Plan](docs/DATA_PROVIDER_PLAN.md)
- [Historical Data Acquisition Campaign](docs/HISTORICAL_DATA_ACQUISITION_CAMPAIGN.md)
- [Historical Data Acquisition Runbook](docs/HISTORICAL_DATA_ACQUISITION_RUNBOOK.md)
- [Polygon Data Acquisition Plan](docs/POLYGON_DATA_ACQUISITION_PLAN.md)
- [Acquisition Infrastructure](docs/ACQUISITION_INFRASTRUCTURE.md)
- [Future Features](docs/FUTURE_FEATURES.md)
- [Options Research Plan](docs/OPTIONS_RESEARCH_PLAN.md)
- [Feature Registry](docs/FEATURE_REGISTRY.md)
- [Local Setup](docs/LOCAL_SETUP.md)
- [Diagnostics](docs/DIAGNOSTICS.md)
- [Baseline Experiment Report](docs/BASELINE_EXPERIMENT_REPORT.md)

## License

This project is released under the [MIT License](LICENSE).

## Quick local setup

For a fresh machine or a friend/brother tester, use:

```bash
bash scripts/bootstrap-dev.sh
```

Full instructions are in [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).

## Local workflow

```bash
cp .env.example .env
make up
make migrate
make test
```

Alembic owns the Postgres schema. App startup does not create or alter Postgres tables.

Use `make migrate` to apply migrations and `make reset-db` to destroy local dev data and rebuild the schema from scratch.

## Local UI

Start the browser cockpit:

```bash
make ui
```

Or run the frontend directly:

```bash
make frontend-install
make frontend-dev
```

Open:

```text
http://localhost:5173
```

For mock-only local development, leave the default:

```bash
MARKET_DATA_PROVIDER=mock
```

For real local Yahoo Finance data pulls:

```bash
MARKET_DATA_PROVIDER=yfinance
```

If you want the optional local provider installed, use:

```bash
pip install -e '.[dev,yfinance]'
```

Provider choice affects both ingestion and backtesting. The same setting is used by
`POST /ingest/{ticker}` and `POST /backtests/run`.

The default scoring strategy is:

```bash
SCORING_STRATEGY=balanced
```

Current model versions:

```bash
SCORING_MODEL_VERSION=0.1.0
SIGNAL_MODEL_VERSION=0.1.0
```

## API

- `GET /health`
- `GET /watchlist`
- `POST /watchlist/{ticker}`
- `DELETE /watchlist/{ticker}`
- `POST /ingest/{ticker}`
- `POST /ingest/watchlist`
- `POST /signals/{ticker}/generate`
- `GET /signals/{ticker}`
- `GET /signals/{ticker}/latest`
- `GET /signals/{ticker}/history`
- `POST /score/{ticker}`
- `POST /score/watchlist`
- `GET /strategies`
- `GET /stocks/{ticker}`
- `GET /stocks/{ticker}/prices`
- `GET /stocks/{ticker}/score`
- `GET /stocks/{ticker}/scores`
- `GET /analysis/{ticker}`
- `GET /analysis/{ticker}/history`
- `GET /analysis/{ticker}/compare-strategies`
- `GET /rankings`
- `POST /backtests/run`
- `GET /backtests`
- `GET /backtests/{id}`

## Notes

The initial provider is a deterministic mock provider. That makes the scoring and backtesting
workflow runnable before wiring in free market data providers.

`yfinance` is useful for personal experimentation, but it should not be treated as a guaranteed
production-grade market-data source.

Signals are persisted separately from final scores so scoring weights and recommendation logic
can change later without losing the underlying evidence.

Available scoring strategies:

- `balanced`: general-purpose default
- `conservative_quality`: emphasizes stability, cash flow, and lower debt
- `growth_momentum`: emphasizes growth and momentum, tolerating more risk and valuation
- `value_recovery`: emphasizes cheaper valuation and improving trend

Use a strategy per request when scoring or analyzing:

```bash
POST /score/AAPL?strategy=conservative_quality
GET /analysis/AAPL?strategy=growth_momentum
```

To tell whether an analysis came from mock or yfinance data, inspect the `data_sources` section
returned by `GET /analysis/{ticker}`. It reports the latest source for prices, fundamentals,
signals, and scores. For example, `prices: mock` or `prices: yfinance`.

Example personal workflow:

```bash
POST /watchlist/AAPL
POST /ingest/AAPL
POST /signals/AAPL/generate
POST /score/AAPL
GET /analysis/AAPL
```

Daily workflow:

```bash
make refresh
make rankings
make evaluate
make status
```

Rebuild the local database from scratch:

```bash
make reset-db
```

Manual inspection endpoints:

```bash
GET /stocks/AAPL/prices?limit=365&order=desc
GET /stocks/AAPL/scores?limit=30
GET /signals/AAPL/history?signal_category=RISK&limit=200
GET /strategies
GET /analysis/AAPL?compact=true
GET /analysis/AAPL/history?limit=30
GET /analysis/AAPL/compare-strategies
GET /diagnostics/distributions?strategy_name=balanced
GET /rankings/strategies
GET /export/rankings.csv?strategy=value_recovery&limit=25
GET /export/signals/AAPL.csv
GET /export/analysis-history/AAPL.csv
GET /export/distributions.csv
```

Strategy ranking examples:

```bash
GET /rankings/strategies
GET /rankings/strategies?strategies=balanced
GET /rankings/strategies?strategies=balanced,conservative_quality,value_recovery
GET /rankings/strategies?strategies=value_recovery&limit=10&include_signals=true
```

CSV export examples:

```bash
curl -o rankings.csv "http://localhost:8000/export/rankings.csv?strategy=value_recovery&limit=25"
curl -o AAPL-signals.csv "http://localhost:8000/export/signals/AAPL.csv"
curl -o AAPL-history.csv "http://localhost:8000/export/analysis-history/AAPL.csv"
```

Decision journal examples:

```bash
POST /decisions/AAPL
GET /decisions
GET /decisions/AAPL
GET /decisions/AAPL/performance
GET /decisions/performance
```

Example payload:

```json
{
  "action": "BUY",
  "strategy_name": "balanced",
  "quantity": 10,
  "conviction": 4,
  "thesis": "Strong cash flow and acceptable risk.",
  "risks": "Valuation is elevated."
}
```

Performance checks:

```bash
GET /decisions/AAPL/performance
GET /decisions/performance?action=BUY&strategy_name=balanced&min_conviction=4
```

Horizon checks:

```bash
GET /decisions/performance-horizons
GET /decisions/performance-horizons?horizons=30,90,180,365
GET /decisions/performance-horizons?action=BUY&strategy_name=balanced&min_conviction=4
```

Engine vs human evaluation:

```bash
GET /decisions/evaluation
GET /decisions/evaluation?horizon=90&strategy_name=balanced&min_conviction=4
```

Engine score evaluation:

```bash
GET /scores/evaluation
GET /scores/evaluation?horizon=90&strategy_name=balanced&recommendation=ACCUMULATE
GET /scores/evaluation/details?horizon=90&recommendation=WATCH
```

Strategy comparison:

```bash
GET /scores/evaluation/strategies
GET /scores/evaluation/strategies?horizon=90&recommendation=ACCUMULATE
GET /scores/evaluation/strategies?horizon=180&min_opportunity_score=60&risk_category=MEDIUM_RISK
```

CLI workflow:

```bash
python -m app.cli refresh-watchlist --strategies balanced,conservative_quality,value_recovery
python -m app.cli rankings --strategy balanced --limit 25
python -m app.cli evaluate-scores --horizon 90
python -m app.cli evaluate-decisions --horizon 90
python -m app.cli status
```

Cron example:

```cron
0 7 * * 1-5 cd ~/projects/stock-signal-lab && make refresh > backups/daily-refresh.json && make rankings > backups/daily-rankings.json && make evaluate > backups/daily-evaluation.json
```

Manual verification:

1. `POST /watchlist/AAPL`
2. `POST /ingest/AAPL`
3. `POST /signals/AAPL/generate`
4. `POST /score/AAPL`
5. `GET /analysis/AAPL`

TODOs in the code mark where formulas and provider integrations should evolve.
