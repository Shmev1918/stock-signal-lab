from __future__ import annotations

import inspect
from datetime import date

from sqlalchemy import func
from sqlmodel import Session
from sqlmodel import select

from app.config import get_settings
from app.db.models import DailyPrice, Fundamental, StockScore, StockSignal
from app.providers.factory import get_market_data_provider
from app.scoring.strategy_profiles import get_strategy_profile, list_strategy_profiles
from app.services.ingestion_service import ingest_ticker
from app.services.scoring_service import score_ticker
from app.services.signal_service import generate_signals as generate_signals_for_ticker
from app.services.stock_service import (
    get_latest_market_snapshot_date,
    get_latest_signal_date_at,
    get_stock,
    get_watchlist,
    get_watchlist_status,
    needs_ingest,
    upsert_watchlist_item,
)


def _count_rows(session: Session, statement) -> int:
    value = session.exec(statement).one()
    return int(value or 0)


def _ticker_refresh_state(session: Session, ticker: str) -> dict[str, int]:
    stock = get_stock(session, ticker)
    signal_count = 0
    if stock is not None and stock.id is not None:
        signal_count = _count_rows(
            session,
            select(func.count()).select_from(StockSignal).where(StockSignal.stock_id == stock.id),
        )
    return {
        "price_count": _count_rows(
            session,
            select(func.count()).select_from(DailyPrice).where(DailyPrice.ticker == ticker),
        ),
        "fundamental_count": _count_rows(
            session,
            select(func.count()).select_from(Fundamental).where(Fundamental.ticker == ticker),
        ),
        "signal_count": signal_count,
        "score_count": _count_rows(
            session,
            select(func.count()).select_from(StockScore).where(StockScore.ticker == ticker),
        ),
    }


def active_watchlist(session: Session) -> list:
    items = get_watchlist(session)
    if items:
        return items
    settings = get_settings()
    return [upsert_watchlist_item(session, ticker) for ticker in settings.default_watchlist]


def parse_strategies(strategies: str | None) -> list[str]:
    if strategies is None:
        return [profile.name for profile in list_strategy_profiles()]
    parsed = [item.strip() for item in strategies.split(",") if item.strip()]
    return [get_strategy_profile(name).name for name in parsed] if parsed else [profile.name for profile in list_strategy_profiles()]


def refresh_watchlist_workflow(
    session: Session,
    strategies: str | None = None,
    generate_signals: bool = True,
    score: bool = True,
    force_reingest: bool = False,
    provider_name: str | None = None,
    ingest_fn=ingest_ticker,
    generate_signals_fn=generate_signals_for_ticker,
    score_fn=score_ticker,
) -> dict[str, object]:
    selected_strategies = parse_strategies(strategies)
    provider = get_market_data_provider(provider_name) if provider_name is not None else get_market_data_provider()
    watchlist = active_watchlist(session)
    successes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for item in watchlist:
        ticker = item.ticker
        try:
            before_state = _ticker_refresh_state(session, ticker)
            ingest_attempted = force_reingest or needs_ingest(session, ticker)
            ingest_failed = False
            ingest_result: dict[str, object] = {"status": "skipped", "warnings": []}
            if ingest_attempted:
                ingest_kwargs = {}
                if "provider" in inspect.signature(ingest_fn).parameters:
                    ingest_kwargs["provider"] = provider
                ingest_result = ingest_fn(session, ticker, **ingest_kwargs)
                if "error" in ingest_result:
                    ingest_failed = True
                    failures.append({"ticker": ticker, "stage": "ingest", **ingest_result})
                    continue
            target_date = get_latest_market_snapshot_date(session, ticker) or date.today()
            latest_signal_date = get_latest_signal_date_at(session, ticker, target_date)
            should_generate_signals = generate_signals and (
                ingest_attempted or latest_signal_date is None or latest_signal_date < target_date
            )

            def _call_with_optional_kwargs(fn, **kwargs):
                params = inspect.signature(fn).parameters
                call_kwargs = {key: value for key, value in kwargs.items() if key in params}
                return fn(session, ticker, **call_kwargs)

            if should_generate_signals:
                _call_with_optional_kwargs(generate_signals_fn, as_of_date=target_date)
            if score:
                for strategy_name in selected_strategies:
                    _call_with_optional_kwargs(score_fn, as_of_date=target_date, strategy_name=strategy_name)
            after_state = _ticker_refresh_state(session, ticker)
            partial_warnings = [str(item) for item in ingest_result.get("warnings", [])]
            ingested = bool(ingest_attempted and not ingest_failed)
            if not ingest_attempted and after_state["price_count"] > 0:
                skipped_existing_data = True
            else:
                skipped_existing_data = False
            signals_generated = should_generate_signals and after_state["signal_count"] > before_state["signal_count"]
            signals_skipped_existing = not signals_generated and after_state["signal_count"] > 0
            scores_created = after_state["score_count"] > before_state["score_count"]
            scores_skipped_existing = not scores_created and after_state["score_count"] > 0
            successes.append(
                {
                    "ticker": ticker,
                    "ingested": ingested,
                    "ingest_status": "partial_success" if partial_warnings else ("success" if ingested else "skipped_existing_data"),
                    "skipped_existing_data": skipped_existing_data,
                    "signals_generated": signals_generated,
                    "signals_skipped_existing": signals_skipped_existing,
                    "scores_created": scores_created,
                    "scores_skipped_existing": scores_skipped_existing,
                    "partial_warnings": partial_warnings,
                    "failures": [],
                }
            )
        except Exception as exc:  # pragma: no cover - defensive bulk workflow guard
            failures.append({"ticker": ticker, "stage": "refresh", "error": str(exc)})

    return {
        "provider": provider_name or get_settings().market_data_provider,
        "tickers_processed": len(watchlist),
        "successes": successes,
        "failures": failures,
        "strategies": selected_strategies,
    }


def watchlist_status_payload(session: Session) -> list[dict[str, object]]:
    active_watchlist(session)
    return get_watchlist_status(session)
