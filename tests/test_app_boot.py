from __future__ import annotations


def test_app_boots(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_details(client) -> None:
    response = client.get("/health/details")
    assert response.status_code == 200
    payload = response.json()
    assert payload["database_reachable"] is True
    assert payload["active_provider"] in {"mock", "yfinance"}
    assert payload["default_scoring_strategy"] == "balanced"
    assert payload["scoring_model_version"] == "0.1.0"
    assert payload["signal_model_version"] == "0.1.0"
