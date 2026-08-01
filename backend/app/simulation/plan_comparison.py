"""Deterministic constrained traffic-control optimization with replay evidence.

The organizer snapshots remain immutable. Every coefficient used below is
versioned and returned to the caller; no LLM participates in calculations.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json

from ..config import CROWD_CSV, INCIDENTS_JSON, ROAD_NETWORK_JSON, SOP_TXT, TRAFFIC_CSV
from ..data_loader import parse_ts
from ..engines.ete_calculator import calculate_ete
from ..engines.rule_engine import classify_congestion
from ..engines.signal_timing import calculate_signal_plan
from .incident_effects import project_incident


MODEL_VERSION = "constrained-rolling-optimizer-v2"
CONTROLLER_VERSION = "signal-routing-resource-mpc-v2.0"
DEFAULT_CONFIG = {
    "step_seconds": 5,
    "horizon_minutes": 20,
    "random_seed": 42,
    "controller_version": CONTROLLER_VERSION,
}
GREEN_EXTENSION_OPTIONS = (0, 10, 20, 25)
DIVERSION_SHARE_OPTIONS = (0.0, 0.25, 0.50, 0.75)


def _sha256_file(path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _resource_limit(incident_state: dict, resource_type: str) -> int:
    return sum(
        int(action.get("fulfilled_count") or 0)
        for action in (incident_state.get("dispatch") or {}).get("actions", [])
        if action.get("resource_type") == resource_type
    )


def _signal_commands(signal_plan: dict | None, focus_id: str, extension_pct: int) -> tuple[list[dict], bool]:
    if extension_pct <= 0:
        return [], True
    if not signal_plan:
        return [], False
    approaches = [dict(row) for row in signal_plan["approaches"]]
    focus = next((row for row in approaches if row["segment_id"] == focus_id), None)
    if focus is None:
        return [], False
    target = min(50, round(focus["next_green_seconds"] * (1 + extension_pct / 100)))
    needed = target - focus["next_green_seconds"]
    if needed <= 0:
        return [], True
    donors = sorted(
        (row for row in approaches if row["segment_id"] != focus_id),
        key=lambda row: row["next_green_seconds"] - row["safety_minimum_green_seconds"],
        reverse=True,
    )
    remaining = needed
    for donor in donors:
        available = max(0, donor["next_green_seconds"] - donor["safety_minimum_green_seconds"])
        take = min(available, remaining)
        donor["next_green_seconds"] -= take
        remaining -= take
    if remaining > 0:
        return [], False
    focus["next_green_seconds"] = target
    return [{
        "command": "SET_SIGNAL_TIMING",
        "segment_id": row["segment_id"],
        "segment_name": row["name"],
        "green_seconds": row["next_green_seconds"],
        "minimum_green_seconds": row["safety_minimum_green_seconds"],
        "cycle_seconds": signal_plan["cycle_seconds"],
    } for row in approaches], True


def _apply_controls(
    traffic, focus_id: str, diversion_id: str | None, controls: dict,
    network: dict, signal_plan: dict | None, incident_state: dict, at, horizon_minutes: int,
):
    result = dict(traffic)
    focus = result[focus_id]
    green_pct = int(controls["green_extension_pct"])
    diversion_share = float(controls["diversion_share"])
    police_units = int(controls["police_units"])
    police_limit = _resource_limit(incident_state, "Police")
    signal_limit = _resource_limit(incident_state, "SignalControl")
    signal_commands, signal_safe = _signal_commands(signal_plan, focus_id, green_pct)
    constraints = [
        {"code": "POLICE_AVAILABLE", "passed": police_units <= police_limit,
         "detail": f"需求 {police_units}／可核配 {police_limit}"},
        {"code": "SIGNAL_CONTROL_AVAILABLE", "passed": green_pct == 0 or signal_limit > 0,
         "detail": f"綠燈延長 {green_pct}%／號誌控制可用 {signal_limit}"},
        {"code": "PEDESTRIAN_MIN_GREEN", "passed": signal_safe,
         "detail": "調整後各方向仍須高於行人安全綠燈下限"},
        {"code": "DIVERSION_ROUTE_AVAILABLE", "passed": diversion_share == 0 or diversion_id is not None,
         "detail": f"引流 {round(diversion_share * 100)}%／替代路段 {diversion_id or '無'}"},
    ]
    relief = 0.0032 * green_pct + 0.22 * diversion_share + 0.025 * police_units
    speed_gain = 1 + 0.006 * green_pct + 0.28 * diversion_share + 0.04 * police_units
    result[focus_id] = replace(
        focus,
        saturation_score=round(_clamp(focus.saturation_score - relief, .15, 1.25), 3),
        avg_speed=round(_clamp(focus.avg_speed * speed_gain, 1, 65), 1),
        lane_status="optimized control forecast · deterministic simulation",
    )
    if diversion_share > 0 and diversion_id and diversion_id in result:
        row = result[diversion_id]
        moved_vehicles = round(focus.vehicle_count * diversion_share)
        diversion_capacity = max(1, network[diversion_id].capacity_vph)
        load_delta = moved_vehicles / diversion_capacity * 0.45
        result[diversion_id] = replace(
            row,
            saturation_score=round(_clamp(row.saturation_score + load_delta, .15, 1.25), 3),
            avg_speed=round(_clamp(row.avg_speed * (1 - min(.35, load_delta * .4)), 1, 65), 1),
            vehicle_count=row.vehicle_count + moved_vehicles,
            lane_status="controlled diversion load · deterministic simulation",
        )
        constraints.append({
            "code": "DIVERSION_CAPACITY",
            "passed": result[diversion_id].saturation_score <= 1.05,
            "detail": f"{network[diversion_id].name} 預測飽和度 {result[diversion_id].saturation_score} ≤ 1.05",
        })
    commands = signal_commands[:]
    if diversion_share > 0 and diversion_id:
        commands.append({"command": "DIVERT_TRAFFIC", "from_segment_id": focus_id,
                         "to_segment_id": diversion_id, "share_pct": round(diversion_share * 100)})
        commands.append({"command": "SET_CMS_MESSAGE", "target_segment_id": focus_id,
                         "message": f"前方事件，請依指示改道 {network[diversion_id].name}"})
    if police_units > 0:
        commands.append({"command": "DISPATCH_RESOURCE", "resource_type": "Police",
                         "units": police_units, "target_segment_id": focus_id})
    commands.append({"command": "REOPTIMIZE", "after_minutes": 5})
    for command in commands:
        command["effective_from"] = at.strftime("%Y-%m-%d %H:%M")
        command["effective_minutes"] = horizon_minutes
    forecast = []
    for minute in range(0, horizon_minutes + 1, 5):
        progress = minute / max(1, horizon_minutes)
        forecast.append({
            "minute": minute,
            "focus_saturation": round(focus.saturation_score + (result[focus_id].saturation_score - focus.saturation_score) * progress, 3),
            "focus_speed_kmh": round(focus.avg_speed + (result[focus_id].avg_speed - focus.avg_speed) * progress, 1),
        })
    return result, constraints, commands, forecast


def _estimated_wait(saturation: float) -> float:
    return round(10 + 50 * _clamp(saturation, 0, 1), 1)


def _kpis(traffic, focus_id: str, incident_state: dict, incident_reference=None) -> dict:
    rows = list(traffic.values())
    waits = [_estimated_wait(row.saturation_score) for row in rows]
    focus = traffic[focus_id]
    assignments = [
        assignment
        for action in (incident_state.get("dispatch") or {}).get("actions", [])
        for assignment in (action.get("assignments") or [])
    ]
    base_resource_eta = min((int(row.get("eta_minutes") or 0) for row in assignments), default=8)
    emergency_eta = round(base_resource_eta + 6 * _clamp(focus.saturation_score, 0, 1.25), 1)
    max_queue = max(
        (round(row.vehicle_count * _clamp(row.saturation_score, 0, 1.25) * .08) for row in rows),
        default=0,
    )
    congested = sum(row.saturation_score >= .85 for row in rows)
    side_effect = 0.0
    if incident_reference:
        other_ids = [key for key in traffic if key != focus_id and key in incident_reference]
        if other_ids:
            side_effect = round(sum(
                _estimated_wait(traffic[key].saturation_score)
                - _estimated_wait(incident_reference[key].saturation_score)
                for key in other_ids
            ) / len(other_ids), 1)
    severity = (incident_state.get("event") or {}).get("severity")
    ete = calculate_ete(severity, [focus.saturation_score]) if severity else None
    return {
        "emergency_eta_minutes": emergency_eta,
        "average_vehicle_wait_seconds": round(sum(waits) / max(1, len(waits)), 1),
        "maximum_queue_vehicles": max_queue,
        "congested_segment_count": congested,
        "crowd_evacuation_minutes": None,
        "pedestrian_service": "NOT_MEASURED_NO_DIRECTIONAL_PEDESTRIAN_SENSOR",
        "control_side_effect_wait_seconds": side_effect,
        "focus_speed_kmh": focus.avg_speed,
        "focus_saturation": focus.saturation_score,
        "ete_minutes": ete["ete_minutes_display"] if ete else None,
    }


def _traffic_payload(traffic) -> dict:
    return {
        key: {
            "road_name": row.road_name,
            "avg_speed": row.avg_speed,
            "vehicle_count": row.vehicle_count,
            "saturation_score": row.saturation_score,
            "lane_status": row.lane_status,
            "congestion_level": classify_congestion(row.saturation_score),
        }
        for key, row in sorted(traffic.items())
    }


def build_plan_comparison(bundle, incident_state: dict, config: dict | None = None) -> dict:
    event = incident_state["event"]
    at = parse_ts(event["timestamp"])
    focus_id = event.get("affected_segment")
    if focus_id not in bundle.network:
        raise KeyError(f"事件路段 {focus_id} 不存在於 authoritative road network")
    merged_config = {**DEFAULT_CONFIG, **(config or {})}
    baseline = bundle.traffic_at(at)
    incident, context = project_incident(
        at=at,
        baseline=baseline,
        incident_state=incident_state,
        network=bundle.network,
    )
    routing = context.get("dynamic_routing") or incident_state.get("routing_result") or {}
    primary = routing.get("primary_route") or {}
    diversion_id = primary.get("segment_id")

    candidate_ids = [focus_id]
    if diversion_id:
        candidate_ids.append(diversion_id)
    candidate_ids.extend(
        row["segment_id"] for row in routing.get("secondary_routes", [])
        if row.get("segment_id")
    )
    signal_plan = None
    signal_ids = list(dict.fromkeys(candidate_ids))[:4]
    if len(signal_ids) >= 2:
        signal_plan = calculate_signal_plan(bundle, at, signal_ids)

    police_limit = _resource_limit(incident_state, "Police")
    police_options = tuple(sorted(set((0, min(2, police_limit), police_limit))))
    candidates = []
    for green_pct in GREEN_EXTENSION_OPTIONS:
        for diversion_share in DIVERSION_SHARE_OPTIONS:
            for police_units in police_options:
                if green_pct == 0 and diversion_share == 0 and police_units == 0:
                    continue
                controls = {
                    "green_extension_pct": green_pct,
                    "diversion_share": diversion_share,
                    "police_units": police_units,
                }
                projected, constraints, commands, forecast = _apply_controls(
                    incident, focus_id, diversion_id, controls, bundle.network,
                    signal_plan, incident_state, at, merged_config["horizon_minutes"],
                )
                kpis = _kpis(projected, focus_id, incident_state, incident)
                eligible = all(row["passed"] for row in constraints)
                score = round(
                    .30 * _clamp(kpis["focus_saturation"] / 1.25, 0, 1)
                    + .20 * _clamp(kpis["average_vehicle_wait_seconds"] / 60, 0, 1)
                    + .20 * _clamp(kpis["emergency_eta_minutes"] / 20, 0, 1)
                    + .15 * _clamp(kpis["congested_segment_count"] / max(1, len(baseline)), 0, 1)
                    + .15 * _clamp(max(0, kpis["control_side_effect_wait_seconds"]) / 30, 0, 1),
                    4,
                )
                candidates.append({
                    "controls": controls, "constraints": constraints,
                    "executable_commands": commands, "forecast_series": forecast,
                    "eligible": eligible, "score": score, "kpis": kpis,
                    "traffic": projected,
                })
    eligible_candidates = sorted(
        (candidate for candidate in candidates if candidate["eligible"]),
        key=lambda row: (row["score"], row["controls"]["police_units"],
                         row["controls"]["green_extension_pct"], row["controls"]["diversion_share"]),
    )
    selected = eligible_candidates[:3]
    plans = [{
        "plan_id": "BASELINE", "name": "事件發生但未處置", "eligible": False,
        "state": "UNMITIGATED_REFERENCE", "tradeoff": "比較基準，不是處置方案。",
        "score": None, "kpis": _kpis(incident, focus_id, incident_state),
        "traffic": _traffic_payload(incident), "controls": None,
        "constraints": [], "executable_commands": [], "forecast_series": [],
    }]
    for index, candidate in enumerate(selected, start=1):
        controls = candidate["controls"]
        plans.append({
            "plan_id": f"OPT_{index:03d}",
            "name": f"最佳化候選 {index}",
            "eligible": True,
            "ineligible_reason": None,
            "state": "OPTIMIZED_READY_FOR_APPROVAL",
            "tradeoff": (
                f"綠燈 +{controls['green_extension_pct']}%｜引流 {round(controls['diversion_share'] * 100)}%｜"
                f"警力 {controls['police_units']} 人"
            ),
            **{key: value for key, value in candidate.items() if key != "traffic"},
            "traffic": _traffic_payload(candidate["traffic"]),
        })

    manual_controls = merged_config.get("manual_controls")
    if manual_controls:
        projected, constraints, commands, forecast = _apply_controls(
            incident, focus_id, diversion_id, manual_controls, bundle.network,
            signal_plan, incident_state, at, merged_config["horizon_minutes"],
        )
        kpis = _kpis(projected, focus_id, incident_state, incident)
        eligible = all(row["passed"] for row in constraints)
        manual_score = round(
            .30 * _clamp(kpis["focus_saturation"] / 1.25, 0, 1)
            + .20 * _clamp(kpis["average_vehicle_wait_seconds"] / 60, 0, 1)
            + .20 * _clamp(kpis["emergency_eta_minutes"] / 20, 0, 1)
            + .15 * _clamp(kpis["congested_segment_count"] / max(1, len(baseline)), 0, 1)
            + .15 * _clamp(max(0, kpis["control_side_effect_wait_seconds"]) / 30, 0, 1), 4,
        )
        plans.append({
            "plan_id": "MANUAL", "name": "指揮官 Challenge", "eligible": eligible,
            "ineligible_reason": None if eligible else "人工方案違反執行限制，禁止核准",
            "state": "MANUAL_CHALLENGE_EVALUATED", "tradeoff": "使用與系統候選相同模型與限制重新求解。",
            "score": manual_score, "kpis": kpis, "controls": manual_controls,
            "constraints": constraints, "executable_commands": commands,
            "forecast_series": forecast, "traffic": _traffic_payload(projected),
        })
    approvable_plans = [
        plan for plan in plans
        if plan.get("eligible") and plan.get("score") is not None
    ]
    recommended = min(
        approvable_plans, key=lambda plan: (plan["score"], plan["plan_id"])
    )["plan_id"] if approvable_plans else None

    dataset_versions = {
        "traffic": _sha256_file(TRAFFIC_CSV),
        "crowd": _sha256_file(CROWD_CSV),
        "road_network": _sha256_file(ROAD_NETWORK_JSON),
        "incidents": _sha256_file(INCIDENTS_JSON),
        "sop": _sha256_file(SOP_TXT),
    }
    canonical_input = {
        "scenario_id": event.get("event_id"),
        "data_snapshot_id": f"SNAP-{at:%Y%m%d-%H%M}",
        "dataset_versions": dataset_versions,
        "event_payload": event,
        "simulation_config": merged_config,
        "model_version": MODEL_VERSION,
    }
    input_hash = _canonical_hash(canonical_input)
    deterministic_output = {
        "recommended_plan_id": recommended,
        "plans": plans,
        "route_evidence": routing,
        "signal_plan": signal_plan,
        "optimizer": {
            "evaluated_candidate_count": len(candidates),
            "eligible_candidate_count": len(eligible_candidates),
        },
    }
    output_hash = _canonical_hash(deterministic_output)
    return {
        "simulation_run_id": f"SIM-{at:%Y%m%d-%H%M}-{input_hash[:8]}",
        "scenario_id": event.get("event_id"),
        "started_at": at.isoformat(),
        "data_snapshot_id": canonical_input["data_snapshot_id"],
        "dataset_versions": dataset_versions,
        "event_payload": event,
        "simulation_config": merged_config,
        "model_version": MODEL_VERSION,
        "randomness_used": False,
        "input_sha256": input_hash,
        "output_sha256": output_hash,
        "recommended_plan_id": recommended,
        "recommendation_reason": "枚舉可執行控制組合，排除違反資源、號誌安全或替代道路容量限制者，再選擇加權代價最低方案。",
        "score_formula": "0.30×目標飽和度 + 0.20×平均等待 + 0.20×救援 ETA + 0.15×壅塞路段比例 + 0.15×側向等待副作用；愈低愈好",
        "approval_status": "READY_FOR_APPROVAL" if recommended else "NO_FEASIBLE_PLAN",
        "optimizer": {
            "method": "deterministic_grid_search_with_hard_constraints",
            "evaluated_candidate_count": len(candidates),
            "eligible_candidate_count": len(eligible_candidates),
            "decision_variables": {
                "green_extension_pct": list(GREEN_EXTENSION_OPTIONS),
                "diversion_share": list(DIVERSION_SHARE_OPTIONS),
                "police_units": list(police_options),
            },
            "hard_constraints": [
                "POLICE_AVAILABLE", "SIGNAL_CONTROL_AVAILABLE",
                "PEDESTRIAN_MIN_GREEN", "DIVERSION_ROUTE_AVAILABLE", "DIVERSION_CAPACITY",
            ],
            "forecast_horizon_minutes": merged_config["horizon_minutes"],
            "rolling_reoptimization_minutes": 5,
        },
        "plans": plans,
        "route_evidence": routing,
        "signal_plan": signal_plan,
        "kpi_evidence": {
            "average_vehicle_wait_seconds": "10 + 50×clamp(saturation,0,1)，主辦方無實測等待欄位，故明標為估計",
            "maximum_queue_vehicles": "vehicle_count×clamp(saturation,0,1.25)×0.08，為 deterministic-v1 代理值",
            "emergency_eta_minutes": "最短資源 ETA + 6×目標路段飽和度，為方案比較估計，不是正式派遣 ETA",
            "congested_segment_count": "Saturation_Score >= 0.85 的路段數",
            "crowd_evacuation_minutes": "本道路事件無適用的人流疏散模型，回傳 null，不製造假精確值",
        },
        "limitations": [
            "主辦方資料無逐車道佇列、方向等待與行人相位感測值，相關 KPI 為透明代理值或 null",
            "目前 Run 保存於 API 程序記憶體；正式部署應改為不可變資料庫紀錄",
            "核准方案會驅動本系統的後續模擬狀態，但不直接連接正式號誌或派遣設備",
            "目前為資料驅動的離散控制搜尋，不是 SUMO 微觀車流模擬",
        ],
    }


def replay_plan_comparison(bundle, stored: dict, incident_state: dict) -> dict:
    replayed = build_plan_comparison(bundle, incident_state, stored["simulation_config"])
    return {
        "simulation_run_id": stored["simulation_run_id"],
        "replay_output_sha256": replayed["output_sha256"],
        "original_output_sha256": stored["output_sha256"],
        "matches": replayed["output_sha256"] == stored["output_sha256"],
        "replayed_at": datetime.now().isoformat(timespec="seconds"),
        "random_seed": stored["simulation_config"]["random_seed"],
        "model_version": stored["model_version"],
    }
