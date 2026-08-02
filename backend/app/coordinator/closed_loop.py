"""Deterministic closed-loop supervision for an active incident.

The Coordinator may observe, verify and re-plan automatically.  Commands that
change traffic control, dispatch resources or notify the public remain behind
one explicit commander approval.  This is a human-on-the-loop controller, not
an unrestricted LLM agent.
"""
from __future__ import annotations

from datetime import timedelta

from ..data_loader import format_ts, parse_ts


SATURATION_IMPROVEMENT_TARGET = 0.08
SPEED_IMPROVEMENT_TARGET_KMH = 3.0
CROWD_REDUCTION_TARGET = 0.10


def new_closed_loop(event: dict, as_of: str) -> dict:
    review_minutes = int(event.get("review_interval_minutes") or 15)
    start = parse_ts(as_of)
    return {
        "mode": "SUPERVISED_CLOSED_LOOP",
        "status": "AWAITING_COMMANDER_APPROVAL",
        "cycle_count": 0,
        "replan_count": 0,
        "review_interval_minutes": review_minutes,
        "next_review_at": format_ts(start + timedelta(minutes=review_minutes)),
        "last_evaluated_at": None,
        "last_transition_at": as_of,
        "pending_human_gate": "APPROVE_EXECUTABLE_PLAN",
        "objectives": {
            "saturation_reduction_min": SATURATION_IMPROVEMENT_TARGET,
            "speed_gain_kmh_min": SPEED_IMPROVEMENT_TARGET_KMH,
            "crowd_reduction_ratio_min": CROWD_REDUCTION_TARGET,
            "field_confirmation_required_for_resolution": True,
        },
        "latest_metrics": None,
        "latest_plan_run_id": None,
        "cycles": [],
        "safety_policy": {
            "automatic": ["observe", "verify_kpi", "replan", "reprioritize_reserved_resources"],
            "approval_required": ["signal_control", "road_diversion", "resource_dispatch", "public_notification"],
            "llm_authority": "TEXT_GENERATION_ONLY",
        },
    }


def evaluate_closed_loop(state: dict, view: dict) -> dict:
    """Evaluate one simulation snapshot and mutate only the incident state."""
    loop = state.setdefault("closed_loop", new_closed_loop(state.get("event", {}), state["as_of"]))
    sim_time = view.get("sim_time")
    if not sim_time or loop.get("last_evaluated_at") == sim_time:
        return {"changed": False, "replan_required": False, "closed_loop": loop}

    context = view.get("simulation_context") or {}
    previous_status = loop["status"]
    previous_metrics = loop.get("latest_metrics") or {}
    metrics: dict = {"sim_time": sim_time, "response_phase": context.get("response_phase")}
    objective_met = False

    segment_id = context.get("affected_segment_id")
    current_traffic = (view.get("traffic") or {}).get(segment_id) if segment_id else None
    unmitigated = (context.get("unmitigated_metrics") or {}).get(segment_id) if segment_id else None
    if current_traffic and unmitigated:
        saturation_reduction = round(
            float(unmitigated["saturation_score"]) - float(current_traffic["saturation_score"]), 3
        )
        speed_gain = round(float(current_traffic["avg_speed"]) - float(unmitigated["avg_speed"]), 1)
        metrics.update({
            "entity_id": segment_id,
            "metric_type": "traffic",
            "current_saturation": current_traffic["saturation_score"],
            "incident_saturation": unmitigated["saturation_score"],
            "saturation_reduction": saturation_reduction,
            "current_speed_kmh": current_traffic["avg_speed"],
            "incident_speed_kmh": unmitigated["avg_speed"],
            "speed_gain_kmh": speed_gain,
        })
        objective_met = (
            saturation_reduction >= SATURATION_IMPROVEMENT_TARGET
            or speed_gain >= SPEED_IMPROVEMENT_TARGET_KMH
        )
    else:
        station_id = state.get("event", {}).get("affected_segment")
        current_crowd = (view.get("crowd") or {}).get(station_id)
        crowd_event = context.get("crowd_unmitigated") or {}
        if current_crowd and crowd_event.get("user_count"):
            reduction = round(
                (float(crowd_event["user_count"]) - float(current_crowd["user_count"]))
                / max(1.0, float(crowd_event["user_count"])), 3
            )
            metrics.update({
                "entity_id": station_id,
                "metric_type": "crowd",
                "current_user_count": current_crowd["user_count"],
                "incident_user_count": crowd_event["user_count"],
                "crowd_reduction_ratio": reduction,
            })
            objective_met = reduction >= CROWD_REDUCTION_TARGET

    mitigation = float(context.get("mitigation_progress") or 0)
    metrics["mitigation_progress"] = round(mitigation, 3)
    metrics["objective_met"] = objective_met
    accepted = bool(
        context.get("accepted_action_ids")
        or context.get("approved_optimization")
        or state.get("approved_optimization")
    )
    now = parse_ts(sim_time)
    review_due = now >= parse_ts(loop["next_review_at"])
    worsened = (
        metrics.get("metric_type") == "traffic"
        and previous_metrics.get("current_saturation") is not None
        and metrics["current_saturation"] >= previous_metrics["current_saturation"] + 0.03
    )

    replan_required = False
    if state.get("operational_status") == "RESOLVED":
        status = "RESOLVED"
        gate = None
    elif context.get("response_phase") == "CLEARED" or mitigation >= 0.999:
        status = "FIELD_CONFIRMATION_REQUIRED"
        gate = "CONFIRM_INCIDENT_CLEARED"
    elif not accepted:
        status = "AWAITING_COMMANDER_APPROVAL"
        gate = "APPROVE_EXECUTABLE_PLAN"
    elif review_due and (worsened or not objective_met):
        status = "REPLAN_REQUIRED"
        gate = None
        replan_required = True
    elif objective_met:
        status = "EFFECTIVE_MONITORING"
        gate = None
    elif context.get("response_phase") == "CLEARANCE_ACTIVE":
        status = "VERIFYING_RESPONSE"
        gate = None
    else:
        status = "EXECUTING_APPROVED_PLAN"
        gate = None

    loop["cycle_count"] += 1
    loop["last_evaluated_at"] = sim_time
    loop["latest_metrics"] = metrics
    loop["status"] = status
    loop["pending_human_gate"] = gate
    if review_due:
        loop["next_review_at"] = format_ts(
            now + timedelta(minutes=loop["review_interval_minutes"])
        )
    if status != previous_status:
        loop["last_transition_at"] = sim_time
    cycle = {
        "cycle": loop["cycle_count"],
        "sim_time": sim_time,
        "from_status": previous_status,
        "to_status": status,
        "objective_met": objective_met,
        "review_due": review_due,
        "worsened": worsened,
        "replan_required": replan_required,
        "metrics": metrics,
    }
    loop["cycles"].append(cycle)
    loop["cycles"] = loop["cycles"][-50:]
    return {
        "changed": status != previous_status or review_due,
        "replan_required": replan_required,
        "cycle": cycle,
        "closed_loop": loop,
    }


def register_replan(state: dict, run_id: str, sim_time: str) -> None:
    loop = state["closed_loop"]
    loop["replan_count"] += 1
    loop["latest_plan_run_id"] = run_id
    loop["status"] = "REPLAN_AWAITING_APPROVAL"
    loop["pending_human_gate"] = "APPROVE_REPLANNED_PACKAGE"
    loop["last_transition_at"] = sim_time
