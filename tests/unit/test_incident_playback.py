from app.coordinator.coordinator import Coordinator, DataBundle
from app.simulation.player import SimulationPlayer


def _active_player():
    bundle = DataBundle()
    coordinator = Coordinator(bundle)
    player = SimulationPlayer(bundle)
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    player.activate_incident(state)
    return player


def test_incident_projection_changes_map_snapshot_and_preserves_baseline():
    player = _active_player()
    view = player.seek("2026-05-20 22:10")
    context = view["simulation_context"]
    affected = view["traffic"]["RD_TPE_002"]

    assert context["active"] is True
    assert context["model"] == "deterministic-incident-v1"
    assert context["baseline_source"] == "city_traffic_flow.csv"
    assert "RD_TPE_002" in context["changed_segment_ids"]
    assert affected["simulation_source"] == "incident_projection"
    assert affected["avg_speed"] < affected["baseline_avg_speed"]
    assert affected["saturation_score"] > affected["baseline_saturation_score"]


def test_incident_projection_recalculates_route_and_is_replayable():
    player = _active_player()
    first = player.seek("2026-05-20 22:10")
    second = player.seek("2026-05-20 22:10")

    route = first["simulation_context"]["dynamic_routing"]
    assert route["primary_route"]["segment_id"] == "RD_TPE_004"
    assert first["traffic"] == second["traffic"]
    assert first["simulation_context"]["changed_segment_ids"] == second["simulation_context"]["changed_segment_ids"]
    assert first["scenario_comparison"] == second["scenario_comparison"]


def test_scenario_comparison_is_backend_owned_and_treatment_starts_locked():
    player = _active_player()
    comparison = player.seek("2026-05-20 22:10")["scenario_comparison"]

    assert comparison["simulation_run_id"].startswith("COMPARE-")
    assert len(comparison["input_sha256"]) == 64
    assert comparison["randomness_used"] is False
    assert comparison["scenarios"]["baseline"]["ete"] is None
    assert comparison["scenarios"]["incident"]["ete"]["formula"].startswith("ETE = ")
    assert comparison["scenarios"]["treatment"]["available"] is False
    assert comparison["scenarios"]["treatment"]["metrics"] is None
    assert "尚未核准" in comparison["scenarios"]["treatment"]["locked_reason"]


def test_seeking_before_incident_returns_organizer_baseline():
    player = _active_player()
    view = player.seek("2026-05-20 21:00")

    assert view["simulation_context"]["active"] is False
    assert view["simulation_context"]["reason"] == "before_incident"
    assert all(row["simulation_source"] == "organizer_dataset" for row in view["traffic"].values())


def test_closed_custom_incident_persists_until_human_resolution():
    bundle = DataBundle()
    coordinator = Coordinator(bundle)
    player = SimulationPlayer(bundle)
    state = coordinator.process_incident({
        "event_id": "CUSTOM-CLOSED", "type": "Road_Collapse",
        "affected_segment": "RD_TPE_003", "location": "基隆路一段",
        "status": "Closed", "severity": "High", "timestamp": "2026-05-20 22:00",
        "affected_direction": "northbound", "lanes_total": 3, "lanes_closed": 3,
        "review_interval_minutes": 15, "description": "道路完全封閉",
    })
    player.activate_incident(state)

    active = player.seek("2026-05-20 22:10")
    affected = active["traffic"]["RD_TPE_003"]
    assert active["simulation_context"]["capacity_factor"] == 0
    assert active["simulation_context"]["affected_direction"] == "northbound"
    assert affected["avg_speed"] == 1.0
    assert affected["saturation_score"] == 1.25

    overdue = player.seek("2026-05-20 22:30")
    assert overdue["simulation_context"]["active"] is True
    assert overdue["simulation_context"]["review_overdue"] is True

    coordinator.resolve_incident(
        state["incident_id"], operator="field_commander", reason="現場確認排除",
        simulation_time="2026-05-20 22:30",
    )
    resolved = player.seek("2026-05-20 22:30")
    assert resolved["simulation_context"]["active"] is False
    assert resolved["simulation_context"]["reason"] == "resolved_by_human"
    historical = player.seek("2026-05-20 22:10")
    assert historical["simulation_context"]["active"] is True


def test_clearance_starts_only_after_decision_acceptance_and_improves_over_time():
    bundle = DataBundle()
    coordinator = Coordinator(bundle)
    player = SimulationPlayer(bundle)
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    player.activate_incident(state)

    obstacle = player.seek("2026-05-20 22:10")
    obstacle_speed = obstacle["traffic"]["RD_TPE_002"]["avg_speed"]
    assert obstacle["simulation_context"]["response_phase"] == "OBSTACLE_ACTIVE"
    assert all(action["allocation_state"] == "reserved" for action in state["dispatch"]["actions"])

    for action in state["dispatch"]["actions"]:
        coordinator.dispatch_action(
            state["incident_id"], action["action_id"], "accept",
            operator="test_commander", simulation_time="2026-05-20 22:00",
        )
    improving = player.seek("2026-05-20 22:10")
    assert improving["simulation_context"]["response_phase"] == "CLEARANCE_ACTIVE"
    assert improving["simulation_context"]["mitigation_progress"] > 0
    assert improving["traffic"]["RD_TPE_002"]["avg_speed"] > obstacle_speed
    assert all(action["allocation_state"] == "committed" for action in state["dispatch"]["actions"])
    comparison = improving["scenario_comparison"]
    treatment = comparison["scenarios"]["treatment"]
    assert treatment["available"] is True
    assert treatment["effect_started"] is True
    assert treatment["ete"]["ete_minutes"] < comparison["scenarios"]["incident"]["ete"]["ete_minutes"]

    later = player.seek("2026-05-20 22:30")
    assert later["simulation_context"]["mitigation_progress"] > improving["simulation_context"]["mitigation_progress"]
    assert later["traffic"]["RD_TPE_002"]["avg_speed"] >= later["traffic"]["RD_TPE_002"]["event_avg_speed"]
    assert later["traffic"]["RD_TPE_002"]["saturation_score"] <= later["traffic"]["RD_TPE_002"]["event_saturation_score"]
