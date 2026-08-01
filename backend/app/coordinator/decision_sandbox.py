"""Interactive, deterministic traffic decision sandbox.

This module deliberately does not call an LLM.  Operators choose road measures
and disruptions; the sandbox applies transparent coefficients to a copied
traffic snapshot and returns both map-ready projections and comparison metrics.
"""
from __future__ import annotations

import hashlib
import json
from ..data_loader import parse_ts
from ..engines.rule_engine import classify_congestion
from ..engines.signal_timing import calculate_signal_plan
from .coordinator import DataBundle


ACTION_LABELS = {
    "extend_green": "延長綠燈",
    "open_lane": "開放調撥車道",
    "divert": "引流至替代道路",
    "police_control": "警力手動疏導",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _row(segment_id: str, network, record) -> dict:
    segment = network[segment_id]
    if record:
        return {
            "segment_id": segment_id,
            "road_name": segment.name,
            "saturation_score": record.saturation_score,
            "avg_speed": record.avg_speed,
            "vehicle_count": record.vehicle_count,
            "lane_status": record.lane_status,
            "source": "observed",
        }
    # Some demo roads start reporting later in the timeline.  Keep them
    # operable, while explicitly identifying the fallback as an estimate.
    return {
        "segment_id": segment_id,
        "road_name": segment.name,
        "saturation_score": 0.55,
        "avg_speed": 36.0,
        "vehicle_count": round(segment.capacity_vph * 0.45),
        "lane_status": "Estimated",
        "source": "estimated",
    }


def _metrics(traffic: dict[str, dict], focus_id: str) -> dict:
    rows = list(traffic.values())
    focus = traffic[focus_id]
    avg_sat = sum(r["saturation_score"] for r in rows) / len(rows)
    avg_speed = sum(r["avg_speed"] for r in rows) / len(rows)
    return {
        "focus_saturation": round(focus["saturation_score"], 2),
        "focus_speed": round(focus["avg_speed"], 1),
        "network_saturation": round(avg_sat, 2),
        "network_speed": round(avg_speed, 1),
        "critical_segments": sum(r["saturation_score"] >= 0.95 for r in rows),
        "congested_segments": sum(r["saturation_score"] >= 0.85 for r in rows),
        "clearance_minutes": round(18 + focus["saturation_score"] * 34),
    }


def run_decision_sandbox(bundle: DataBundle, scenario: dict) -> dict:
    at = parse_ts(scenario["at"])
    focus_id = scenario["focus_segment_id"]
    if focus_id not in bundle.network:
        raise KeyError(f"未知的路段 ID: {focus_id}")

    snapshot = bundle.traffic_at(at)
    baseline = {
        segment_id: _row(segment_id, bundle.network, snapshot.get(segment_id))
        for segment_id in bundle.network
    }
    projected = {segment_id: dict(row) for segment_id, row in baseline.items()}
    applied: list[dict] = []

    for action in scenario.get("actions", []):
        kind = action.get("type")
        segment_id = action.get("segment_id", focus_id)
        if kind not in ACTION_LABELS or segment_id not in projected:
            continue
        strength = _clamp(float(action.get("strength", 1)), 0.25, 1.5)
        row = projected[segment_id]
        if kind == "extend_green":
            row["saturation_score"] -= 0.14 * strength
            row["avg_speed"] *= 1 + 0.18 * strength
        elif kind == "open_lane":
            row["saturation_score"] -= 0.18 * strength
            row["avg_speed"] *= 1 + 0.22 * strength
            row["lane_status"] = "Reversible lane open"
        elif kind == "police_control":
            row["saturation_score"] -= 0.08 * strength
            row["avg_speed"] *= 1 + 0.10 * strength
        elif kind == "divert":
            target_id = action.get("target_segment_id")
            if target_id not in projected or target_id == segment_id:
                continue
            share = _clamp(float(action.get("share", 0.25)), 0.1, 0.5)
            target = projected[target_id]
            row["saturation_score"] -= 0.32 * share * strength
            row["avg_speed"] *= 1 + 0.20 * share * strength
            target["saturation_score"] += 0.24 * share * strength
            target["avg_speed"] *= 1 - 0.12 * share * strength
            applied.append({"label": ACTION_LABELS[kind], "segment_id": segment_id,
                            "target_segment_id": target_id, "share": share})
            continue
        applied.append({"label": ACTION_LABELS[kind], "segment_id": segment_id})

    disruption = scenario.get("disruption") or "none"
    disruption_target = scenario.get("disruption_segment_id") or focus_id
    if disruption == "rain":
        for row in projected.values():
            row["saturation_score"] += 0.07
            row["avg_speed"] *= 0.88
    elif disruption == "secondary_accident" and disruption_target in projected:
        projected[disruption_target]["saturation_score"] += 0.22
        projected[disruption_target]["avg_speed"] *= 0.58
        projected[disruption_target]["lane_status"] = "Partial closure"
    elif disruption == "pedestrian_surge" and disruption_target in projected:
        projected[disruption_target]["saturation_score"] += 0.12
        projected[disruption_target]["avg_speed"] *= 0.78
    elif disruption == "custom_load" and disruption_target in projected:
        load = _clamp(float(scenario.get("disruption_load", 20)), 0, 80) / 100
        projected[disruption_target]["saturation_score"] += load * 0.55
        projected[disruption_target]["avg_speed"] *= 1 - load * 0.45

    for row in projected.values():
        row["saturation_score"] = round(_clamp(row["saturation_score"], 0.15, 1.25), 3)
        row["avg_speed"] = round(_clamp(row["avg_speed"], 5, 65), 1)
        row["congestion_level"] = classify_congestion(row["saturation_score"])
    for row in baseline.values():
        row["congestion_level"] = classify_congestion(row["saturation_score"])

    before = _metrics(baseline, focus_id)
    after = _metrics(projected, focus_id)
    delta = {
        key: round(after[key] - before[key], 2)
        for key in before
    }
    # A small deterministic response curve for playback in the UI.
    series = []
    for minute, progress in ((0, 0), (5, .35), (10, .65), (15, .85), (20, 1)):
        series.append({
            "minute": minute,
            "focus_saturation": round(before["focus_saturation"] + delta["focus_saturation"] * progress, 2),
            "network_saturation": round(before["network_saturation"] + delta["network_saturation"] * progress, 2),
        })

    if after["focus_saturation"] < before["focus_saturation"] and after["critical_segments"] <= before["critical_segments"]:
        verdict = "可行：目標路段改善，且未增加全網危急路段。"
    elif after["focus_saturation"] < before["focus_saturation"]:
        verdict = "需調整：目標路段改善，但壅塞可能轉移到其他道路。"
    else:
        verdict = "不建議：在目前突發條件下，方案未改善目標路段。"

    result = {
        "scenario_name": scenario.get("name", "未命名方案"),
        "as_of": scenario["at"],
        "focus_segment_id": focus_id,
        "focus_name": bundle.network[focus_id].name,
        "baseline_traffic": baseline,
        "projected_traffic": projected,
        "baseline_metrics": before,
        "projected_metrics": after,
        "delta": delta,
        "series": series,
        "applied_actions": applied,
        "disruption": disruption,
        "verdict": verdict,
        "model": "deterministic-v1",
        "production_state_modified": False,
    }
    if any(action.get("type") == "extend_green" for action in scenario.get("actions", [])):
        approach_ids = [focus_id, *bundle.network[focus_id].alternatives[:3]]
        result["signal_plan"] = calculate_signal_plan(bundle, at, approach_ids)
    else:
        result["signal_plan"] = None
    result["evidence_contract"] = {
        "data": ["city_traffic_flow.csv", "signaling_crowd_density.csv", "road_network_geometry.json"],
        "formula": "decision-sandbox deterministic-v1 coefficients; signal timing formula attached when used",
        "rules": [],
        "simulation": {"model": result["model"], "production_state_modified": False},
    }
    scenario_json = json.dumps(scenario, ensure_ascii=False, sort_keys=True, default=str)
    baseline_json = json.dumps(baseline, ensure_ascii=False, sort_keys=True, default=str)
    result["evidence_contract"]["scenario_sha256"] = hashlib.sha256(scenario_json.encode()).hexdigest()
    result["evidence_contract"]["baseline_snapshot_sha256"] = hashlib.sha256(baseline_json.encode()).hexdigest()
    result["simulation_run_id"] = f"DECISION-{result['evidence_contract']['scenario_sha256'][:12]}"
    return result
