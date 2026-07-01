from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class StockBase(SQLModel):
    ticker: str = Field(index=True)
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None
    last_updated: datetime = Field(default_factory=datetime.now, index=True)


class Stock(StockBase, table=True):
    __tablename__ = "stocks"
    id: int | None = Field(default=None, primary_key=True)


class DailyPrice(SQLModel, table=True):
    __tablename__ = "daily_prices"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    price_date: date = Field(index=True)
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    adj_close: float | None = None
    volume: int | None = None
    source: str = Field(default="mock", index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class Fundamental(SQLModel, table=True):
    __tablename__ = "fundamentals"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    as_of_date: date = Field(index=True)
    revenue_growth: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    free_cash_flow: float | None = None
    return_on_equity: float | None = None
    debt_to_equity: float | None = None
    interest_coverage: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    price_to_sales: float | None = None
    price_to_fcf: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source: str = Field(default="mock", index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class Dividend(SQLModel, table=True):
    __tablename__ = "dividends"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    ex_date: date = Field(index=True)
    pay_date: date | None = None
    amount: float = 0.0
    source: str = Field(default="mock", index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class NewsItem(SQLModel, table=True):
    __tablename__ = "news_items"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    published_at: datetime = Field(index=True)
    title: str
    summary: str | None = None
    url: str | None = None
    sentiment: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source: str = Field(default="mock", index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class StockScore(SQLModel, table=True):
    __tablename__ = "stock_scores"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    as_of_date: date = Field(index=True)
    risk_score: float
    quality_score: float
    valuation_score: float
    momentum_score: float
    opportunity_score: float
    risk_category: str
    recommendation: str
    explanation: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source: str = Field(default="internal", index=True)
    scoring_model_version: str = Field(default="0.1.0", index=True)
    signal_model_version: str = Field(default="0.1.0", index=True)
    strategy_name: str = Field(default="balanced", index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class StockSignal(SQLModel, table=True):
    __tablename__ = "stock_signals"
    id: int | None = Field(default=None, primary_key=True)
    stock_id: int = Field(foreign_key="stocks.id", index=True)
    signal_date: date = Field(index=True)
    signal_name: str = Field(index=True)
    signal_category: str = Field(index=True)
    raw_value: float | None = None
    normalized_score: float
    weight: float
    direction: str
    confidence: str
    source: str = Field(index=True)
    explanation: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class Recommendation(SQLModel, table=True):
    __tablename__ = "recommendations"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    as_of_date: date = Field(index=True)
    label: str = Field(index=True)
    explanation: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class InvestmentDecision(SQLModel, table=True):
    __tablename__ = "investment_decisions"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    decision_date: date = Field(index=True)
    action: str = Field(index=True)
    strategy_name: str = Field(default="balanced", index=True)
    price_at_decision: float
    quantity: float | None = None
    conviction: int
    thesis: str
    risks: str
    engine_recommendation: str
    engine_opportunity_score: float
    engine_risk_category: str
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class BacktestRun(SQLModel, table=True):
    __tablename__ = "backtest_runs"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    start_date: date
    end_date: date
    rebalance_frequency: str = "monthly"
    benchmark: str = "SPY"
    provider: str = Field(default="mock", index=True)
    scoring_model_version: str = Field(default="0.1.0", index=True)
    signal_model_version: str = Field(default="0.1.0", index=True)
    run_timestamp: datetime = Field(default_factory=datetime.now, index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class BacktestResult(SQLModel, table=True):
    __tablename__ = "backtest_results"
    id: int | None = Field(default=None, primary_key=True)
    backtest_run_id: int = Field(index=True)
    ticker: str = Field(index=True)
    result_type: str = Field(index=True)
    value: float | None = None
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class Experiment(SQLModel, table=True):
    __tablename__ = "experiments"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    experiment_type: str = Field(index=True)
    strategy_name: str | None = Field(default=None, index=True)
    horizon_days: int
    benchmark_ticker: str = Field(default="SPY", index=True)
    start_date: date = Field(index=True)
    end_date: date = Field(index=True)
    filters_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class ExperimentResult(SQLModel, table=True):
    __tablename__ = "experiment_results"
    id: int | None = Field(default=None, primary_key=True)
    experiment_id: int = Field(foreign_key="experiments.id", index=True)
    ticker: str = Field(index=True)
    as_of_date: date = Field(index=True)
    strategy_name: str = Field(index=True)
    recommendation: str = Field(index=True)
    risk_category: str = Field(index=True)
    opportunity_score: float
    risk_score: float
    quality_score: float
    valuation_score: float
    momentum_score: float
    future_price_date: date | None = Field(default=None, index=True)
    future_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    outcome_label: str | None = Field(default=None, index=True)
    status: str = Field(default="completed", index=True)
    skip_reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class WatchlistItem(SQLModel, table=True):
    __tablename__ = "watchlist_items"
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True, unique=True)
    active: bool = Field(default=True, index=True)
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now, index=True)
