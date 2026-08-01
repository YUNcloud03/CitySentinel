from app.coordinator.coordinator import DataBundle
from app.coordinator.decision_sandbox import run_decision_sandbox


def test_operator_actions_improve_focus_without_mutating_bundle():
    bundle = DataBundle()
    original = bundle.traffic[0]
    result = run_decision_sandbox(bundle, {
        "name": "方案 A",
        "at": "2026-05-20 22:00",
        "focus_segment_id": "RD_TPE_014",
        "actions": [
            {"type": "extend_green", "segment_id": "RD_TPE_014"},
            {"type": "divert", "segment_id": "RD_TPE_014", "target_segment_id": "RD_TPE_010", "share": .3},
        ],
    })

    assert result["projected_metrics"]["focus_saturation"] < result["baseline_metrics"]["focus_saturation"]
    assert result["production_state_modified"] is False
    assert bundle.traffic[0] is original
    assert len(result["series"]) == 5
    assert result["signal_plan"]["approaches"]
    assert result["evidence_contract"]["simulation"]["model"] == "deterministic-v1"


def test_custom_disruption_can_be_layered_on_a_plan():
    bundle = DataBundle()
    result = run_decision_sandbox(bundle, {
        "name": "方案 B",
        "at": "2026-05-20 22:00",
        "focus_segment_id": "RD_TPE_014",
        "actions": [{"type": "police_control", "segment_id": "RD_TPE_014"}],
        "disruption": "custom_load",
        "disruption_load": 60,
    })

    assert result["disruption"] == "custom_load"
    assert result["projected_metrics"]["focus_saturation"] > result["baseline_metrics"]["focus_saturation"]
