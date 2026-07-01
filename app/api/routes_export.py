from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session

from app.db.session import get_session
from app.scoring.strategy_profiles import get_strategy_profile
from app.services.analysis_service import build_analysis_history, build_strategy_rankings
from app.services.stock_service import get_signal_history
from app.services.stock_service import get_stock

router = APIRouter(prefix="/export")


def _csv_response(filename: str, rows: list[dict[str, object]]) -> Response:
    buffer = io.StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    else:
        buffer.write("")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/rankings.csv")
def export_rankings(
    strategy: str = Query(default="balanced"),
    limit: int = Query(default=100, ge=1, le=1000),
    include_signals: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    try:
        selected_strategy = get_strategy_profile(strategy).name
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rankings = build_strategy_rankings(
        session,
        strategy_names=[selected_strategy],
        limit=limit,
        include_signals=include_signals,
    )[selected_strategy]
    rows = []
    for row in rankings:
        export_row = dict(row)
        if include_signals:
            export_row["positive_signals"] = json.dumps(export_row.get("positive_signals", []), default=str)
            export_row["negative_signals"] = json.dumps(export_row.get("negative_signals", []), default=str)
        rows.append(export_row)
    return _csv_response(f"rankings-{selected_strategy}.csv", rows)


@router.get("/signals/{ticker}.csv")
def export_signals(
    ticker: str,
    signal_category: str | None = Query(default=None),
    signal_name: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    signals = get_signal_history(
        session,
        ticker.upper(),
        signal_name=signal_name,
        signal_category=signal_category,
        limit=limit,
    )
    if not signals:
        raise HTTPException(status_code=404, detail="Signals not found")
    rows = [
        {
            "id": row.id,
            "stock_id": row.stock_id,
            "signal_date": row.signal_date,
            "signal_name": row.signal_name,
            "signal_category": row.signal_category,
            "raw_value": row.raw_value,
            "normalized_score": row.normalized_score,
            "severity": row.explanation.get("severity"),
            "weight": row.weight,
            "direction": row.direction,
            "confidence": row.confidence,
            "source": row.source,
            "explanation": row.explanation.get("explanation"),
            "created_at": row.created_at,
        }
        for row in signals
    ]
    return _csv_response(f"{ticker.upper()}-signals.csv", rows)


@router.get("/analysis-history/{ticker}.csv")
def export_analysis_history(
    ticker: str,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    stock = get_stock(session, ticker.upper())
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
    history = build_analysis_history(session, ticker.upper(), limit=limit)
    if not history:
        raise HTTPException(status_code=404, detail="Analysis history not found")
    rows = [
        {
            "ticker": ticker.upper(),
            "scored_at": row["scored_at"],
            "recommendation": row["recommendation"],
            "risk_category": row["risk_category"],
            "risk_score": row["risk_score"],
            "quality_score": row["quality_score"],
            "valuation_score": row["valuation_score"],
            "momentum_score": row["momentum_score"],
            "opportunity_score": row["opportunity_score"],
            "summary": row["summary"],
            "strategy_name": row["strategy_name"],
            "prices_source": row["data_sources"]["prices"],
            "fundamentals_source": row["data_sources"]["fundamentals"],
            "signals_source": row["data_sources"]["signals"],
            "scores_source": row["data_sources"]["scores"],
            "scoring_model_version": row["model_versions"]["scoring"],
            "signal_model_version": row["model_versions"]["signals"],
        }
        for row in history
    ]
    return _csv_response(f"{ticker.upper()}-analysis-history.csv", rows)
