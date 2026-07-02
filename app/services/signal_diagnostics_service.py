from __future__ import annotations

from datetime import date
from statistics import pstdev
from typing import Any

from sqlmodel import Session, select

from app.db.models import Fundamental
from app.signals.signal_engine import SignalEngine
from app.services.stock_service import get_prices, get_stock


def _latest_fundamental_snapshot(fundamentals: list[Fundamental]) -> dict[str, Any] | None:
    latest = fundamentals[-1] if fundamentals else None
    if latest is None:
        return None
    return {
        "as_of_date": latest.as_of_date,
        "revenue_growth": latest.revenue_growth,
        "gross_margin": latest.gross_margin,
        "operating_margin": latest.operating_margin,
        "free_cash_flow": latest.free_cash_flow,
        "return_on_equity": latest.return_on_equity,
        "debt_to_equity": latest.debt_to_equity,
        "interest_coverage": latest.interest_coverage,
        "pe_ratio": latest.pe_ratio,
        "forward_pe": latest.forward_pe,
        "price_to_sales": latest.price_to_sales,
        "price_to_fcf": latest.price_to_fcf,
        "source": latest.source,
    }


def _price_closes(prices: list) -> list[float]:
    return [float(row.close) for row in prices if getattr(row, "close", None) is not None]


def _rolling_start(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    return closes[-(window + 1)]


def _price_input_values(closes: list[float]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "price_count": len(closes),
        "latest_close": closes[-1] if closes else None,
        "first_close": closes[0] if closes else None,
        "close_stddev": round(pstdev(closes), 6) if len(closes) >= 2 else 0.0,
    }
    if closes:
        payload["window_3m_start"] = _rolling_start(closes, 63)
        payload["window_6m_start"] = _rolling_start(closes, 126)
        payload["window_12m_start"] = _rolling_start(closes, 252)
        payload["ma_50"] = round(sum(closes[-50:]) / 50, 6) if len(closes) >= 50 else None
        payload["ma_200"] = round(sum(closes[-200:]) / 200, 6) if len(closes) >= 200 else None
    return payload


def _fallback_reason(signal_name: str, raw_value: Any, closes: list[float], fundamentals: list[Fundamental]) -> str | None:
    if raw_value is not None:
        return None

    latest = fundamentals[-1] if fundamentals else None
    if signal_name in {"volatility", "max_drawdown", "return_3m", "return_6m", "return_12m", "ma_50_vs_200"}:
        if len(closes) < 2:
            return "missing price history"
        if signal_name in {"return_3m", "return_6m", "return_12m"} and len(closes) <= {"return_3m": 63, "return_6m": 126, "return_12m": 252}[signal_name]:
            return "insufficient rows for lookback window"
        if signal_name == "ma_50_vs_200" and len(closes) < 200:
            return "insufficient rows for moving averages"
        return "formula not implemented or input mismatch"

    if signal_name == "revenue_growth_consistency":
        values = [row.revenue_growth for row in fundamentals if row.revenue_growth is not None]
        return "missing revenue growth history" if not values else "formula not implemented or input mismatch"

    if signal_name == "free_cash_flow_positive":
        if latest is None:
            return "missing fundamentals snapshot"
        if latest.free_cash_flow is None:
            return "missing free cash flow"
        return "formula not implemented or input mismatch"

    field_map = {
        "roe": "return_on_equity",
        "debt_to_equity": "debt_to_equity",
        "pe_ratio": "pe_ratio",
        "price_to_sales": "price_to_sales",
    }
    if signal_name in field_map:
        if latest is None:
            return "missing fundamentals snapshot"
        if getattr(latest, field_map[signal_name]) is None:
            return f"missing {field_map[signal_name]}"
        return "formula not implemented or input mismatch"

    return "missing input data"


def _signal_input_values(signal_name: str, closes: list[float], fundamentals: list[Fundamental]) -> dict[str, Any]:
    payload = {
        "price_inputs": _price_input_values(closes),
        "fundamental_inputs": _latest_fundamental_snapshot(fundamentals),
    }
    if signal_name in {"volatility", "max_drawdown", "return_3m", "return_6m", "return_12m", "ma_50_vs_200"}:
        payload["signal_type"] = "price"
    elif signal_name in {"revenue_growth_consistency", "roe", "debt_to_equity", "free_cash_flow_positive", "pe_ratio", "price_to_sales"}:
        payload["signal_type"] = "fundamental"
    return payload


def get_signal_diagnostics(session: Session, ticker: str, as_of_date: date | None = None) -> dict[str, object]:
    as_of_date = as_of_date or date.today()
    stock = get_stock(session, ticker.upper())
    if stock is None:
        raise LookupError(f"Stock not found: {ticker}")

    prices = get_prices(session, ticker.upper(), end_date=as_of_date, limit=1000, order="asc")
    closes = _price_closes(prices)
    fundamentals = list(
        session.exec(
            select(Fundamental)
            .where(Fundamental.ticker == ticker.upper(), Fundamental.as_of_date <= as_of_date)
            .order_by(Fundamental.as_of_date.asc(), Fundamental.created_at.asc(), Fundamental.id.asc())
        )
    )

    engine = SignalEngine()
    records = engine.generate(session, ticker.upper(), as_of_date=as_of_date)
    signals = []
    for record in records:
        signals.append(
            {
                "signal_name": record.name,
                "signal_category": record.category,
                "input_values": _signal_input_values(record.name, closes, fundamentals),
                "raw_value": record.raw_value,
                "normalized_score": round(float(record.normalized_score), 2),
                "fallback_used": record.raw_value is None,
                "fallback_reason": _fallback_reason(record.name, record.raw_value, closes, fundamentals),
                "source": record.source,
            }
        )

    return {
        "ticker": ticker.upper(),
        "as_of_date": as_of_date,
        "signals": signals,
    }
