from __future__ import annotations


def test_price_endpoint_defaults_to_windowed_desc(client) -> None:
    client.post("/ingest/AAPL")
    response = client.get("/stocks/AAPL/prices")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 365
    assert rows[0]["price_date"] >= rows[-1]["price_date"]


def test_score_history_returns_recent_rows(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/score/AAPL")
    client.post("/score/AAPL")

    response = client.get("/stocks/AAPL/scores?limit=2")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert rows[0]["scored_at"] >= rows[1]["scored_at"]
    assert rows[0]["model_versions"]["scoring"] == "0.1.0"
    assert rows[0]["strategy_name"] == rows[1]["strategy_name"]


def test_signal_history_filters(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/signals/AAPL/generate")

    response = client.get("/signals/AAPL/history?signal_name=volatility&signal_category=RISK&limit=10")
    assert response.status_code == 200
    rows = response.json()
    assert rows
    assert all(row["signal_name"] == "volatility" for row in rows)
    assert all(row["signal_category"] == "RISK" for row in rows)


def test_analysis_history_and_compact_mode(client) -> None:
    client.post("/watchlist/AAPL")
    client.post("/ingest/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")
    client.post("/signals/AAPL/generate")
    client.post("/score/AAPL")

    history = client.get("/analysis/AAPL/history?limit=2")
    assert history.status_code == 200
    snapshots = history.json()
    assert len(snapshots) == 2
    assert snapshots[0]["scored_at"] >= snapshots[1]["scored_at"]
    assert snapshots[0]["model_versions"]["scoring"] == "0.1.0"
    assert snapshots[0]["data_sources"]["scores"] == "internal"
    assert snapshots[0]["strategy_name"]

    compact = client.get("/analysis/AAPL?compact=true")
    assert compact.status_code == 200
    payload = compact.json()
    assert payload["ticker"] == "AAPL"
    assert "stock_profile" not in payload
    assert len(payload["positive_signals"]) <= 5
    assert len(payload["negative_signals"]) <= 5
    assert payload["data_sources"]["scores"] == "internal"
