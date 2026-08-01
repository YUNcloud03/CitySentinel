"""Deterministic plan-comparison and replay API contract tests."""
from datetime import timedelta

from fastapi.testclient import TestClient

from app.api import main as api_main
from app.data_loader import parse_ts
from app.simulation.incident_effects import project_incident


def _inject(client: TestClient) -> str:
    client.post("/api/simulation/reset")
    response = client.post(
        "/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"}
    )
    assert response.status_code == 200
    return response.json()["incident_id"]


def test_plan_comparison_has_traceable_same_schema_plans_and_replay():
    client = TestClient(api_main.app)
    incident_id = _inject(client)

    response = client.post(
        "/api/simulation/plan-comparison",
        json={"incident_id": incident_id, "random_seed": 42},
    )
    assert response.status_code == 200
    run = response.json()

    assert run["scenario_id"] == incident_id
    assert run["randomness_used"] is False
    assert run["simulation_config"]["random_seed"] == 42
    assert run["model_version"] == "constrained-rolling-optimizer-v2"
    assert set(run["dataset_versions"]) == {
        "traffic", "crowd", "road_network", "incidents", "sop"
    }
    assert all(value.startswith("sha256:") for value in run["dataset_versions"].values())

    plans = {row["plan_id"]: row for row in run["plans"]}
    assert set(plans) == {"BASELINE", "OPT_001", "OPT_002", "OPT_003"}
    assert run["recommended_plan_id"] == "OPT_001"
    assert run["optimizer"]["evaluated_candidate_count"] > len(plans)
    assert run["optimizer"]["eligible_candidate_count"] >= 3
    assert plans["BASELINE"]["state"] == "UNMITIGATED_REFERENCE"
    assert plans["OPT_001"]["state"] == "OPTIMIZED_READY_FOR_APPROVAL"
    assert all(row["passed"] for row in plans["OPT_001"]["constraints"])
    assert plans["OPT_001"]["executable_commands"]
    assert plans["OPT_001"]["forecast_series"][-1]["minute"] == 20
    assert plans["OPT_001"]["kpis"].keys() == plans["OPT_003"]["kpis"].keys()
    assert plans["OPT_001"]["kpis"]["crowd_evacuation_minutes"] is None
    assert plans["OPT_001"]["kpis"]["pedestrian_service"].startswith("NOT_MEASURED")

    replay = client.post(
        f"/api/simulation/plan-comparison/{run['simulation_run_id']}/replay"
    )
    assert replay.status_code == 200
    assert replay.json()["matches"] is True
    assert replay.json()["replay_output_sha256"] == run["output_sha256"]


def test_same_input_and_seed_produces_same_hash():
    client = TestClient(api_main.app)
    incident_id = _inject(client)
    payload = {"incident_id": incident_id, "random_seed": 42}
    first = client.post("/api/simulation/plan-comparison", json=payload).json()
    second = client.post("/api/simulation/plan-comparison", json=payload).json()
    assert first["input_sha256"] == second["input_sha256"]
    assert first["output_sha256"] == second["output_sha256"]
    assert first["simulation_run_id"] == second["simulation_run_id"]


def test_plan_comparison_rejects_unknown_incident():
    client = TestClient(api_main.app)
    client.post("/api/simulation/reset")
    response = client.post(
        "/api/simulation/plan-comparison", json={"incident_id": "UNKNOWN"}
    )
    assert response.status_code == 404


def test_manual_challenge_uses_same_constraints_and_can_be_rejected():
    client = TestClient(api_main.app)
    incident_id = _inject(client)
    response = client.post("/api/simulation/plan-comparison", json={
        "incident_id": incident_id,
        "manual_controls": {
            "green_extension_pct": 25,
            "diversion_share": .75,
            "police_units": 12,
        },
    })
    assert response.status_code == 200
    manual = next(row for row in response.json()["plans"] if row["plan_id"] == "MANUAL")
    assert manual["state"] == "MANUAL_CHALLENGE_EVALUATED"
    assert manual["eligible"] is False
    assert any(not row["passed"] for row in manual["constraints"])


def test_approved_optimized_plan_becomes_active_simulation_control():
    client = TestClient(api_main.app)
    incident_id = _inject(client)
    state = api_main.coordinator.incident_states[incident_id]
    event_at = parse_ts(state["event"]["timestamp"])
    comparison_at = event_at + timedelta(minutes=5)
    baseline = api_main.bundle.traffic_at(comparison_at)
    before, _ = project_incident(
        at=comparison_at, baseline=baseline, incident_state=state,
        network=api_main.bundle.network,
    )
    run = client.post("/api/simulation/plan-comparison", json={"incident_id": incident_id}).json()
    approval = client.post(
        f"/api/simulation/plan-comparison/{run['simulation_run_id']}/approve",
        json={"plan_id": run["recommended_plan_id"], "approved_by": "測試指揮官"},
    )
    assert approval.status_code == 200
    assert approval.json()["approval_status"] == "APPROVED_FOR_SIMULATION"
    assert state["approved_optimization"]["plan_id"] == run["recommended_plan_id"]
    assert state["approved_optimization"]["commands"]
    assert state["decision_trace"][-1]["step"] == "OPTIMIZED_PLAN_APPROVED"
    after, context = project_incident(
        at=comparison_at, baseline=baseline, incident_state=state,
        network=api_main.bundle.network,
    )
    focus_id = state["event"]["affected_segment"]
    assert after[focus_id].saturation_score < before[focus_id].saturation_score
    primary_id = run["route_evidence"]["primary_route"]["segment_id"]
    assert after[primary_id].saturation_score < before[primary_id].saturation_score
    assert context["optimization_control_progress"] == 1.0
