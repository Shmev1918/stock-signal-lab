from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.constants import SCORING_MODEL_VERSION, SIGNAL_MODEL_VERSION
from app.backtesting.evaluation import calculate_metrics
from app.db.models import BacktestResult, BacktestRun, DailyPrice, Fundamental
from app.ingestion.ingest_fundamentals import ingest_fundamentals
from app.ingestion.ingest_prices import ingest_prices
from app.providers.base import MarketDataNotFound, MarketDataProvider, MarketDataTimeout
from app.providers.factory import get_market_data_provider
from app.services.scoring_service import score_ticker
from app.services.stock_service import get_watchlist


@dataclass
class BacktestRequest:
    name: str
    start_date: date
    end_date: date
    rebalance_frequency: str = "monthly"
    benchmark: str = "SPY"
    universe: list[str] | None = None


def _backtest_tickers(session: Session, request: BacktestRequest) -> list[str]:
    if request.universe:
        return [ticker.upper() for ticker in request.universe]
    watchlist = get_watchlist(session)
    if watchlist:
        return [item.ticker for item in watchlist]
    return [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "META",
        "TSLA",
        "BRK.B",
        "V",
        "JNJ",
        "KO",
        "PEP",
        "COST",
        "PLTR",
        "SOFI",
        "RIVN",
    ]


def _has_price_coverage(session: Session, ticker: str, start_date: date, end_date: date) -> bool:
    stmt = select(func.min(DailyPrice.price_date), func.max(DailyPrice.price_date)).where(DailyPrice.ticker == ticker)
    minimum, maximum = session.exec(stmt).one()
    return minimum is not None and maximum is not None and minimum <= start_date and maximum >= end_date


def _has_fundamental_snapshot(session: Session, ticker: str) -> bool:
    stmt = select(func.count(Fundamental.id)).where(Fundamental.ticker == ticker)
    return int(session.exec(stmt).one()) > 0


def _ensure_local_data(
    session: Session,
    provider: MarketDataProvider,
    ticker: str,
    start_date: date,
    end_date: date,
) -> list[str]:
    warnings: list[str] = []
    try:
        if not _has_price_coverage(session, ticker, start_date, end_date):
            ingest_prices(session, provider, ticker, start_date, end_date)
    except (MarketDataNotFound, MarketDataTimeout) as exc:
        warnings.append(str(exc))

    try:
        if not _has_fundamental_snapshot(session, ticker):
            ingest_fundamentals(session, provider, ticker)
    except (MarketDataNotFound, MarketDataTimeout) as exc:
        warnings.append(str(exc))

    return warnings


def _rebalance_boundaries(start_date: date, end_date: date, rebalance_frequency: str) -> list[date]:
    step_days = 30 if rebalance_frequency == "monthly" else 90
    boundaries = [start_date]
    cursor = start_date
    while cursor < end_date:
        cursor = min(cursor + timedelta(days=step_days), end_date)
        if cursor != boundaries[-1]:
            boundaries.append(cursor)
    if boundaries[-1] != end_date:
        boundaries.append(end_date)
    return boundaries


def _price_on_or_before(session: Session, ticker: str, target_date: date) -> float | None:
    stmt = (
        select(DailyPrice.close)
        .where(DailyPrice.ticker == ticker, DailyPrice.price_date <= target_date)
        .order_by(DailyPrice.price_date.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def _returns_for_period(session: Session, ticker: str, start_date: date, end_date: date) -> float | None:
    start_price = _price_on_or_before(session, ticker, start_date)
    end_price = _price_on_or_before(session, ticker, end_date)
    if start_price is None or end_price is None or start_price <= 0:
        return None
    return (end_price - start_price) / start_price


def _simulate_portfolio_returns(
    session: Session,
    selected_tickers: list[str],
    start_date: date,
    end_date: date,
) -> tuple[float, list[dict[str, Any]]]:
    if not selected_tickers:
        return 0.0, []
    holding_returns = []
    holding_rows: list[dict[str, Any]] = []
    for ticker in selected_tickers:
        ticker_return = _returns_for_period(session, ticker, start_date, end_date)
        if ticker_return is None:
            continue
        holding_returns.append(ticker_return)
        holding_rows.append({"ticker": ticker, "weight": round(1.0 / len(selected_tickers), 4), "period_return": round(ticker_return, 4)})
    if not holding_returns:
        return 0.0, holding_rows
    return mean(holding_returns), holding_rows


def _persist_backtest_results(
    session: Session,
    provider: str,
    backtest_run_id: int,
    metrics: dict[str, float],
    benchmark_return: float,
    excess_return: float,
) -> None:
    rows = [
        BacktestResult(backtest_run_id=backtest_run_id, ticker="PORTFOLIO", result_type="total_return", value=metrics["total_return"], details={"provider": provider}),
        BacktestResult(backtest_run_id=backtest_run_id, ticker="PORTFOLIO", result_type="annualized_return", value=metrics["annualized_return"], details={"provider": provider}),
        BacktestResult(backtest_run_id=backtest_run_id, ticker="PORTFOLIO", result_type="max_drawdown", value=metrics["max_drawdown"], details={"provider": provider}),
        BacktestResult(backtest_run_id=backtest_run_id, ticker="PORTFOLIO", result_type="volatility", value=metrics["volatility"], details={"provider": provider}),
        BacktestResult(backtest_run_id=backtest_run_id, ticker="PORTFOLIO", result_type="win_rate", value=metrics["win_rate"], details={"provider": provider}),
        BacktestResult(backtest_run_id=backtest_run_id, ticker="BENCHMARK", result_type="total_return", value=benchmark_return, details={"benchmark": True, "provider": provider}),
        BacktestResult(backtest_run_id=backtest_run_id, ticker="BENCHMARK", result_type="excess_return", value=excess_return, details={"benchmark": True, "provider": provider}),
    ]
    for row in rows:
        session.add(row)
    session.commit()


def run_backtest(session: Session, request: BacktestRequest) -> dict[str, Any]:
    provider = get_market_data_provider()
    provider_class = provider.__class__.__name__.lower()
    if "yfinance" in provider_class:
        provider_name = "yfinance"
    elif "mock" in provider_class:
        provider_name = "mock"
    else:
        provider_name = provider_class.replace("marketdataprovider", "").strip("_") or "internal"
    tickers = _backtest_tickers(session, request)
    all_warnings: list[str] = []
    for ticker in tickers + [request.benchmark]:
        all_warnings.extend(_ensure_local_data(session, provider, ticker, request.start_date, request.end_date))

    boundaries = _rebalance_boundaries(request.start_date, request.end_date, request.rebalance_frequency)
    if len(boundaries) < 2:
        boundaries = [request.start_date, request.end_date]

    period_returns: list[float] = []
    benchmark_returns: list[float] = []
    selected_portfolio: list[dict[str, Any]] = []

    for idx, rebalance_date in enumerate(boundaries[:-1]):
        next_date = boundaries[idx + 1]
        scored_rows = [score_ticker(session, ticker, as_of_date=rebalance_date) for ticker in tickers]
        ranked = sorted(scored_rows, key=lambda row: row.opportunity_score, reverse=True)
        selected = ranked[:5]
        selected_tickers = [row.ticker for row in selected]
        portfolio_return, holding_rows = _simulate_portfolio_returns(session, selected_tickers, rebalance_date, next_date)
        benchmark_return = _returns_for_period(session, request.benchmark, rebalance_date, next_date) or 0.0
        period_returns.append(portfolio_return)
        benchmark_returns.append(benchmark_return)
        selected_portfolio = holding_rows

    metrics = calculate_metrics(period_returns)
    benchmark_total = 1.0
    for value in benchmark_returns:
        benchmark_total *= 1 + value
    benchmark_total -= 1
    excess_return = metrics.total_return - benchmark_total

    run = BacktestRun(
        name=request.name,
        start_date=request.start_date,
        end_date=request.end_date,
        rebalance_frequency=request.rebalance_frequency,
        benchmark=request.benchmark,
        provider=provider_name,
        scoring_model_version=SCORING_MODEL_VERSION,
        signal_model_version=SIGNAL_MODEL_VERSION,
        run_timestamp=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    _persist_backtest_results(
        session,
        provider=provider_name,
        backtest_run_id=run.id or 0,
        metrics={
            "total_return": metrics.total_return,
            "annualized_return": metrics.annualized_return,
            "max_drawdown": metrics.max_drawdown,
            "volatility": metrics.volatility,
            "win_rate": metrics.win_rate,
        },
        benchmark_return=benchmark_total,
        excess_return=excess_return,
    )

    run_payload = {
        "id": run.id,
        "name": run.name,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "rebalance_frequency": run.rebalance_frequency,
        "benchmark": run.benchmark,
        "provider": run.provider,
        "scoring_model_version": run.scoring_model_version,
        "signal_model_version": run.signal_model_version,
        "run_timestamp": run.run_timestamp.isoformat() if run.run_timestamp else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }

    return {
        "run": run_payload,
        "portfolio": selected_portfolio,
        "metrics": {
            "total_return": metrics.total_return,
            "annualized_return": metrics.annualized_return,
            "max_drawdown": metrics.max_drawdown,
            "volatility": metrics.volatility,
            "win_rate": metrics.win_rate,
            "benchmark_return": benchmark_total,
            "excess_return": excess_return,
        },
        "warnings": all_warnings,
    }
