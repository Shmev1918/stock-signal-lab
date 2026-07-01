.PHONY: up down migrate test lint format refresh rankings evaluate status frontend-install frontend-dev ui reset-db

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	docker compose run --rm --build app alembic upgrade head

test:
	docker compose run --rm --build -e DATABASE_URL=sqlite:///./stock_signal_lab_test.db app pytest

lint:
	ruff check .

format:
	ruff format .

refresh:
	python -m app.cli refresh-watchlist --strategies balanced,conservative_quality,value_recovery

rankings:
	python -m app.cli rankings --strategy balanced --limit 25

evaluate:
	python -m app.cli evaluate-scores --horizon 90
	python -m app.cli evaluate-decisions --horizon 90

status:
	python -m app.cli status

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev -- --host 0.0.0.0

ui:
	docker compose up -d --build

reset-db:
	docker compose down -v
	docker compose up -d db
	docker compose run --rm --build app alembic upgrade head
