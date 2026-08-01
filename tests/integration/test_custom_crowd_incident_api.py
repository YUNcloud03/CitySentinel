"""Custom crowd-event parameters must affect a copied simulation snapshot."""
from fastapi.testclient import TestClient

from app.api.main import app


def test_custom_crowd_event_triggers_rules_and_updates_playback_snapshot():
    client = TestClient(app)
    client.post("/api/simulation/reset")
    stations = client.get("/api/crowd-stations")
    assert stations.status_code == 200
    assert any(row["station_id"] == "BS_MRT_BL17" for row in stations.json())

    response = client.post("/api/incidents/custom", json={
        "type": "Crowd_Surge_Injury",
        "affected_segment": "BS_MRT_BL17",
        "status": "Surging",
        "severity": "High",
        "location": "捷運國父紀念館站",
        "description": "五分鐘內人潮快速增加",
        "source_type": "operator",
        "human_confirmed": True,
        "timestamp": "2026-05-20 22:00",
        "crowd_user_count_override": 30_000,
        "crowd_growth_rate_override": 0.5,
        "crowd_roaming_user_pct_override": 35,
        "crowd_stay_time_avg_override": 45,
    })
    assert response.status_code == 200
    state = response.json()
    assert 3 in state["triggered_rules"]
    assert 3 in state["rule_attribution"]["caused_by_incident"]
    assumption = next(row for row in state["assumptions"] if row["field"] == "crowd_snapshot")
    assert assumption["station_id"] == "BS_MRT_BL17"
    assert assumption["applied"]["growth_rate"] == 0.5

    view = client.post("/api/simulation/seek", json={"timestamp": "2026-05-20 22:00"})
    assert view.status_code == 200
    body = view.json()
    assert body["simulation_context"]["model"] == "deterministic-crowd-response-v1"
    assert body["simulation_context"]["affected_station_id"] == "BS_MRT_BL17"
    assert body["crowd"]["BS_MRT_BL17"]["user_count"] == 30_000
    assert body["crowd"]["BS_MRT_BL17"]["growth_rate"] == 0.5
    assert body["crowd"]["BS_MRT_BL17"]["roaming_user_pct"] == 35


def test_custom_crowd_event_rejects_road_target():
    client = TestClient(app)
    response = client.post("/api/incidents/custom", json={
        "type": "Crowd_Surge_Injury",
        "affected_segment": "RD_TPE_001",
        "status": "Surging",
        "severity": "High",
        "timestamp": "2026-05-20 22:00",
    })
    assert response.status_code == 422


def test_att_crowd_growth_produces_venue_decision_without_mrt_bypass():
    client = TestClient(app)
    client.post("/api/simulation/reset")
    response = client.post("/api/incidents/custom", json={
        "type": "Crowd_Surge_Injury",
        "affected_segment": "BS_XY_ATT",
        "status": "Surging",
        "severity": "High",
        "location": "ATT 4 FUN 周邊",
        "description": "5 分鐘人潮增幅達 50%",
        "source_type": "operator",
        "human_confirmed": True,
        "timestamp": "2026-05-20 22:00",
        "crowd_user_count_override": 18_000,
        "crowd_growth_rate_override": 0.5,
        "crowd_roaming_user_pct_override": 20,
        "crowd_stay_time_avg_override": 110,
    })
    assert response.status_code == 200
    state = response.json()
    assert 3 in state["rule_attribution"]["caused_by_incident"]
    assert state["dispatch"] is not None
    assert all(
        action["resource_type"] != "MRTLiaison"
        for action in state["dispatch"]["actions"]
    )
    assert "場館出入口" in state["coordinator_summary"]["recommendation"]
    assert "過站不停" not in state["coordinator_summary"]["recommendation"]
    policy = next(row for row in state["sop_evidence"] if row["rule_id"] == 3)
    assert policy["title"] == "單站人潮異常分流政策"
    assert policy["source"] == "competition_requirement"
