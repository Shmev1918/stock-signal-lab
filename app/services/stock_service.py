from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.db.models import DailyPrice, Fundamental, Stock, StockScore, StockSignal, WatchlistItem


def upsert_watchlist_item(session: Session, ticker: str) -> WatchlistItem:
    item = session.exec(select(WatchlistItem).where(WatchlistItem.ticker == ticker)).first()
    if item:
        item.active = True
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    item = WatchlistItem(ticker=ticker, active=True)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def remove_watchlist_item(session: Session, ticker: str) -> None:
    item = session.exec(select(WatchlistItem).where(WatchlistItem.ticker == ticker)).first()
    if item:
        item.active = False
        session.add(item)
        session.commit()


def get_watchlist(session: Session) -> list[WatchlistItem]:
    return list(session.exec(select(WatchlistItem).where(WatchlistItem.active.is_(True))))


def get_stock(session: Session, ticker: str) -> Stock | None:
    return session.exec(select(Stock).where(Stock.ticker == ticker)).first()


def get_prices(
    session: Session,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 365,
    order: str = "desc",
) -> list[DailyPrice]:
    stmt = select(DailyPrice).where(DailyPrice.ticker == ticker)
    if start_date is not None:
        stmt = stmt.where(DailyPrice.price_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(DailyPrice.price_date <= end_date)
    stmt = stmt.order_by(DailyPrice.price_date.desc(), DailyPrice.created_at.desc(), DailyPrice.id.desc())
    if limit > 0:
        stmt = stmt.limit(limit)
    rows = list(session.exec(stmt))
    if order == "asc":
        rows.reverse()
    return rows


def get_latest_price(session: Session, ticker: str) -> DailyPrice | None:
    stmt = select(DailyPrice).where(DailyPrice.ticker == ticker).order_by(DailyPrice.price_date.desc(), DailyPrice.created_at.desc())
    return session.exec(stmt).first()


def get_price_on_or_after(session: Session, ticker: str, target_date: date) -> DailyPrice | None:
    stmt = (
        select(DailyPrice)
        .where(DailyPrice.ticker == ticker, DailyPrice.price_date >= target_date)
        .order_by(DailyPrice.price_date.asc(), DailyPrice.created_at.asc(), DailyPrice.id.asc())
        .limit(1)
    )
    return session.exec(stmt).first()


def get_latest_fundamental(session: Session, ticker: str):
    stmt = select(Fundamental).where(Fundamental.ticker == ticker).order_by(Fundamental.as_of_date.desc(), Fundamental.created_at.desc())
    return session.exec(stmt).first()


def get_latest_score(session: Session, ticker: str, strategy_name: str | None = None) -> StockScore | None:
    stmt = select(StockScore).where(StockScore.ticker == ticker)
    if strategy_name is not None:
        stmt = stmt.where(StockScore.strategy_name == strategy_name)
    stmt = stmt.order_by(StockScore.as_of_date.desc(), StockScore.created_at.desc(), StockScore.id.desc())
    return session.exec(stmt).first()


def get_latest_score_at(
    session: Session,
    ticker: str,
    as_of_date: date,
    strategy_name: str | None = None,
) -> StockScore | None:
    stmt = select(StockScore).where(StockScore.ticker == ticker, StockScore.as_of_date <= as_of_date)
    if strategy_name is not None:
        stmt = stmt.where(StockScore.strategy_name == strategy_name)
    stmt = stmt.order_by(StockScore.as_of_date.desc(), StockScore.created_at.desc(), StockScore.id.desc()).limit(1)
    return session.exec(stmt).first()


def get_latest_score_source(session: Session, ticker: str, strategy_name: str | None = None) -> str | None:
    score = get_latest_score(session, ticker, strategy_name=strategy_name)
    return score.source if score else None


def get_latest_scores(session: Session) -> list[StockScore]:
    ordered = list(
        session.exec(
            select(StockScore).order_by(
                StockScore.ticker,
                StockScore.as_of_date.desc(),
                StockScore.created_at.desc(),
                StockScore.id.desc(),
            )
        )
    )
    latest: dict[str, StockScore] = {}
    for row in ordered:
        latest.setdefault(row.ticker, row)
    return sorted(latest.values(), key=lambda row: (row.opportunity_score, row.as_of_date), reverse=True)


def get_score_history(
    session: Session,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 30,
    strategy_name: str | None = None,
) -> list[StockScore]:
    stmt = select(StockScore).where(StockScore.ticker == ticker)
    if strategy_name is not None:
        stmt = stmt.where(StockScore.strategy_name == strategy_name)
    if start_date is not None:
        stmt = stmt.where(StockScore.as_of_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(StockScore.as_of_date <= end_date)
    stmt = stmt.order_by(StockScore.created_at.desc(), StockScore.as_of_date.desc(), StockScore.id.desc())
    if limit > 0:
        stmt = stmt.limit(limit)
    return list(session.exec(stmt))


def get_score_history_all(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    strategy_name: str | None = None,
    recommendation: str | None = None,
) -> list[StockScore]:
    stmt = select(StockScore)
    if strategy_name is not None:
        stmt = stmt.where(StockScore.strategy_name == strategy_name)
    if recommendation is not None:
        stmt = stmt.where(StockScore.recommendation == recommendation)
    if start_date is not None:
        stmt = stmt.where(StockScore.as_of_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(StockScore.as_of_date <= end_date)
    stmt = stmt.order_by(StockScore.as_of_date.desc(), StockScore.created_at.desc(), StockScore.id.desc())
    return list(session.exec(stmt))


def score_history_dicts(scores: list[StockScore]) -> list[dict[str, object]]:
    return [
        {
            **score.model_dump(),
            "scored_at": score.created_at,
            "model_versions": {
                "scoring": score.scoring_model_version,
                "signals": score.signal_model_version,
            },
            "strategy_name": score.strategy_name,
        }
        for score in scores
    ]


def get_signals(session: Session, ticker: str) -> list[StockSignal]:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if not stock:
        return []
    stmt = select(StockSignal).where(StockSignal.stock_id == stock.id).order_by(StockSignal.signal_date.desc(), StockSignal.created_at.desc(), StockSignal.id.desc())
    return list(session.exec(stmt))


def get_latest_signals(session: Session, ticker: str) -> list[StockSignal]:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if not stock:
        return []
    ordered = list(
        session.exec(
            select(StockSignal)
            .where(StockSignal.stock_id == stock.id)
            .order_by(StockSignal.signal_date.desc(), StockSignal.created_at.desc(), StockSignal.id.desc())
        )
    )
    latest_by_name: dict[str, StockSignal] = {}
    if not ordered:
        return []
    latest_date = ordered[0].signal_date
    for row in ordered:
        if row.signal_date != latest_date:
            break
        latest_by_name.setdefault(row.signal_name, row)
    return sorted(latest_by_name.values(), key=lambda row: (row.signal_category, row.signal_name))


def get_latest_signals_at(session: Session, ticker: str, as_of_date: date) -> list[StockSignal]:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if not stock:
        return []
    ordered = list(
        session.exec(
            select(StockSignal)
            .where(StockSignal.stock_id == stock.id, StockSignal.signal_date <= as_of_date)
            .order_by(StockSignal.signal_date.desc(), StockSignal.created_at.desc(), StockSignal.id.desc())
        )
    )
    latest_by_name: dict[str, StockSignal] = {}
    if not ordered:
        return []
    latest_date = ordered[0].signal_date
    for row in ordered:
        if row.signal_date != latest_date:
            break
        latest_by_name.setdefault(row.signal_name, row)
    return sorted(latest_by_name.values(), key=lambda row: (row.signal_category, row.signal_name))


def get_latest_signal_at(
    session: Session,
    ticker: str,
    as_of_date: date,
    signal_name: str | None = None,
    signal_category: str | None = None,
) -> StockSignal | None:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if not stock:
        return None
    stmt = select(StockSignal).where(StockSignal.stock_id == stock.id, StockSignal.signal_date <= as_of_date)
    if signal_name is not None:
        stmt = stmt.where(StockSignal.signal_name == signal_name)
    if signal_category is not None:
        stmt = stmt.where(StockSignal.signal_category == signal_category)
    stmt = stmt.order_by(StockSignal.signal_date.desc(), StockSignal.created_at.desc(), StockSignal.id.desc()).limit(1)
    return session.exec(stmt).first()


def get_latest_price_source(session: Session, ticker: str) -> str | None:
    price = get_latest_price(session, ticker)
    return price.source if price else None


def get_latest_price_source_at(session: Session, ticker: str, as_of_date: date) -> str | None:
    stmt = (
        select(DailyPrice.source)
        .where(DailyPrice.ticker == ticker, DailyPrice.price_date <= as_of_date)
        .order_by(DailyPrice.price_date.desc(), DailyPrice.created_at.desc(), DailyPrice.id.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def get_latest_fundamental_source(session: Session, ticker: str) -> str | None:
    fundamental = get_latest_fundamental(session, ticker)
    return fundamental.source if fundamental else None


def get_latest_fundamental_source_at(session: Session, ticker: str, as_of_date: date) -> str | None:
    stmt = (
        select(Fundamental.source)
        .where(Fundamental.ticker == ticker, Fundamental.as_of_date <= as_of_date)
        .order_by(Fundamental.as_of_date.desc(), Fundamental.created_at.desc(), Fundamental.id.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def get_latest_signal_source(session: Session, ticker: str) -> str | None:
    signals = get_latest_signals(session, ticker)
    if not signals:
        return None
    return signals[0].source


def get_latest_price_date(session: Session, ticker: str) -> date | None:
    price = get_latest_price(session, ticker)
    return price.price_date if price else None


def get_latest_fundamental_date(session: Session, ticker: str) -> date | None:
    fundamental = get_latest_fundamental(session, ticker)
    return fundamental.as_of_date if fundamental else None


def get_latest_signal_date(session: Session, ticker: str) -> date | None:
    signals = get_latest_signals(session, ticker)
    return signals[0].signal_date if signals else None


def get_latest_score_date(session: Session, ticker: str, strategy_name: str | None = None) -> date | None:
    score = get_latest_score(session, ticker, strategy_name=strategy_name)
    return score.as_of_date if score else None


def get_available_strategies(session: Session, ticker: str) -> list[str]:
    return list(
        session.exec(
            select(StockScore.strategy_name)
            .where(StockScore.ticker == ticker)
            .distinct()
            .order_by(StockScore.strategy_name)
        )
    )


def get_watchlist_status(session: Session) -> list[dict[str, object]]:
    watchlist = get_watchlist(session)
    status_rows: list[dict[str, object]] = []
    for item in watchlist:
        ticker = item.ticker
        price = get_latest_price(session, ticker)
        fundamental = get_latest_fundamental(session, ticker)
        signals = get_latest_signals(session, ticker)
        score = get_latest_score(session, ticker)
        status_rows.append(
            {
                "ticker": ticker,
                "has_prices": price is not None,
                "latest_price_date": price.price_date if price else None,
                "has_signals": bool(signals),
                "latest_signal_date": signals[0].signal_date if signals else None,
                "has_scores": score is not None,
                "latest_score_date": score.as_of_date if score else None,
                "available_strategies": get_available_strategies(session, ticker),
                "data_sources": {
                    "prices": price.source if price else None,
                    "fundamentals": fundamental.source if fundamental else None,
                    "signals": signals[0].source if signals else None,
                    "scores": score.source if score else None,
                },
            }
        )
    return status_rows


def needs_ingest(session: Session, ticker: str) -> bool:
    return get_latest_price(session, ticker) is None or get_latest_fundamental(session, ticker) is None


def get_latest_signal_source_at(session: Session, ticker: str, as_of_date: date) -> str | None:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if not stock:
        return None
    stmt = (
        select(StockSignal.source)
        .where(StockSignal.stock_id == stock.id, StockSignal.signal_date <= as_of_date)
        .order_by(StockSignal.signal_date.desc(), StockSignal.created_at.desc(), StockSignal.id.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def get_signal_history(
    session: Session,
    ticker: str,
    signal_name: str | None = None,
    signal_category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 200,
) -> list[StockSignal]:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if not stock:
        return []
    stmt = select(StockSignal).where(StockSignal.stock_id == stock.id)
    if signal_name is not None:
        stmt = stmt.where(StockSignal.signal_name == signal_name)
    if signal_category is not None:
        stmt = stmt.where(StockSignal.signal_category == signal_category)
    if start_date is not None:
        stmt = stmt.where(StockSignal.signal_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(StockSignal.signal_date <= end_date)
    stmt = stmt.order_by(StockSignal.signal_date.desc(), StockSignal.created_at.desc(), StockSignal.id.desc())
    if limit > 0:
        stmt = stmt.limit(limit)
    return list(session.exec(stmt))


def get_analysis_history(
    session: Session,
    ticker: str,
    limit: int = 30,
    start_date: date | None = None,
    end_date: date | None = None,
    strategy_name: str | None = None,
) -> list[dict[str, object]]:
    scores = get_score_history(
        session,
        ticker,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        strategy_name=strategy_name,
    )
    if not scores:
        return []
    snapshots: list[dict[str, object]] = []
    for score in scores:
        snapshots.append(
            {
                "scored_at": score.created_at,
                "recommendation": score.recommendation,
                "risk_category": score.risk_category,
                "risk_score": score.risk_score,
                "quality_score": score.quality_score,
                "valuation_score": score.valuation_score,
                "momentum_score": score.momentum_score,
                "opportunity_score": score.opportunity_score,
                "summary": (score.explanation or {}).get("summary"),
                "data_sources": {
                    "prices": get_latest_price_source_at(session, ticker, score.as_of_date),
                    "fundamentals": get_latest_fundamental_source_at(session, ticker, score.as_of_date),
                    "signals": get_latest_signal_source_at(session, ticker, score.as_of_date) or "internal",
                    "scores": score.source,
                },
                "model_versions": {
                    "scoring": score.scoring_model_version,
                    "signals": score.signal_model_version,
                },
                "strategy_name": score.strategy_name,
            }
        )
    return snapshots


def get_latest_analysis_snapshot(session: Session, ticker: str) -> dict[str, object] | None:
    history = get_analysis_history(session, ticker, limit=1)
    return history[0] if history else None
