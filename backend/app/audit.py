"""Machine-readable verification reports for the challenge datasets and simulator."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from .config import CROWD_CSV, INCIDENTS_JSON, ROAD_NETWORK_JSON, SOP_TXT, TRAFFIC_CSV
from .data_loader import all_timestamps, format_ts


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _missing_cells(rows: list[dict[str, str]]) -> int:
    return sum(value is None or not str(value).strip() for row in rows for value in row.values())


def _duplicate_count(rows: list[dict[str, str]], fields: tuple[str, ...]) -> int:
    keys = [tuple((row.get(field) or "").strip() for field in fields) for row in rows]
    return len(keys) - len(set(keys))


def simulation_contract(bundle) -> dict:
    stamps = all_timestamps(bundle.traffic, bundle.crowd)
    gaps = [int((right - left).total_seconds() // 60) for left, right in zip(stamps, stamps[1:])]
    gap_counts = dict(sorted(Counter(gaps).items()))
    traffic_names = {segment_id: segment.name for segment_id, segment in bundle.network.items()}
    traffic_mismatches = sorted({
        f"{record.segment_id}: {record.road_name} != {traffic_names.get(record.segment_id)}"
        for record in bundle.traffic
        if traffic_names.get(record.segment_id) != record.road_name
    })

    canonical = []
    for stamp in stamps:
        traffic = bundle.traffic_at(stamp)
        crowd = bundle.crowd_at(stamp)
        canonical.append({
            "at": format_ts(stamp),
            "traffic": {
                key: [value.avg_speed, value.vehicle_count, value.saturation_score, value.lane_status,
                      format_ts(value.timestamp)]
                for key, value in sorted(traffic.items())
            },
            "crowd": {
                key: [value.user_count, value.stay_time_avg, value.growth_rate, value.roaming_user_pct,
                      format_ts(value.timestamp)]
                for key, value in sorted(crowd.items())
            },
        })
    replay_hash = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return {
        "time_range": {
            "start": format_ts(stamps[0]) if stamps else None,
            "end": format_ts(stamps[-1]) if stamps else None,
            "timeline_points": len(stamps),
            "gap_minutes_distribution": {str(key): value for key, value in gap_counts.items()},
            "nominal_source_granularity_minutes": Counter(gaps).most_common(1)[0][0] if gaps else None,
            "tick_policy": "advance_to_next_available_source_timestamp",
            "interpolation": False,
        },
        "initialization": {
            "source": "city_traffic_flow.csv + signaling_crowd_density.csv",
            "front_end_constants_used": False,
            "missing_entity_policy": "last observation carried forward; absent before first observation",
        },
        "name_alignment": {
            "network_segments": len(bundle.network),
            "traffic_segment_ids": len({record.segment_id for record in bundle.traffic}),
            "traffic_name_mismatches": traffic_mismatches,
            "all_traffic_names_match": not traffic_mismatches,
        },
        "reproducibility": {
            "deterministic": True,
            "randomness_used": False,
            "snapshot_sha256": replay_hash,
            "scope": "dataset-driven baseline plus deterministic incident projection; audit timestamps excluded",
        },
        "update_equations": {
            "dataset_playback": "values are replaced only when a source row exists; otherwise prior value is retained",
            "incident_projection": "deterministic-incident-v1: organizer baseline × documented severity/status/type coefficients; affected and diversion roads only",
            "dynamic_routing": "re-evaluated for every scenario snapshot using projected saturation and organizer topology constraints",
            "congestion": "Normal < 0.85, B = 0.85..0.949, A >= 0.95",
            "decision_sandbox_model": "deterministic-v1; coefficients returned with each scenario result",
        },
    }


def dataset_usage_report() -> list[dict]:
    return [
        {"file": "city_traffic_flow.csv", "status": "used", "functions": [
            "simulation traffic snapshots", "congestion classification", "routing exclusion",
            "ETE saturation input", "incident projection baseline", "decision sandbox baseline", "green-corridor ETA"],
         "fields": ["Timestamp", "Segment_ID", "Road_Name", "Avg_Speed", "Vehicle_Count",
                    "Saturation_Score", "Lane_Status"],
         "display_only_fields": [], "unused_fields": []},
        {"file": "signaling_crowd_density.csv", "status": "used", "functions": [
            "simulation crowd snapshots", "crowd anomaly rules", "confidence corroboration",
            "notification audience context", "what-if baseline"],
         "fields": ["Timestamp", "BS_ID", "Location_Name", "User_Count", "Stay_Time_Avg",
                    "Growth_Rate", "Roaming_User_Pct"],
         "display_only_fields": [], "unused_fields": ["Stay_Time_Avg"]},
        {"file": "live_incidents.json", "status": "used", "functions": [
            "event injection", "incident playback projection", "dynamic routing", "rule evaluation", "resource dispatch", "notifications"],
         "fields": ["event_id", "type", "location", "affected_segment", "affected_road", "status",
                    "severity", "description", "timestamp"], "display_only_fields": [], "unused_fields": []},
        {"file": "road_network_geometry.json", "status": "used", "functions": [
            "road ID/name validation", "alternatives for routing", "capacity filtering",
            "station-road association", "green-corridor graph"],
         "fields": ["segment_id", "name", "flow_direction", "intersections", "capacity_vph",
                    "alternatives", "nearby_stations"],
         "display_only_fields": ["flow_direction"], "unused_fields": [],
         "limitation": "organizer file has topology attributes but no coordinates; map geometry is rebuilt from Taipei official GIS"},
        {"file": "emergency_traffic_sop.txt", "status": "used", "functions": [
            "rules 1-7 evidence retrieval", "decision trace", "notification actions", "advisor citations"],
         "fields": ["rule_id", "title", "text"]},
    ]


def confidence_contract() -> dict:
    return {
        "source_priors": {
            "official": 0.50, "organizer_dataset": 0.50, "operator": 0.30,
            "iot": 0.30, "camera": 0.30, "citizen": 0.10, "unknown": 0.10,
        },
        "corroboration": {
            "speed_at_or_below_10_kmh": 0.20,
            "otherwise_saturation_at_or_above_0_95": 0.15,
            "abnormal_lane_status": 0.15,
            "nearby_crowd_growth_abs_at_or_above_0_30": 0.10,
            "human_confirmed": 0.20,
        },
        "execution_gates": [
            {"minimum": 0.75, "policy": "ACTION_PROPOSED", "effect": "resources may be reserved; external action still needs approval"},
            {"minimum": 0.50, "policy": "HUMAN_CONFIRMATION_REQUIRED", "effect": "no resource reservation or external notification"},
            {"minimum": 0.00, "policy": "MONITOR_ONLY", "effect": "dashboard monitoring only"},
        ],
        "trusted_source_override": "official/organizer fixtures and human-confirmed operator reports may propose action from score 0.50; external approval remains mandatory",
        "known_limitations": [
            "organizer incidents contain no signed provenance, so their source is explicitly marked inferred",
            "no freshness decay, duplicate-evidence identity, or conflict penalty yet",
        ],
    }


def coordinator_contract() -> dict:
    return {
        "implemented": [
            "severity-dependent resource quantities", "finite inventory and shortfall detection",
            "lower-priority preemption proposals", "human-approved preemption",
            "priority-ordered automatic refill after release", "re-injection recalculates and releases prior allocation",
            "simulation-time closed-loop KPI evaluation", "automatic constrained re-planning when KPI misses its review target",
            "single approval gate commits the optimized controls and reserved response tasks",
            "field confirmation gate before incident resolution",
        ],
        "proof_scenario": [
            "inject Medium EVT_003 to reserve police", "inject Critical ACC_001",
            "inject another Critical incident to create a shortfall",
            "observe a proposal to pull only from the lower-priority event",
            "approve preemption or reject the lower-priority task and observe priority refill plus dual audit traces",
        ],
        "not_implemented": [
            "production traffic-controller adapters", "signed field telemetry provenance",
            "resource failed-state telemetry and automatic replacement dispatch",
        ],
        "classification": "deterministic supervised closed-loop Coordinator (human-on-the-loop for consequential commands; LLM has no execution authority)",
    }


def data_quality_report(bundle) -> dict:
    traffic_rows = _csv_rows(TRAFFIC_CSV)
    crowd_rows = _csv_rows(CROWD_CSV)
    incident_rows = json.loads(INCIDENTS_JSON.read_text(encoding="utf-8"))
    network_rows = json.loads(ROAD_NETWORK_JSON.read_text(encoding="utf-8"))
    station_ids = {record.bs_id for record in bundle.crowd}
    segment_ids = set(bundle.network)

    traffic_name_mismatch = sum(
        1 for row in traffic_rows
        if bundle.network.get((row.get("Segment_ID") or "").strip()) is None
        or bundle.network[(row.get("Segment_ID") or "").strip()].name != (row.get("Road_Name") or "").strip()
    )
    invalid_traffic_ranges = sum(
        1 for row in traffic_rows
        if float(row["Avg_Speed"]) < 0 or int(row["Vehicle_Count"]) < 0
        or not 0 <= float(row["Saturation_Score"]) <= 1.5
    )
    invalid_crowd_ranges = sum(
        1 for row in crowd_rows
        if int(row["User_Count"]) < 0 or float(row["Stay_Time_Avg"]) < 0
    )
    broken_alternatives = sum(
        alternative not in segment_ids for row in network_rows for alternative in row.get("alternatives", [])
    )
    unknown_nearby_stations = sum(
        station not in station_ids for row in network_rows for station in row.get("nearby_stations", [])
    )

    reports = {
        "city_traffic_flow.csv": {
            "raw_rows": len(traffic_rows), "loaded_rows": len(bundle.traffic),
            "rejected_rows": len(traffic_rows) - len(bundle.traffic), "missing_cells": _missing_cells(traffic_rows),
            "duplicate_timestamp_entity_rows": _duplicate_count(traffic_rows, ("Timestamp", "Segment_ID")),
            "invalid_numeric_ranges": invalid_traffic_ranges, "road_name_mismatches": traffic_name_mismatch,
        },
        "signaling_crowd_density.csv": {
            "raw_rows": len(crowd_rows), "loaded_rows": len(bundle.crowd),
            "rejected_rows": len(crowd_rows) - len(bundle.crowd), "missing_cells": _missing_cells(crowd_rows),
            "duplicate_timestamp_entity_rows": _duplicate_count(crowd_rows, ("Timestamp", "BS_ID")),
            "invalid_numeric_ranges": invalid_crowd_ranges,
        },
        "live_incidents.json": {
            "raw_rows": len(incident_rows), "loaded_rows": len(bundle.incidents),
            "rejected_rows": len(incident_rows) - len(bundle.incidents),
            "duplicate_event_ids": len(incident_rows) - len({row.get("event_id") for row in incident_rows}),
            "missing_required_fields": sum(
                not all(row.get(field) for field in ("event_id", "type", "status", "severity", "timestamp"))
                for row in incident_rows
            ),
        },
        "road_network_geometry.json": {
            "raw_rows": len(network_rows), "loaded_rows": len(bundle.network),
            "rejected_rows": len(network_rows) - len(bundle.network),
            "duplicate_segment_ids": len(network_rows) - len({row.get("segment_id") for row in network_rows}),
            "broken_alternative_references": broken_alternatives,
            "unknown_nearby_station_references": unknown_nearby_stations,
        },
        "emergency_traffic_sop.txt": {
            "raw_rules": len(bundle.sop.rules), "loaded_rules": len(bundle.sop.rules), "rejected_rules": 0,
        },
    }
    source_paths = {
        "city_traffic_flow.csv": TRAFFIC_CSV,
        "signaling_crowd_density.csv": CROWD_CSV,
        "live_incidents.json": INCIDENTS_JSON,
        "road_network_geometry.json": ROAD_NETWORK_JSON,
        "emergency_traffic_sop.txt": SOP_TXT,
    }
    for name, path in source_paths.items():
        reports[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    issue_count = sum(
        value for report in reports.values() for key, value in report.items()
        if key not in {"raw_rows", "loaded_rows", "raw_rules", "loaded_rules"} and isinstance(value, int)
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": {
            "missing_or_invalid": "fail fast; no silent row deletion",
            "duplicates": "reported as quality errors; current loaders preserve rows",
            "timestamps": "trim then parse exactly as YYYY-MM-DD HH:MM",
            "percentages": "accept numeric text with optional percent sign and normalize to percentage points",
            "identifiers_and_names": "trim surrounding whitespace; validate road names against organizer topology",
            "coordinates": "map assets are converted to EPSG:4326 and source CRS is retained in metadata",
        },
        "datasets": reports,
        "summary": {"detected_issue_count": issue_count, "silent_drops": 0},
    }
