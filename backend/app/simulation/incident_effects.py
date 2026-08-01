"""Deterministic incident projection applied on top of organizer snapshots.

The organizer CSV remains the immutable baseline.  This module returns copied
TrafficRecord values plus an evidence contract; it never mutates source data.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from ..data_loader import TrafficRecord, parse_ts
from ..engines import routing_engine


MODEL_NAME = "deterministic-incident-v1"

SEVERITY_PROFILE = {
    "Critical": {"saturation_delta": 0.38, "speed_loss": 0.78, "queue_gain": 0.18, "diversion_delta": 0.22},
    "High": {"saturation_delta": 0.29, "speed_loss": 0.62, "queue_gain": 0.14, "diversion_delta": 0.17},
    "Medium": {"saturation_delta": 0.19, "speed_loss": 0.43, "queue_gain": 0.10, "diversion_delta": 0.12},
    "Low": {"saturation_delta": 0.10, "speed_loss": 0.24, "queue_gain": 0.06, "diversion_delta": 0.07},
}
STATUS_FACTOR = {"Closed": 1.0, "Blocked": 0.88, "Restricted": 0.64, "Caution": 0.42}
TYPE_FACTOR = {
    "Road_Collapse_Accident": 1.0,
    "Road_Collapse": 1.0,
    "Traffic_Accident": 0.9,
    "Flooding": 0.82,
    "Power_Failure": 0.7,
    "Crowd_Surge_Injury": 0.55,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _affected_road(event: dict, network: dict) -> str | None:
    direct = event.get("affected_segment", "")
    if direct in network and str(direct).startswith("RD_"):
        return direct
    fallback = event.get("affected_road", "")
    return fallback if fallback in network else None


def _replace_traffic(
    record: TrafficRecord,
    *,
    saturation_delta: float,
    speed_factor: float,
    volume_factor: float,
    lane_status: str,
) -> TrafficRecord:
    return replace(
        record,
        saturation_score=round(_clamp(record.saturation_score + saturation_delta, 0.15, 1.25), 3),
        avg_speed=round(_clamp(record.avg_speed * speed_factor, 1.0, 65.0), 1),
        vehicle_count=max(0, round(record.vehicle_count * volume_factor)),
        lane_status=lane_status,
    )


def _blend_toward_baseline(
    baseline: TrafficRecord,
    affected: TrafficRecord,
    mitigation: float,
    lane_status: str,
) -> TrafficRecord:
    """Blend an incident projection back toward its immutable baseline."""
    remaining = 1 - _clamp(mitigation, 0.0, 1.0)
    return replace(
        affected,
        saturation_score=round(baseline.saturation_score + (affected.saturation_score - baseline.saturation_score) * remaining, 3),
        avg_speed=round(baseline.avg_speed + (affected.avg_speed - baseline.avg_speed) * remaining, 1),
        vehicle_count=max(0, round(baseline.vehicle_count + (affected.vehicle_count - baseline.vehicle_count) * remaining)),
        lane_status=lane_status,
    )


def project_incident(
    *,
    at: datetime,
    baseline: dict[str, TrafficRecord],
    incident_state: dict | None,
    network: dict,
) -> tuple[dict[str, TrafficRecord], dict]:
    """Return the projected traffic snapshot and its machine-readable evidence."""
    if not incident_state:
        return baseline, {"active": False, "model": MODEL_NAME}

    event = incident_state.get("event") or {}
    starts_at = parse_ts(incident_state.get("as_of") or event["timestamp"])
    review_interval_minutes = int(event.get("review_interval_minutes") or 15)
    next_review_at = starts_at + timedelta(minutes=review_interval_minutes)
    road_id = _affected_road(event, network)
    resolved_at_text = incident_state.get("resolved_at")
    resolved_at = parse_ts(resolved_at_text) if resolved_at_text else None
    if incident_state.get("operational_status") == "RESOLVED" and resolved_at and at >= resolved_at:
        return baseline, {
            "active": False,
            "model": MODEL_NAME,
            "incident_id": incident_state.get("incident_id"),
            "reason": "resolved_by_human",
            "resolved_at": incident_state.get("resolved_at"),
            "resolution": incident_state.get("resolution"),
        }
    if at < starts_at or road_id is None or road_id not in baseline:
        return baseline, {
            "active": False,
            "model": MODEL_NAME,
            "incident_id": incident_state.get("incident_id"),
            "starts_at": starts_at.strftime("%Y-%m-%d %H:%M"),
            "next_review_at": next_review_at.strftime("%Y-%m-%d %H:%M"),
            "reason": "before_incident" if at < starts_at else "no_road_projection_target",
        }

    elapsed_minutes = max(0.0, (at - starts_at).total_seconds() / 60)
    ramp = min(1.0, 0.55 + elapsed_minutes / 30 * 0.45)
    dispatch_actions = (incident_state.get("dispatch") or {}).get("actions", [])
    accepted_actions_all = [
        action for action in dispatch_actions
        if action.get("status") in {"accepted", "adjusted"}
        and action.get("accepted_sim_time")
        and parse_ts(action["accepted_sim_time"]) <= at
    ]
    on_scene_actions: list[dict] = []
    on_scene_times: list[datetime] = []
    for action in accepted_actions_all:
        assignments = action.get("assignments") or []
        eta_minutes = min((int(row.get("eta_minutes") or 0) for row in assignments), default=0)
        on_scene_at = parse_ts(action["accepted_sim_time"]) + timedelta(minutes=eta_minutes)
        if on_scene_at <= at:
            on_scene_actions.append(action)
            on_scene_times.append(on_scene_at)
    actionable_count = max(1, len([action for action in dispatch_actions if action.get("status") != "rejected"]))
    response_started_at = None
    mitigation_progress = 0.0
    accepted_ratio = len(on_scene_actions) / actionable_count
    if on_scene_actions:
        response_started_at = min(on_scene_times)
        response_elapsed = max(0.0, (at - response_started_at).total_seconds() / 60)
        clearance_minutes = {"Critical": 30, "High": 24, "Medium": 18, "Low": 12}.get(
            event.get("severity"), 18
        )
        time_progress = min(1.0, response_elapsed / clearance_minutes)
        mitigation_progress = min(1.0, time_progress * (0.4 + 0.6 * accepted_ratio))
    response_phase = (
        "CLEARED" if mitigation_progress >= 0.999
        else "CLEARANCE_ACTIVE" if on_scene_actions
        else "DISPATCHING" if accepted_actions_all
        else "OBSTACLE_ACTIVE"
    )
    profile = SEVERITY_PROFILE.get(event.get("severity"), SEVERITY_PROFILE["Medium"])
    incident_factor = (
        STATUS_FACTOR.get(event.get("status"), 0.55)
        * TYPE_FACTOR.get(event.get("type"), 0.75)
        * ramp
    )
    projected = dict(baseline)
    changed: set[str] = set()
    unmitigated_metrics: dict[str, dict] = {}

    direction = event.get("affected_direction", "both")
    lanes_total = max(1, int(event.get("lanes_total") or 2))
    lanes_closed = min(lanes_total, max(0, int(event.get("lanes_closed") or 0)))
    status = event.get("status", "Affected")
    if status == "Closed":
        raw_affected = replace(
            baseline[road_id],
            saturation_score=1.25,
            avg_speed=min(1.0, baseline[road_id].avg_speed),
            vehicle_count=max(0, round(baseline[road_id].vehicle_count * (1 + profile["queue_gain"] * incident_factor))),
            lane_status=f"Closed ({direction}; {lanes_total}/{lanes_total} lanes) · incident projection",
        )
    else:
        raw_affected = _replace_traffic(
            baseline[road_id],
            saturation_delta=profile["saturation_delta"] * incident_factor,
            speed_factor=1 - profile["speed_loss"] * incident_factor,
            volume_factor=1 + profile["queue_gain"] * incident_factor,
            lane_status=f"{status} ({direction}; {lanes_closed}/{lanes_total} lanes) · incident projection",
        )
    response_label = (
        f"Clearance in progress {round(mitigation_progress * 100)}% · incident projection"
        if on_scene_actions else raw_affected.lane_status
    )
    projected[road_id] = _blend_toward_baseline(
        baseline[road_id], raw_affected, mitigation_progress, response_label
    )
    unmitigated_metrics[road_id] = {
        "avg_speed": raw_affected.avg_speed,
        "vehicle_count": raw_affected.vehicle_count,
        "saturation_score": raw_affected.saturation_score,
        "lane_status": raw_affected.lane_status,
    }
    changed.add(road_id)

    dynamic_routing = None
    if incident_state.get("routing_result"):
        initial = routing_engine.plan_evacuation(
            road_id, network, projected, event.get("location")
        )
        load_targets: list[tuple[str, float]] = []
        primary = initial.get("primary_route")
        if primary:
            load_targets.append((primary["segment_id"], 1.0))
        load_targets.extend(
            (row["segment_id"], 0.42) for row in initial.get("secondary_routes", [])
        )
        for target_id, share in load_targets:
            record = projected.get(target_id)
            if record is None or target_id == road_id:
                continue
            load = profile["diversion_delta"] * incident_factor * share * (1 - mitigation_progress)
            raw_diversion = _replace_traffic(
                record,
                saturation_delta=profile["diversion_delta"] * incident_factor * share,
                speed_factor=1 - 0.28 * incident_factor * share,
                volume_factor=1 + 0.16 * incident_factor * share,
                lane_status="Diversion load · incident projection",
            )
            projected[target_id] = _replace_traffic(
                record,
                saturation_delta=load,
                speed_factor=1 - 0.28 * incident_factor * share * (1 - mitigation_progress),
                volume_factor=1 + 0.16 * incident_factor * share * (1 - mitigation_progress),
                lane_status=(
                    f"Diversion easing {round(mitigation_progress * 100)}% · incident projection"
                    if on_scene_actions else "Diversion load · incident projection"
                ),
            )
            unmitigated_metrics[target_id] = {
                "avg_speed": raw_diversion.avg_speed,
                "vehicle_count": raw_diversion.vehicle_count,
                "saturation_score": raw_diversion.saturation_score,
                "lane_status": raw_diversion.lane_status,
            }
            changed.add(target_id)
        dynamic_routing = routing_engine.plan_evacuation(
            road_id, network, projected, event.get("location")
        )

    return projected, {
        "active": True,
        "incident_id": incident_state.get("incident_id"),
        "starts_at": starts_at.strftime("%Y-%m-%d %H:%M"),
        "next_review_at": next_review_at.strftime("%Y-%m-%d %H:%M"),
        "review_overdue": at >= next_review_at,
        "elapsed_minutes": round(elapsed_minutes, 1),
        "model": MODEL_NAME,
        "deterministic": True,
        "baseline_source": "city_traffic_flow.csv",
        "affected_segment_id": road_id,
        "affected_direction": direction,
        "lanes_total": lanes_total,
        "lanes_closed": lanes_total if status == "Closed" else lanes_closed,
        "capacity_factor": round(
            mitigation_progress if status == "Closed"
            else (1 - lanes_closed / lanes_total) + (lanes_closed / lanes_total) * mitigation_progress,
            3,
        ),
        "response_phase": response_phase,
        "response_started_at": response_started_at.strftime("%Y-%m-%d %H:%M") if response_started_at else None,
        "accepted_action_ids": [action["action_id"] for action in accepted_actions_all],
        "on_scene_action_ids": [action["action_id"] for action in on_scene_actions],
        "accepted_action_ratio": round(accepted_ratio, 3),
        "mitigation_progress": round(mitigation_progress, 3),
        "changed_segment_ids": sorted(changed),
        "unmitigated_metrics": unmitigated_metrics,
        "dynamic_routing": dynamic_routing,
        "formula": {
            "intensity": "status_factor × event_type_factor × min(1, 0.55 + elapsed_minutes/30×0.45)",
            "affected": "baseline + severity_profile × intensity",
            "diversion": "primary 100%, secondary 42% of severity diversion load",
        },
        "production_state_modified": False,
    }
