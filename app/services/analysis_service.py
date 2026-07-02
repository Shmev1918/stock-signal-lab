from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlmodel import Session

from app.config import get_settings
from app.scoring.summary import build_summary
from app.scoring.strategy_profiles import StrategyProfile, get_strategy_profile, list_strategy_profiles
from app.services.signal_service import signal_dicts
from app.services.scoring_service import SignalView
from app.services.stock_service import (
    get_latest_fundamental_source,
    get_latest_price_source,
    get_latest_price_date,
    get_latest_market_snapshot_date,
    get_latest_score,
    get_latest_score_source,
    get_latest_signal_source,
    get_latest_signals,
    get_watchlist,
    get_stock,
)
from app.signals.signal_engine import SignalEngine


_SEVERITY_RANK = {
    "STRONG_POSITIVE": 4,
    "POSITIVE": 3,
    "NEUTRAL": 2,
    "NEGATIVE": 1,
    "STRONG_NEGATIVE": 0,
}


def _group_latest_signals(session: Session, ticker: str) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for signal in signal_dicts(get_latest_signals(session, ticker)):
        grouped[signal["signal_category"]].append(signal)
    for category in ("RISK", "QUALITY", "VALUATION", "MOMENTUM"):
        grouped[category] = sorted(grouped.get(category, []), key=lambda row: row["signal_name"])
    return {category: grouped[category] for category in ("RISK", "QUALITY", "VALUATION", "MOMENTUM")}


def _signals_by_severity(signals: dict[str, list[dict[str, object]]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    positives: list[dict[str, object]] = []
    negatives: list[dict[str, object]] = []
    for category_signals in signals.values():
        for signal in category_signals:
            severity = str(signal.get("severity", "NEUTRAL"))
            if severity in {"STRONG_POSITIVE", "POSITIVE"}:
                positives.append(signal)
            elif severity in {"NEGATIVE", "STRONG_NEGATIVE"}:
                negatives.append(signal)
    return positives, negatives


def _top_signals(signals: list[dict[str, object]], positive: bool, limit: int = 5) -> list[dict[str, object]]:
    def sort_key(signal: dict[str, object]) -> tuple[int, float, str]:
        severity = str(signal.get("severity", "NEUTRAL"))
        rank = _SEVERITY_RANK.get(severity, 2)
        score = float(signal.get("normalized_score") or 50.0)
        return (rank, score, str(signal.get("signal_name", "")))

    filtered = [
        signal
        for signal in signals
        if (
            positive
            and str(signal.get("severity", "NEUTRAL")) in {"STRONG_POSITIVE", "POSITIVE"}
        )
        or (
            not positive
            and str(signal.get("severity", "NEUTRAL")) in {"NEGATIVE", "STRONG_NEGATIVE"}
        )
    ]
    reverse = positive
    sorted_signals = sorted(filtered, key=sort_key, reverse=reverse)
    return sorted_signals[:limit]


def _latest_signal_dicts(session: Session, ticker: str) -> list[dict[str, object]]:
    latest_signals = signal_dicts(get_latest_signals(session, ticker))
    if latest_signals:
        return latest_signals
    from app.services.signal_service import generate_signals

    snapshot_date = get_latest_market_snapshot_date(session, ticker) or date.today()
    return signal_dicts(generate_signals(session, ticker, as_of_date=snapshot_date))


def _compact_analysis_from_signals(
    ticker: str,
    signals: list[dict[str, object]],
    profile: StrategyProfile,
) -> dict[str, object]:
    engine = SignalEngine()
    signal_views = [SignalView(signal) for signal in signals]
    scores = engine.category_scores(signal_views, profile)
    opportunity_score = engine.opportunity_score(scores, profile)
    recommendation = engine.recommendation(scores, opportunity_score)
    risk_category = engine.risk_category(scores["risk"])
    positives, negatives = engine.positive_negative_signals(signal_views)
    top_positive = _top_signals(positives, positive=True, limit=3)
    top_negative = _top_signals(negatives, positive=False, limit=3)
    summary = build_summary(risk_category, top_positive, top_negative, scores)
    return {
        "ticker": ticker,
        "strategy_name": profile.name,
        "recommendation": recommendation,
        "risk_category": risk_category,
        "scores": {
            "risk": scores["risk"],
            "quality": scores["quality"],
            "valuation": scores["valuation"],
            "momentum": scores["momentum"],
            "opportunity": opportunity_score,
        },
        "positive_signals": top_positive,
        "negative_signals": top_negative,
        "summary": summary,
    }


def _base_analysis(session: Session, ticker: str, strategy_name: str | None = None) -> dict[str, object]:
    ticker = ticker.upper()
    selected_strategy = strategy_name or get_settings().scoring_strategy
    stock = get_stock(session, ticker)
    if stock is None:
        raise LookupError(f"Stock not found: {ticker}")

    latest_score = get_latest_score(session, ticker, strategy_name=selected_strategy)
    if latest_score is None:
        raise LookupError(f"Score not found: {ticker}")

    grouped_signals = _group_latest_signals(session, ticker)
    positive_signals, negative_signals = _signals_by_severity(grouped_signals)
    explanation = latest_score.explanation or {}
    scores = {
        "risk": latest_score.risk_score,
        "quality": latest_score.quality_score,
        "valuation": latest_score.valuation_score,
        "momentum": latest_score.momentum_score,
        "opportunity": latest_score.opportunity_score,
    }
    summary = str(explanation.get("summary") or build_summary(latest_score.risk_category, positive_signals, negative_signals, scores))
    data_sources = {
        "prices": get_latest_price_source(session, ticker),
        "fundamentals": get_latest_fundamental_source(session, ticker),
        "signals": get_latest_signal_source(session, ticker) or "internal",
        "scores": get_latest_score_source(session, ticker, strategy_name=selected_strategy) or "internal",
    }
    warnings = list(explanation.get("data_warnings", []))
    latest_price_date = get_latest_price_date(session, ticker)
    if latest_price_date is not None:
        age_days = (date.today() - latest_price_date).days
        if age_days > 7:
            warnings.append(f"latest price data is stale by {age_days} days")
    return {
        "ticker": ticker,
        "stock_profile": stock.model_dump(),
        "latest_score": latest_score.model_dump(),
        "recommendation": latest_score.recommendation,
        "risk_category": latest_score.risk_category,
        "scores": scores,
        "signals": grouped_signals,
        "positive_signals": positive_signals,
        "negative_signals": negative_signals,
        "warnings": warnings,
        "summary": summary,
        "data_sources": data_sources,
        "latest_price_source": data_sources["prices"],
        "latest_fundamentals_source": data_sources["fundamentals"],
        "latest_signal_source": data_sources["signals"],
        "score_source": data_sources["scores"],
        "strategy_name": latest_score.strategy_name,
    }


def build_analysis(session: Session, ticker: str, compact: bool = False, strategy_name: str | None = None) -> dict[str, object]:
    analysis = _base_analysis(session, ticker, strategy_name=strategy_name)
    if not compact:
        return analysis
    compact_positive = _top_signals(analysis["positive_signals"], positive=True)
    compact_negative = _top_signals(analysis["negative_signals"], positive=False)
    return {
        "ticker": analysis["ticker"],
        "recommendation": analysis["recommendation"],
        "risk_category": analysis["risk_category"],
        "scores": analysis["scores"],
        "latest_score": {
            "as_of_date": analysis["latest_score"]["as_of_date"],
            "created_at": analysis["latest_score"]["created_at"],
            "strategy_name": analysis["latest_score"]["strategy_name"],
        },
        "positive_signals": compact_positive,
        "negative_signals": compact_negative,
        "summary": analysis["summary"],
        "warnings": analysis["warnings"],
        "data_sources": analysis["data_sources"],
        "strategy_name": analysis["strategy_name"],
    }


def build_analysis_history(
    session: Session,
    ticker: str,
    limit: int = 30,
    start_date: date | None = None,
    end_date: date | None = None,
    strategy_name: str | None = None,
) -> list[dict[str, object]]:
    selected_strategy = strategy_name or get_settings().scoring_strategy
    from app.services.stock_service import get_analysis_history

    return get_analysis_history(
        session,
        ticker,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        strategy_name=selected_strategy,
    )


def build_strategy_comparison(
    session: Session,
    ticker: str,
    strategy_names: list[str] | None = None,
) -> list[dict[str, object]]:
    ticker = ticker.upper()
    stock = get_stock(session, ticker)
    if stock is None:
        raise LookupError(f"Stock not found: {ticker}")

    latest_signals = _latest_signal_dicts(session, ticker)
    if strategy_names is None:
        profiles = list_strategy_profiles()
    else:
        profiles = [get_strategy_profile(name) for name in strategy_names]

    return [_compact_analysis_from_signals(ticker, latest_signals, profile) for profile in profiles]


def build_strategy_rankings(
    session: Session,
    strategy_names: list[str] | None = None,
    limit: int = 25,
    include_signals: bool = False,
) -> dict[str, list[dict[str, object]]]:
    watchlist = get_watchlist(session)
    tickers = [item.ticker for item in watchlist]
    if strategy_names is None:
        profiles = list_strategy_profiles()
    else:
        profiles = [get_strategy_profile(name) for name in strategy_names]

    rankings: dict[str, list[dict[str, object]]] = {}
    for profile in profiles:
        rows: list[dict[str, object]] = []
        for ticker in tickers:
            latest_signals = _latest_signal_dicts(session, ticker)
            stock = get_stock(session, ticker)
            if stock is None:
                continue
            score = get_latest_score(session, ticker, strategy_name=profile.name)
            if score is None:
                from app.services.scoring_service import score_ticker

                score = score_ticker(session, ticker, strategy_name=profile.name)
            compact = _compact_analysis_from_signals(ticker, latest_signals, profile)
            row = {
                "ticker": ticker,
                "recommendation": compact["recommendation"],
                "risk_category": compact["risk_category"],
                "opportunity_score": compact["scores"]["opportunity"],
                "quality_score": compact["scores"]["quality"],
                "valuation_score": compact["scores"]["valuation"],
                "momentum_score": compact["scores"]["momentum"],
                "risk_score": compact["scores"]["risk"],
                "summary": compact["summary"],
                "strategy_name": profile.name,
                "score_as_of_date": score.as_of_date,
                "scored_at": score.created_at,
            }
            if include_signals:
                row["positive_signals"] = compact["positive_signals"]
                row["negative_signals"] = compact["negative_signals"]
            rows.append(row)

        rows = sorted(rows, key=lambda row: (row["opportunity_score"], row["ticker"]), reverse=True)
        for idx, row in enumerate(rows[:limit], start=1):
            row["rank"] = idx
        rankings[profile.name] = rows[:limit]
    return rankings
