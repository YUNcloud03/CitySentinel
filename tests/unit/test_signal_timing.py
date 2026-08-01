from app.coordinator.coordinator import DataBundle
from app.data_loader import parse_ts
from app.engines.signal_timing import calculate_signal_plan


def test_signal_timing_is_deterministic_and_conserves_cycle():
    bundle = DataBundle()
    at = parse_ts("2026-05-20 22:00")
    ids = ["RD_TPE_014", "RD_TPE_010"]
    first = calculate_signal_plan(bundle, at, ids)
    second = calculate_signal_plan(bundle, at, ids)
    assert first == second
    assert sum(row["next_green_seconds"] for row in first["approaches"]) == first["green_budget_seconds"]
    assert first["model"] == "deterministic-signal-timing-v1"


def test_signal_timing_respects_safety_and_labels_estimated_wait():
    plan = calculate_signal_plan(
        DataBundle(), parse_ts("2026-05-20 22:00"), ["RD_TPE_014", "RD_TPE_010"]
    )
    for row in plan["approaches"]:
        assert row["next_green_seconds"] >= row["safety_minimum_green_seconds"]
        assert row["next_green_seconds"] <= plan["safety_constraints"]["maximum_green_seconds"]
        assert row["wait_time_source"] == "estimated_from_saturation_not_observed"

