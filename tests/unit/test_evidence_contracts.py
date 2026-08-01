import pytest

from app.coordinator.coordinator import DataBundle
from app.coordinator.decision_sandbox import run_decision_sandbox
from app.coordinator.whatif import run_what_if


def test_whatif_replay_has_stable_evidence_hashes():
    bundle = DataBundle()
    scenario = {"at": "2026-05-20 22:00", "traffic_overrides": {
        "RD_TPE_014": {"saturation_score": 0.9}
    }}
    first, second = run_what_if(bundle, scenario), run_what_if(bundle, scenario)
    assert first["simulation_run_id"] == second["simulation_run_id"]
    assert first["evidence_contract"] == second["evidence_contract"]


def test_whatif_rejects_unknown_ids_instead_of_silently_ignoring():
    with pytest.raises(KeyError, match="RD_TPE_999"):
        run_what_if(DataBundle(), {"at": "2026-05-20 22:00",
                                  "traffic_overrides": {"RD_TPE_999": {"saturation_score": 1}}})


def test_decision_sandbox_attaches_baseline_and_scenario_hashes():
    result = run_decision_sandbox(DataBundle(), {
        "name": "方案證據測試", "at": "2026-05-20 22:00",
        "focus_segment_id": "RD_TPE_014",
        "actions": [{"type": "extend_green", "segment_id": "RD_TPE_014"}],
    })
    evidence = result["evidence_contract"]
    assert len(evidence["baseline_snapshot_sha256"]) == 64
    assert len(evidence["scenario_sha256"]) == 64
    assert result["simulation_run_id"].startswith("DECISION-")
