from fastapi.testclient import TestClient

from app.api.main import app


def test_green_corridor_api_returns_auditable_plan():
    client = TestClient(app)
    client.post("/api/simulation/reset")
    response = client.post("/api/green-corridor/simulate", json={
        "at": "2026-05-20 22:00",
        "origin_segment_id": "RD_TPE_015",
        "destination_segment_id": "RD_TPE_007",
        "vehicle_type": "Ambulance",
        "blocked_segment_ids": ["RD_TPE_001"],
    })

    assert response.status_code == 200
    body = response.json()
    assert body["decision_trace"][-1]["step"] == "HUMAN_APPROVAL_REQUIRED"
    assert body["evidence"]["road_topology_source"] == "road_network_geometry.json"
    assert body["evidence"]["traffic_source"] == "organizer_snapshot"
    assert "saturation_score" in body["evidence"]["route_score_formula"]
    assert body["messages"].keys() == {"zh", "en", "ja", "ko"}
    assert body["dispatch_recommendation"]["requested_units"] >= 1
    assert body["approval_status"] == "READY_FOR_APPROVAL"

    approved = client.post(
        f"/api/green-corridor/{body['scenario_id']}/approve",
        json={"approved_by": "測試指揮官"},
    )
    assert approved.status_code == 200
    approved_body = approved.json()
    assert approved_body["approval_status"] == "APPROVED_FOR_SIMULATION"
    assert approved_body["approved_by"] == "測試指揮官"
    assert approved_body["production_state_modified"] is False
    assert approved_body["decision_trace"][-1]["step"] == "SIMULATION_ACTIVATED"
    runtime = client.get(
        f"/api/green-corridor/{body['scenario_id']}/state?elapsed_seconds=9"
    )
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert len([
        row for row in runtime_body["intersection_states"]
        if row["state"] == "EMERGENCY_GREEN"
    ]) <= 1


def test_green_corridor_uses_active_incident_projection_for_route_cost():
    client = TestClient(app)
    client.post("/api/simulation/reset")
    injected = client.post(
        "/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"}
    )
    assert injected.status_code == 200

    response = client.post("/api/green-corridor/simulate", json={
        "at": injected.json()["event"]["timestamp"],
        "origin_segment_id": "RD_TPE_015",
        "destination_segment_id": "RD_TPE_007",
        "vehicle_type": "Ambulance",
        "blocked_segment_ids": [],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["traffic_source"] == "incident_projection"
    assert body["evidence"]["incident_id"] == "TPE_2026_ACC_001"
    assert "RD_TPE_002" not in body["route_segment_ids"]
