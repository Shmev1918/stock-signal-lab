from __future__ import annotations


def test_acquisition_routes_create_pause_resume_run_and_estimate(client) -> None:
    create_response = client.post(
        "/acquisition/jobs",
        json={
            "job_name": "polygon_core",
            "provider": "mock",
            "universe_name": "CUSTOM",
            "years": 1,
            "include_prices": True,
            "include_fundamentals": True,
            "include_dividends": True,
            "include_splits": True,
            "include_options": False,
            "start_date": "2026-01-01",
            "end_date": "2026-01-05",
            "config_json": {"tickers": ["AAPL"]},
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    job_id = created["job"]["id"]
    assert created["job"]["status"] == "PENDING"
    assert created["task_total"] == 4

    list_response = client.get("/acquisition/jobs")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == job_id

    pause_response = client.post(f"/acquisition/jobs/{job_id}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["job"]["status"] == "PAUSED"

    run_while_paused = client.post(f"/acquisition/jobs/{job_id}/run")
    assert run_while_paused.status_code == 200
    assert run_while_paused.json()["warnings"][0].startswith("Job is paused")

    resume_response = client.post(f"/acquisition/jobs/{job_id}/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["job"]["status"] == "PENDING"

    run_response = client.post(f"/acquisition/jobs/{job_id}/run")
    assert run_response.status_code == 200
    assert run_response.json()["job"]["status"] == "COMPLETED"
    assert run_response.json()["progress_percent"] == 100.0

    report_response = client.get(f"/acquisition/jobs/{job_id}/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["job"]["id"] == job_id
    assert report["job"]["status"] == "COMPLETED"

    estimate_response = client.get(
        "/acquisition/estimate",
        params={
            "provider": "polygon",
            "universe_name": "STOCK_RESEARCH_CORE",
            "years": 2,
            "include_prices": True,
            "include_fundamentals": True,
            "include_options": False,
            "rate_limit_per_minute": 3,
        },
    )
    assert estimate_response.status_code == 200
    estimate = estimate_response.json()
    assert estimate["provider"] == "polygon"
    assert estimate["estimated_api_calls"] > 0


def test_acquisition_routes_reject_polygon_run_without_live_flag(client) -> None:
    create_response = client.post(
        "/acquisition/jobs",
        json={
            "job_name": "polygon_guard",
            "provider": "polygon",
            "universe_name": "CUSTOM",
            "years": 1,
            "include_prices": True,
            "include_metadata": False,
            "include_fundamentals": False,
            "include_dividends": False,
            "include_splits": False,
            "include_options": False,
            "start_date": "2026-01-01",
            "end_date": "2026-01-05",
            "config_json": {"tickers": ["AAPL"]},
        },
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["job"]["id"]

    run_response = client.post(
        f"/acquisition/jobs/{job_id}/run",
        params={"max_requests": 10, "start_date": "2026-01-01", "end_date": "2026-01-05"},
    )
    assert run_response.status_code == 400
    assert "--live" in run_response.json()["detail"]
