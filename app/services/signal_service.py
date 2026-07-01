from __future__ import annotations

from datetime import date
from datetime import datetime

from sqlmodel import Session, select

from app.db.models import Stock, StockSignal
from app.signals.base import SignalRecord, signal_severity
from app.signals.signal_engine import SignalEngine


def _stock_or_raise(session: Session, ticker: str) -> Stock:
    stock = session.exec(select(Stock).where(Stock.ticker == ticker)).first()
    if stock is None:
        stock = Stock(ticker=ticker, last_updated=datetime.now())
        session.add(stock)
        session.commit()
        session.refresh(stock)
    if stock.id is None:
        raise LookupError(f"Stock missing primary key: {ticker}")
    return stock


def generate_signals(session: Session, ticker: str, as_of_date: date | None = None) -> list[StockSignal]:
    engine = SignalEngine()
    as_of_date = as_of_date or date.today()
    stock = _stock_or_raise(session, ticker)
    signal_records: list[SignalRecord] = engine.generate(session, ticker, as_of_date=as_of_date)

    rows: list[StockSignal] = []
    for signal in signal_records:
        row = StockSignal(
            stock_id=stock.id,
            signal_date=as_of_date,
            signal_name=signal.name,
            signal_category=signal.category,
            raw_value=signal.raw_value,
            normalized_score=signal.normalized_score,
            weight=signal.weight,
            direction=signal.direction,
            confidence=signal.confidence,
            source=signal.source,
            explanation={
                "name": signal.name,
                "category": signal.category,
                "raw_value": signal.raw_value,
                "normalized_score": round(signal.normalized_score, 2),
                "severity": signal_severity(signal.normalized_score),
                "weight": round(signal.weight, 4),
                "direction": signal.direction,
                "confidence": signal.confidence,
                "source": signal.source,
                "explanation": signal.explanation,
            },
        )
        session.add(row)
        rows.append(row)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def signal_dicts(signals: list[StockSignal]) -> list[dict[str, object]]:
    return [
        {
            "id": row.id,
            "stock_id": row.stock_id,
            "signal_date": row.signal_date,
            "signal_name": row.signal_name,
            "signal_category": row.signal_category,
            "raw_value": row.raw_value,
            "normalized_score": row.normalized_score,
            "severity": signal_severity(row.normalized_score),
            "weight": row.weight,
            "direction": row.direction,
            "confidence": row.confidence,
            "source": row.source,
            "explanation": row.explanation,
            "created_at": row.created_at,
        }
        for row in signals
    ]
