# Local Setup

## Prerequisites

- Git
- Docker Desktop or Docker Engine
- `docker compose`

## Clone

```bash
git clone git@github.com:Shmev1918/stock-signal-lab.git
cd stock-signal-lab
```

## Bootstrap

Run one command:

```bash
bash scripts/bootstrap-dev.sh
```

That will:

- create `.env` from `.env.example` if needed
- default `MARKET_DATA_PROVIDER=mock` unless already set
- start the app, frontend, and database
- apply Alembic migrations

## Open the app

- Backend: `http://localhost:8000`
- Health: `http://localhost:8000/health/details`
- Frontend: `http://localhost:5173`

## Switch to real local data

Set:

```bash
MARKET_DATA_PROVIDER=yfinance
```

in `.env`, then rerun the bootstrap or refresh workflow.

## Reset local data

Use:

```bash
bash scripts/reset-dev.sh
```

This destroys local Postgres data and rebuilds the schema.

## Troubleshooting

- If Docker is not reachable, start Docker Desktop and retry.
- If ports 8000 or 5173 are busy, stop the conflicting process and rerun bootstrap.
- If migrations fail, run `make reset-dev`.
- If the frontend does not open, check `docker compose ps`.
