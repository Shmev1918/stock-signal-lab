from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlmodel import Session

from app.config import get_settings
from app.db.models import DailyPrice, Experiment, ExperimentResult, StockScore
from app.experiments.filters import normalize_filters, score_matches_filters, signal_matches_filters
from app.experiments.outcome import classify_outcome
from app.experiments.summary import summarize_experiment_results
from app.services.stock_service import get_latest_signal_at, get_latest_signals_at, get_price_on_or_after


@dataclass
class ExperimentRequest:
    name: str
    experiment_type: str
    strategy_name: str | None
    horizon_days: int
    benchmark_ticker: str
    start_date: date
    end_date: date
    filters: dict[str, Any] = field(default_factory=dict)
    description: str | None = None


def _selected_strategy(request: ExperimentRequest) -> str:
    return request.strategy_name or get_settings().scoring_strategy


def _score_candidates(session: Session, request: ExperimentRequest) -> list[StockScore]:
    strategy_name = _selected_strategy(request)
    stmt = select(StockScore).where(StockScore.as_of_date >= request.start_date, StockScore.as_of_date <= request.end_date)
    stmt = stmt.where(StockScore.strategy_name == strategy_name)
    stmt = stmt.order_by(StockScore.as_of_date.asc(), StockScore.ticker.asc(), StockScore.created_at.asc(), StockScore.id.asc())
    return list(session.exec(stmt))


def _benchmark_return(session: Session, benchmark_ticker: str, as_of_date: date, horizon_days: int) -> tuple[float | None, date | None]:
    start_price = get_price_on_or_after(session, benchmark_ticker, as_of_date)
    if start_price is None or not start_price.close:
        return None, None
    future_price = get_price_on_or_after(session, benchmark_ticker, as_of_date + timedelta(days=horizon_days))
    if future_price is None or not future_price.close:
        return None, None
    benchmark_return = ((future_price.close - start_price.close) / start_price.close) * 100.0
    return benchmark_return, future_price.price_date


def _future_return(session: Session, ticker: str, as_of_date: date, horizon_days: int) -> tuple[float | None, date | None, str | None]:
    start_price = get_price_on_or_after(session, ticker, as_of_date)
    if start_price is None or not start_price.close:
        return None, None, "missing_entry_price"
    future_price = get_price_on_or_after(session, ticker, as_of_date + timedelta(days=horizon_days))
    if future_price is None or not future_price.close:
        return None, None, "missing_future_price"
    future_return = ((future_price.close - start_price.close) / start_price.close) * 100.0
    return future_return, future_price.price_date, None


def _evaluate_score_candidate(
    session: Session,
    experiment_id: int,
    score: StockScore,
    request: ExperimentRequest,
    filters: dict[str, Any],
) -> ExperimentResult:
    benchmark_return, benchmark_date = _benchmark_return(session, request.benchmark_ticker, score.as_of_date, request.horizon_days)
    future_return, future_date, skip_reason = _future_return(session, score.ticker, score.as_of_date, request.horizon_days)
    if skip_reason is None and benchmark_return is None:
        skip_reason = "missing_benchmark_price"

    if skip_reason is not None:
        return ExperimentResult(
            experiment_id=experiment_id,
            ticker=score.ticker,
            as_of_date=score.as_of_date,
            strategy_name=score.strategy_name,
            recommendation=score.recommendation,
            risk_category=score.risk_category,
            opportunity_score=score.opportunity_score,
            risk_score=score.risk_score,
            quality_score=score.quality_score,
            valuation_score=score.valuation_score,
            momentum_score=score.momentum_score,
            future_price_date=future_date,
            future_return=future_return,
            benchmark_return=benchmark_return,
            excess_return=None,
            outcome_label=None,
            status="skipped",
            skip_reason=skip_reason,
        )

    excess_return = future_return - benchmark_return
    return ExperimentResult(
        experiment_id=experiment_id,
        ticker=score.ticker,
        as_of_date=score.as_of_date,
        strategy_name=score.strategy_name,
        recommendation=score.recommendation,
        risk_category=score.risk_category,
        opportunity_score=score.opportunity_score,
        risk_score=score.risk_score,
        quality_score=score.quality_score,
        valuation_score=score.valuation_score,
        momentum_score=score.momentum_score,
        future_price_date=future_date or benchmark_date,
        future_return=future_return,
        benchmark_return=benchmark_return,
        excess_return=excess_return,
        outcome_label=classify_outcome(excess_return),
        status="completed",
        skip_reason=None,
    )


def _evaluate_signal_candidate(
    session: Session,
    experiment_id: int,
    score: StockScore,
    request: ExperimentRequest,
    filters: dict[str, Any],
) -> ExperimentResult | None:
    signal_name = filters.get("signal_name")
    signal_category = filters.get("signal_category")
    if signal_name:
        signal = get_latest_signal_at(
            session,
            score.ticker,
            score.as_of_date,
            signal_name=str(signal_name),
            signal_category=str(signal_category) if signal_category else None,
        )
        if signal is None or not signal_matches_filters(signal, filters):
            return None
    else:
        signals = get_latest_signals_at(session, score.ticker, score.as_of_date)
        signal = next((item for item in signals if signal_matches_filters(item, filters)), None)
        if signal is None:
            return None
    return _evaluate_score_candidate(session, experiment_id, score, request, filters)


def run_experiment(session: Session, request: ExperimentRequest) -> dict[str, Any]:
    filters = normalize_filters(request.filters)
    strategy_name = _selected_strategy(request)
    experiment = Experiment(
        name=request.name,
        description=request.description,
        experiment_type=request.experiment_type,
        strategy_name=strategy_name,
        horizon_days=request.horizon_days,
        benchmark_ticker=request.benchmark_ticker,
        start_date=request.start_date,
        end_date=request.end_date,
        filters_json=filters,
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)

    results: list[ExperimentResult] = []
    for score in _score_candidates(session, request):
        if not score_matches_filters(score, request.experiment_type, filters):
            continue
        if request.experiment_type == "signal_threshold":
            result = _evaluate_signal_candidate(session, experiment.id or 0, score, request, filters)
            if result is None:
                continue
        else:
            result = _evaluate_score_candidate(session, experiment.id or 0, score, request, filters)
        results.append(result)
        session.add(result)

    session.commit()
    for row in results:
        session.refresh(row)

    return get_experiment_by_id(session, experiment.id or 0)


def list_experiments(session: Session) -> list[dict[str, Any]]:
    rows = list(
        session.exec(
            select(Experiment).order_by(Experiment.created_at.desc(), Experiment.id.desc())
        )
    )
    return [row.model_dump() for row in rows]


def get_experiment_results(session: Session, experiment_id: int) -> list[dict[str, Any]]:
    rows = list(
        session.exec(
            select(ExperimentResult).where(ExperimentResult.experiment_id == experiment_id).order_by(
                ExperimentResult.as_of_date.asc(),
                ExperimentResult.ticker.asc(),
                ExperimentResult.created_at.asc(),
                ExperimentResult.id.asc(),
            )
        )
    )
    return [row.model_dump() for row in rows]


def get_experiment(session: Session, experiment_id: int) -> Experiment | None:
    stmt = select(Experiment).where(Experiment.id == experiment_id).limit(1)
    return session.exec(stmt).first()


def get_experiment_by_id(session: Session, experiment_id: int) -> dict[str, Any]:
    experiment = get_experiment(session, experiment_id)
    if experiment is None:
        raise LookupError(f"Experiment not found: {experiment_id}")
    results = get_experiment_results(session, experiment_id)
    payload = experiment.model_dump()
    payload["results"] = results
    payload["result_count"] = len(results)
    return payload


def get_experiment_summary(session: Session, experiment_id: int) -> dict[str, Any]:
    experiment = get_experiment(session, experiment_id)
    if experiment is None:
        raise LookupError(f"Experiment not found: {experiment_id}")
    results = get_experiment_results(session, experiment_id)
    return summarize_experiment_results(experiment.model_dump(), results)
