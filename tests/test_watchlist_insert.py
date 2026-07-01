from __future__ import annotations


def test_watchlist_insert_works(client) -> None:
    response = client.post("/watchlist/AAPL")
    assert response.status_code == 200

    watchlist = client.get("/watchlist")
    assert watchlist.status_code == 200
    items = watchlist.json()
    assert any(item["ticker"] == "AAPL" for item in items)

