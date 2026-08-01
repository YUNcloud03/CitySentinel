"""Simulation lifecycle reset API integration tests."""
from fastapi.testclient import TestClient

from app.api import main as api_main


def test_reset_clears_runtime_state_and_restores_baseline():
    client = TestClient(api_main.app)

    incident = client.post(
        "/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"}
    )
    assert incident.status_code == 200
    assert client.get("/api/notifications").json()

    corridor = client.post("/api/green-corridor/simulate", json={
        "at": "2026-05-20 22:00",
        "origin_segment_id": "RD_TPE_015",
        "destination_segment_id": "RD_TPE_007",
        "vehicle_type": "Ambulance",
        "blocked_segment_ids": ["RD_TPE_001"],
    })
    assert corridor.status_code == 200

    response = client.post("/api/simulation/reset")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reset"
    assert body["baseline_timestamp"] == "2026-05-20 21:00"
    assert body["view"]["playing"] is False
    assert body["view"]["scenario_comparison"] is None
    assert body["view"]["simulation_context"]["active"] is False
    assert body["cleared"]["incidents"] >= 1
    assert body["cleared"]["notifications"] >= 1
    assert body["cleared"]["green_corridors"] >= 1

    assert client.get("/api/incidents").json()["processed"] == []
    assert client.get("/api/notifications").json() == []
    assert client.get("/api/green-corridor/runs").json() == []
    assert client.get("/api/simulation-runs").json() == []
    resources = client.get("/api/resources").json()
    assert all(row["available_count"] == row["total_count"] for row in resources)


def test_reset_is_idempotent():
    client = TestClient(api_main.app)
    first = client.post("/api/simulation/reset")
    second = client.post("/api/simulation/reset")
    assert first.status_code == second.status_code == 200
    assert second.json()["cleared"] == {
        "incidents": 0,
        "notifications": 0,
        "green_corridors": 0,
        "custom_runs": 0,
        "llm_audit_entries": 0,
    }
    assert second.json()["view"]["sim_time"] == "2026-05-20 21:00"
