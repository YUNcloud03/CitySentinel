"""Crowd-event playback must react to approved and manually adjusted resources."""
from app.coordinator.coordinator import Coordinator, DataBundle
from app.simulation.player import SimulationPlayer


EVENT = {
    "event_id": "CUSTOM_ATT_CROWD_TEST",
    "type": "Crowd_Surge_Injury",
    "affected_segment": "BS_XY_ATT",
    "status": "Surging",
    "severity": "High",
    "location": "ATT 4 FUN 周邊",
    "description": "5 分鐘人潮增幅達 50%",
    "source_type": "operator",
    "human_confirmed": True,
    "timestamp": "2026-05-20 22:00",
}
OVERRIDES = {
    "user_count": 18_000,
    "growth_rate": 0.5,
    "roaming_user_pct": 35,
    "stay_time_avg": 120,
}


def _scenario(adjust_first: bool = False):
    bundle = DataBundle()
    coordinator = Coordinator(bundle)
    player = SimulationPlayer(bundle)
    state = coordinator.process_incident(EVENT, crowd_overrides=OVERRIDES)
    player.activate_incident(state)
    obstacle = player.seek("2026-05-20 22:30")
    adjusted = False
    for action in state["dispatch"]["actions"]:
        if adjust_first and not adjusted and action["requested_count"] > 1:
            coordinator.dispatch_action(
                state["incident_id"], action["action_id"], "adjust", count=1,
                operator="test_commander", simulation_time="2026-05-20 22:00",
            )
            adjusted = True
        else:
            coordinator.dispatch_action(
                state["incident_id"], action["action_id"], "accept",
                operator="test_commander", simulation_time="2026-05-20 22:00",
            )
    treated = player.seek("2026-05-20 22:30")
    return obstacle, treated


def test_crowd_stays_unmitigated_until_decision_is_approved():
    obstacle, treated = _scenario()
    assert obstacle["crowd"]["BS_XY_ATT"]["user_count"] == 18_000
    assert obstacle["crowd"]["BS_XY_ATT"]["growth_rate"] == 0.5
    assert obstacle["simulation_context"]["response_phase"] == "OBSTACLE_ACTIVE"
    assert obstacle["simulation_context"]["mitigation_progress"] == 0

    assert treated["simulation_context"]["model"] == "deterministic-crowd-response-v1"
    assert treated["simulation_context"]["response_phase"] in {"CLEARANCE_ACTIVE", "CLEARED"}
    assert treated["simulation_context"]["mitigation_progress"] > 0
    assert treated["crowd"]["BS_XY_ATT"]["user_count"] < obstacle["crowd"]["BS_XY_ATT"]["user_count"]
    assert treated["crowd"]["BS_XY_ATT"]["growth_rate"] < obstacle["crowd"]["BS_XY_ATT"]["growth_rate"]


def test_reducing_crowd_resources_slows_h3_input_recovery():
    _, full = _scenario(False)
    _, reduced = _scenario(True)
    assert reduced["simulation_context"]["accepted_action_ratio"] < full["simulation_context"]["accepted_action_ratio"]
    assert reduced["simulation_context"]["mitigation_progress"] < full["simulation_context"]["mitigation_progress"]
    assert reduced["crowd"]["BS_XY_ATT"]["user_count"] > full["crowd"]["BS_XY_ATT"]["user_count"]
    assert reduced["crowd"]["BS_XY_ATT"]["growth_rate"] > full["crowd"]["BS_XY_ATT"]["growth_rate"]
