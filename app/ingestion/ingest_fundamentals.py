from __future__ import annotations

from datetime import date

from sqlmodel import Session
from sqlmodel import select

from app.db.models import Dividend, Fundamental, NewsItem, Stock
from app.providers.base import MarketDataError, MarketDataProvider, coerce_warnings


def _default_profile(ticker: str) -> dict[str, object]:
    return {
        "ticker": ticker.upper(),
        "name": ticker.upper(),
        "sector": None,
        "industry": None,
        "exchange": None,
        "market_cap": None,
        "source": "yfinance_partial",
    }


def _default_fundamentals(ticker: str) -> dict[str, object]:
    return {
        "ticker": ticker.upper(),
        "as_of_date": date.today(),
        "revenue_growth": None,
        "gross_margin": None,
        "operating_margin": None,
        "free_cash_flow": None,
        "return_on_equity": None,
        "debt_to_equity": None,
        "interest_coverage": None,
        "pe_ratio": None,
        "forward_pe": None,
        "price_to_sales": None,
        "price_to_fcf": None,
        "raw": {},
        "source": "yfinance_partial",
    }


def _best_effort_payload(
    fetch_fn,
    ticker: str,
    default_payload: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    try:
        payload = fetch_fn(ticker)
    except MarketDataError as exc:
        return dict(default_payload), [str(exc)]
    except Exception as exc:  # pragma: no cover - defensive provider guard
        return dict(default_payload), [str(exc)]
    if not isinstance(payload, dict):
        payload = {}
    data, warnings = coerce_warnings(dict(payload))
    merged = dict(default_payload)
    merged.update(data)
    return merged, warnings


def ingest_fundamentals(session: Session, provider: MarketDataProvider, ticker: str) -> dict[str, object]:
    profile, profile_warnings = _best_effort_payload(provider.get_company_profile, ticker, _default_profile(ticker))
    fundamentals, fundamental_warnings = _best_effort_payload(
        provider.get_fundamentals,
        ticker,
        _default_fundamentals(ticker),
    )
    try:
        dividends = provider.get_dividends(ticker)
        dividend_warnings: list[str] = []
    except MarketDataError as exc:
        dividends = []
        dividend_warnings = [str(exc)]
    except Exception as exc:  # pragma: no cover - defensive provider guard
        dividends = []
        dividend_warnings = [str(exc)]
    try:
        news_items = provider.get_news(ticker)
        news_warnings: list[str] = []
    except MarketDataError as exc:
        news_items = []
        news_warnings = [str(exc)]
    except Exception as exc:  # pragma: no cover - defensive provider guard
        news_items = []
        news_warnings = [str(exc)]

    existing_dividend_keys = set(
        session.exec(
            select(Dividend.ex_date).where(Dividend.ticker == profile["ticker"])
        )
    )
    existing_news_keys = set(
        session.exec(
            select(NewsItem.url).where(NewsItem.ticker == profile["ticker"])
        )
    )

    existing_stock = session.exec(select(Stock).where(Stock.ticker == profile["ticker"])).first()
    if existing_stock is None:
        session.add(Stock(**profile))
    else:
        for key, value in profile.items():
            if hasattr(existing_stock, key):
                setattr(existing_stock, key, value)
        session.add(existing_stock)

    existing_fundamental = session.exec(
        select(Fundamental).where(Fundamental.ticker == fundamentals["ticker"], Fundamental.as_of_date == fundamentals["as_of_date"])
    ).first()
    if existing_fundamental is None:
        session.add(Fundamental(**fundamentals))
    else:
        for key, value in fundamentals.items():
            if hasattr(existing_fundamental, key):
                setattr(existing_fundamental, key, value)
        session.add(existing_fundamental)

    for row in dividends:
        if row["ex_date"] in existing_dividend_keys:
            continue
        session.add(Dividend(**row))
    for row in news_items:
        news_key = row.get("url") or row["title"]
        if news_key in existing_news_keys:
            continue
        session.add(NewsItem(**row))
    session.commit()
    return {
        "stocks": 1,
        "fundamentals": 1,
        "dividends": len(dividends),
        "news_items": len(news_items),
        "warnings": profile_warnings + fundamental_warnings + dividend_warnings + news_warnings,
    }
