import pytest

from app.coordinator.coordinator import DataBundle
from app.coordinator.green_corridor import corridor_state_at, simulate_green_corridor


def _scenario(**overrides):
    return {
        "at": "2026-05-20 22:00",
        "origin_segment_id": "RD_TPE_015",
        "destination_segment_id": "RD_TPE_007",
        "vehicle_type": "Ambulance",
        "blocked_segment_ids": [],
        **overrides,
    }


def test_green_corridor_is_deterministic_and_non_mutating():
    bundle = DataBundle()
    result = simulate_green_corridor(bundle, _scenario())

    assert result["route_segment_ids"][0] == "RD_TPE_015"
    assert result["route_segment_ids"][-1] == "RD_TPE_007"
    assert result["eta"]["after_minutes"] < result["eta"]["before_minutes"]
    assert result["eta"]["saved_minutes"] > 0
    assert result["signal_actions"]
    assert all(action["action"] == "EMERGENCY_GREEN" for action in result["signal_actions"])
    assert all(action["pedestrian_clearance_seconds"] == 8 for action in result["signal_actions"])
    assert result["approval_status"] == "READY_FOR_APPROVAL"
    assert result["production_state_modified"] is False
    assert result["model"] == "deterministic-green-corridor-v1"


def test_green_corridor_avoids_operator_blocked_segment():
    bundle = DataBundle()
    result = simulate_green_corridor(
        bundle, _scenario(blocked_segment_ids=["RD_TPE_001"])
    )

    assert "RD_TPE_001" not in result["route_segment_ids"]
    assert result["blocked_segment_ids"] == ["RD_TPE_001"]


def test_green_corridor_rejects_invalid_scenario():
    bundle = DataBundle()
    with pytest.raises(KeyError):
        simulate_green_corridor(bundle, _scenario(destination_segment_id="RD_TPE_999"))
    with pytest.raises(ValueError):
        simulate_green_corridor(bundle, _scenario(destination_segment_id="RD_TPE_015"))


def test_rolling_corridor_never_prioritizes_two_intersections():
    result = simulate_green_corridor(DataBundle(), _scenario())
    total = result["runtime_state"]["total_seconds"]
    seen = set()
    for elapsed in range(total + 1):
        state = corridor_state_at(result, elapsed, approved=True)
        active = [row for row in state["intersection_states"] if row["state"] == "EMERGENCY_GREEN"]
        assert len(active) <= 1
        if active:
            seen.add(active[0]["intersection_id"])
    assert len(seen) > 1


def test_corridor_restores_passed_intersection_before_completion():
    result = simulate_green_corridor(DataBundle(), _scenario())
    first = result["runtime_state"]["intersection_states"][0]
    state = corridor_state_at(result, first["passage_at_seconds"] + 1, approved=True)
    first_state = next(row for row in state["intersection_states"] if row["intersection_id"] == first["intersection_id"])
    assert first_state["state"] == "RESTORING"
