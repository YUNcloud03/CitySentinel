from app.coordinator.closed_loop import evaluate_closed_loop, new_closed_loop, register_replan


def _state():
    event = {"affected_segment": "RD_TPE_001", "review_interval_minutes": 5}
    return {
        "incident_id": "TEST-001",
        "event": event,
        "as_of": "2026-05-20 22:00",
        "operational_status": "IMPACT_ACTIVE",
        "closed_loop": new_closed_loop(event, "2026-05-20 22:00"),
    }


def _view(at: str, saturation: float, *, accepted=False, mitigation=0.0, phase="OBSTACLE_ACTIVE"):
    approved = {"plan_id": "PLAN-A"} if accepted else None
    return {
        "sim_time": at,
        "traffic": {"RD_TPE_001": {"saturation_score": saturation, "avg_speed": 6.0}},
        "simulation_context": {
            "incident_id": "TEST-001",
            "affected_segment_id": "RD_TPE_001",
            "unmitigated_metrics": {
                "RD_TPE_001": {"saturation_score": 1.20, "avg_speed": 5.0}
            },
            "accepted_action_ids": ["ACT-001"] if accepted else [],
            "approved_optimization": approved,
            "mitigation_progress": mitigation,
            "response_phase": phase,
        },
    }


def test_waits_at_human_gate_before_execution():
    state = _state()
    result = evaluate_closed_loop(state, _view("2026-05-20 22:00", 1.20))
    assert result["closed_loop"]["status"] == "AWAITING_COMMANDER_APPROVAL"
    assert result["closed_loop"]["pending_human_gate"] == "APPROVE_EXECUTABLE_PLAN"
    assert not result["replan_required"]


def test_replans_when_review_due_and_kpi_not_met():
    state = _state()
    result = evaluate_closed_loop(
        state, _view("2026-05-20 22:05", 1.18, accepted=True, phase="CLEARANCE_ACTIVE")
    )
    assert result["replan_required"]
    assert result["closed_loop"]["status"] == "REPLAN_REQUIRED"
    register_replan(state, "COMPARE-NEW", "2026-05-20 22:05")
    assert state["closed_loop"]["status"] == "REPLAN_AWAITING_APPROVAL"
    assert state["closed_loop"]["replan_count"] == 1


def test_effective_then_requires_field_confirmation():
    state = _state()
    improved = evaluate_closed_loop(
        state, _view("2026-05-20 22:02", 1.08, accepted=True, mitigation=.3, phase="CLEARANCE_ACTIVE")
    )
    assert improved["closed_loop"]["status"] == "EFFECTIVE_MONITORING"
    cleared = evaluate_closed_loop(
        state, _view("2026-05-20 22:10", .80, accepted=True, mitigation=1, phase="CLEARED")
    )
    assert cleared["closed_loop"]["status"] == "FIELD_CONFIRMATION_REQUIRED"
    assert cleared["closed_loop"]["pending_human_gate"] == "CONFIRM_INCIDENT_CLEARED"
