from __future__ import annotations

import csv
import io


def _seed_analysis_data(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")


def test_rankings_csv_export(client) -> None:
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        client.post(f"/watchlist/{ticker}")
        client.post(f"/ingest/{ticker}")
        client.post(f"/score/{ticker}")

    response = client.get("/export/rankings.csv?strategy=value_recovery&limit=2")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in response.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert {"rank", "ticker", "recommendation", "risk_category", "opportunity_score"} <= set(rows[0])


def test_rankings_csv_include_signals(client) -> None:
    for ticker in ["AAPL", "MSFT"]:
        client.post(f"/watchlist/{ticker}")
        client.post(f"/ingest/{ticker}")
        client.post(f"/score/{ticker}")

    response = client.get("/export/rankings.csv?strategy=balanced&include_signals=true")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows
    assert "positive_signals" in rows[0]
    assert "negative_signals" in rows[0]


def test_signals_csv_export_filters(client) -> None:
    _seed_analysis_data(client)

    response = client.get("/export/signals/AAPL.csv?signal_category=RISK&signal_name=volatility&limit=5")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows
    assert all(row["signal_category"] == "RISK" for row in rows)
    assert all(row["signal_name"] == "volatility" for row in rows)


def test_analysis_history_csv_export(client) -> None:
    _seed_analysis_data(client)

    response = client.get("/export/analysis-history/AAPL.csv?limit=2")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert {"scored_at", "recommendation", "risk_category", "summary", "strategy_name"} <= set(rows[0])


def test_csv_export_content_type_and_download_header(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/score/AAPL")

    response = client.get("/export/signals/AAPL.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith("attachment;")
