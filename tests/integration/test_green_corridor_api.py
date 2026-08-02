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


def test_auto_rescue_mission_selects_available_ambulance_and_builds_two_legs():
    client = TestClient(app)
    client.post("/api/simulation/reset")
    injected = client.post(
        "/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"}
    )
    assert injected.status_code == 200

    response = client.post("/api/green-corridor/simulate", json={
        "at": injected.json()["event"]["timestamp"],
        "vehicle_type": "Ambulance",
        "blocked_segment_ids": [],
        "auto_dispatch": True,
        "incident_id": "TPE_2026_ACC_001",
    })
    assert response.status_code == 200
    body = response.json()
    mission = body["mission"]
    assert body["model"] == "deterministic-rescue-mission-v3-round-trip"
    assert mission["mode"] == "AUTO_HOSPITAL_ROUND_TRIP"
    assert mission["ambulance"]["unit_id"].startswith("AMB-")
    assert mission["ambulance"]["status"] == "RESERVED_FOR_APPROVAL"
    assert [leg["leg_id"] for leg in mission["legs"]] == ["TO_SCENE", "TO_HOSPITAL"]
    assert mission["legs"][0]["route_segment_ids"][-1] == "RD_TPE_002"
    assert mission["legs"][1]["route_segment_ids"][0] == "RD_TPE_002"
    assert body["evidence"]["hospital_source"].startswith("臺北市政府衛生局")
    assert body["evidence"]["ambulance_inventory_source"] == "demo_sandbox_operations_not_live_119"
    intersection_groups = {}
    for action in body["signal_actions"]:
        key = (action["mission_leg_id"], action["intersection_id"])
        intersection_groups.setdefault(key, []).append(action)
    assert all(
        len({action["execution_id"] for action in actions}) == 1
        for actions in intersection_groups.values()
    )
    assert all(
        action["execution_id"] == f"{action['mission_leg_id']}:{action['intersection_id']}"
        for action in body["signal_actions"]
    )
    assert len(body["runtime_state"]["intersection_states"]) == len(intersection_groups)

    second_assignment = client.post("/api/green-corridor/simulate", json={
        "at": injected.json()["event"]["timestamp"],
        "vehicle_type": "Ambulance",
        "blocked_segment_ids": [],
        "auto_dispatch": True,
        "incident_id": "TPE_2026_ACC_001",
    })
    assert second_assignment.status_code == 200
    second_body = second_assignment.json()
    assert second_body["mission"]["ambulance"]["unit_id"] != mission["ambulance"]["unit_id"]
    assert second_body["scenario_id"] != body["scenario_id"]

    approved = client.post(
        f"/api/green-corridor/{body['scenario_id']}/approve",
        json={"approved_by": "測試指揮官"},
    )
    assert approved.status_code == 200
    assert approved.json()["mission"]["ambulance"]["status"] == "DISPATCHED"

    first_end = mission["legs"][0]["travel_end_seconds"]
    on_scene = client.get(
        f"/api/green-corridor/{body['scenario_id']}/state?elapsed_seconds={first_end + 1}"
    ).json()
    assert on_scene["mission_phase"] == "ON_SCENE"

    second_start = mission["legs"][1]["start_seconds"]
    transporting = client.get(
        f"/api/green-corridor/{body['scenario_id']}/state?elapsed_seconds={second_start + 1}"
    ).json()
    assert transporting["mission_phase"] == "TO_HOSPITAL"
