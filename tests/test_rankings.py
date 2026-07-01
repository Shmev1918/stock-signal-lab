from __future__ import annotations


def test_rankings_returns_scored_stocks(client) -> None:
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        client.post(f"/watchlist/{ticker}")
        client.post(f"/ingest/{ticker}")
        client.post(f"/score/{ticker}")

    response = client.get("/rankings")
    assert response.status_code == 200
    rows = response.json()
    assert rows
    assert rows == sorted(rows, key=lambda row: row["opportunity_score"], reverse=True)

