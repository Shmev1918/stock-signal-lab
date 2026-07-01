from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from sqlmodel import Session, select

from app.db.models import InvestmentDecision
from app.scoring.strategy_profiles import get_strategy_profile
from app.services.scoring_service import score_ticker
from app.services.stock_service import get_latest_price, get_latest_score, get_price_on_or_after


def _duplicate_decision_warnings(session: Session, ticker: str, decision_date: date) -> list[str]:
    existing = session.exec(
        select(InvestmentDecision.id).where(
            InvestmentDecision.ticker == ticker,
            InvestmentDecision.decision_date == decision_date,
        ).limit(1)
    ).first()
    if existing is None:
        return []
    return [f"duplicate decision warning: {ticker} already has a decision on {decision_date.isoformat()}"]


def _latest_score_or_raise(session: Session, ticker: str, strategy_name: str) -> object:
    latest_score = get_latest_score(session, ticker, strategy_name=strategy_name)
    if latest_score is None:
        latest_score = score_ticker(session, ticker, strategy_name=strategy_name)
    return latest_score


def create_investment_decision(
    session: Session,
    ticker: str,
    action: str,
    strategy_name: str | None = None,
    decision_date: date | None = None,
    quantity: float | None = None,
    conviction: int = 3,
    thesis: str = "",
    risks: str = "",
) -> tuple[InvestmentDecision, list[str]]:
    selected_strategy = get_strategy_profile(strategy_name).name if strategy_name is not None else None
    if selected_strategy is None:
        from app.config import get_settings

        selected_strategy = get_settings().scoring_strategy

    decision_day = decision_date or date.today()
    price = get_latest_price(session, ticker)
    if price is None:
        raise LookupError(f"Price not found: {ticker}")

    score = _latest_score_or_raise(session, ticker, selected_strategy)
    warnings = _duplicate_decision_warnings(session, ticker, decision_day)
    decision = InvestmentDecision(
        ticker=ticker,
        decision_date=decision_day,
        action=action,
        strategy_name=selected_strategy,
        price_at_decision=price.close,
        quantity=quantity,
        conviction=conviction,
        thesis=thesis,
        risks=risks,
        engine_recommendation=score.recommendation,
        engine_opportunity_score=score.opportunity_score,
        engine_risk_category=score.risk_category,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision, warnings


def list_investment_decisions(session: Session, ticker: str | None = None) -> list[InvestmentDecision]:
    stmt = select(InvestmentDecision)
    if ticker is not None:
        stmt = stmt.where(InvestmentDecision.ticker == ticker)
    stmt = stmt.order_by(InvestmentDecision.decision_date.desc(), InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc())
    return list(session.exec(stmt))


def _performance_row(session: Session, decision: InvestmentDecision) -> dict[str, object]:
    latest_price = get_latest_price(session, decision.ticker)
    latest_price_value = latest_price.close if latest_price else None
    latest_price_date = latest_price.price_date if latest_price else None
    if latest_price_value is not None and decision.price_at_decision:
        return_since = ((latest_price_value - decision.price_at_decision) / decision.price_at_decision) * 100.0
    else:
        return_since = None
    days_held_value = (latest_price_date - decision.decision_date).days if latest_price_date is not None else None
    return {
        "id": decision.id,
        "ticker": decision.ticker,
        "decision_date": decision.decision_date,
        "action": decision.action,
        "strategy_name": decision.strategy_name,
        "price_at_decision": decision.price_at_decision,
        "latest_price": latest_price_value,
        "latest_price_date": latest_price_date,
        "return_since_decision_percent": return_since,
        "days_held": days_held_value,
        "engine_recommendation": decision.engine_recommendation,
        "engine_opportunity_score": decision.engine_opportunity_score,
        "engine_risk_category": decision.engine_risk_category,
        "thesis": decision.thesis,
        "risks": decision.risks,
        "quantity": decision.quantity,
        "conviction": decision.conviction,
        "created_at": decision.created_at,
    }


def get_decision_performance(
    session: Session,
    ticker: str | None = None,
    action: str | None = None,
    strategy_name: str | None = None,
    min_conviction: int | None = None,
) -> list[dict[str, object]]:
    decisions = list_investment_decisions(session, ticker=ticker.upper() if ticker else None)
    rows = []
    for decision in decisions:
        if action is not None and decision.action != action:
            continue
        if strategy_name is not None and decision.strategy_name != strategy_name:
            continue
        if min_conviction is not None and decision.conviction < min_conviction:
            continue
        rows.append(_performance_row(session, decision))
    return rows


def summarize_decision_performance(rows: list[dict[str, object]]) -> dict[str, object]:
    returns = [float(row["return_since_decision_percent"]) for row in rows if row.get("return_since_decision_percent") is not None]
    count = len(rows)
    winning = [value for value in returns if value > 0]

    def _return_value(row: dict[str, object], fallback: float) -> float:
        value = row.get("return_since_decision_percent")
        return float(value) if value is not None else fallback

    best = max(rows, key=lambda row: _return_value(row, float("-inf"))) if returns else None
    worst = min(rows, key=lambda row: _return_value(row, float("inf"))) if returns else None
    return {
        "count": count,
        "average_return": (sum(returns) / len(returns)) if returns else None,
        "win_rate": (len(winning) / len(returns)) if returns else None,
        "best_decision": best,
        "worst_decision": worst,
    }


def _return_for_horizon(session: Session, decision: InvestmentDecision, horizon_days: int) -> float | None:
    target_date = decision.decision_date + timedelta(days=horizon_days)
    price = get_price_on_or_after(session, decision.ticker, target_date)
    if price is None:
        return None
    if not decision.price_at_decision:
        return None
    return ((price.close - decision.price_at_decision) / decision.price_at_decision) * 100.0


def _horizon_summary(rows: list[dict[str, object]], horizon_days: int) -> dict[str, object]:
    key = f"return_{horizon_days}d"
    returns = [float(row[key]) for row in rows if row.get(key) is not None]
    count = len(returns)
    if not returns:
        return {"average_return": None, "win_rate": None, "count": 0}
    winning = [value for value in returns if value > 0]
    return {
        "average_return": sum(returns) / len(returns),
        "win_rate": len(winning) / len(returns),
        "count": count,
    }


def get_decision_performance_horizons(
    session: Session,
    horizons: list[int] | None = None,
    action: str | None = None,
    strategy_name: str | None = None,
    min_conviction: int | None = None,
) -> dict[str, object]:
    selected_horizons = sorted({int(horizon) for horizon in (horizons or [30, 90, 180, 365]) if int(horizon) > 0})
    decisions = list_investment_decisions(session)
    rows: list[dict[str, object]] = []
    for decision in decisions:
        if action is not None and decision.action != action:
            continue
        if strategy_name is not None and decision.strategy_name != strategy_name:
            continue
        if min_conviction is not None and decision.conviction < min_conviction:
            continue

        row = _performance_row(session, decision)
        for horizon in selected_horizons:
            row[f"return_{horizon}d"] = _return_for_horizon(session, decision, horizon)
        rows.append(row)

    summary_by_horizon = {str(horizon): _horizon_summary(rows, horizon) for horizon in selected_horizons}
    return {
        "count": len(rows),
        "horizons": selected_horizons,
        "summary_by_horizon": summary_by_horizon,
        "decisions": rows,
    }


def _summary_statistics(values: list[float]) -> dict[str, object]:
    if not values:
        return {
            "count": 0,
            "average_return": None,
            "median_return": None,
            "win_rate": None,
            "best_return": None,
            "worst_return": None,
        }

    winning = [value for value in values if value > 0]
    return {
        "count": len(values),
        "average_return": sum(values) / len(values),
        "median_return": median(values),
        "win_rate": len(winning) / len(values),
        "best_return": max(values),
        "worst_return": min(values),
    }


def _group_evaluation_rows(rows: list[dict[str, object]], key: str) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        value = row.get("horizon_return_percent")
        if value is None:
            continue
        group_key = str(row.get(key))
        grouped.setdefault(group_key, []).append(float(value))
    return {group_key: _summary_statistics(values) for group_key, values in grouped.items()}


def _evaluate_disagreement_buckets(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    buckets = {
        "human_buy_engine_avoid_or_speculative": [],
        "human_avoid_engine_accumulate": [],
        "human_watch_engine_accumulate": [],
    }
    for row in rows:
        return_value = row.get("horizon_return_percent")
        if return_value is None:
            continue
        action = row["action"]
        engine_recommendation = row["engine_recommendation"]
        value = float(return_value)
        if action == "BUY" and engine_recommendation in {"AVOID", "SPECULATIVE"}:
            buckets["human_buy_engine_avoid_or_speculative"].append(value)
        if action == "AVOID" and engine_recommendation == "ACCUMULATE":
            buckets["human_avoid_engine_accumulate"].append(value)
        if action == "WATCH" and engine_recommendation == "ACCUMULATE":
            buckets["human_watch_engine_accumulate"].append(value)
    return {name: _summary_statistics(values) for name, values in buckets.items()}


def get_decision_evaluation(
    session: Session,
    horizon_days: int = 90,
    strategy_name: str | None = None,
    min_conviction: int | None = None,
) -> dict[str, object]:
    decisions = list_investment_decisions(session)
    rows: list[dict[str, object]] = []
    for decision in decisions:
        if strategy_name is not None and decision.strategy_name != strategy_name:
            continue
        if min_conviction is not None and decision.conviction < min_conviction:
            continue

        row = _performance_row(session, decision)
        row["horizon_days"] = horizon_days
        row["horizon_return_percent"] = _return_for_horizon(session, decision, horizon_days)
        rows.append(row)

    grouped = {
        "human_action": _group_evaluation_rows(rows, "action"),
        "engine_recommendation": _group_evaluation_rows(rows, "engine_recommendation"),
        "strategy_name": _group_evaluation_rows(rows, "strategy_name"),
    }
    disagreements = _evaluate_disagreement_buckets(rows)
    valid_returns = [float(row["horizon_return_percent"]) for row in rows if row.get("horizon_return_percent") is not None]
    return {
        "horizon": horizon_days,
        "count": len(rows),
        "available_count": len(valid_returns),
        "decisions": rows,
        "groups": grouped,
        "disagreements": disagreements,
    }
