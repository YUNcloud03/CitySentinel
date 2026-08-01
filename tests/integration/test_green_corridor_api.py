from fastapi.testclient import TestClient

from app.api.main import app


def test_green_corridor_api_returns_auditable_plan():
    client = TestClient(app)
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
