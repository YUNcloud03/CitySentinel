"""Deterministic emergency green-corridor simulator.

The engine uses the challenge road topology, the current traffic snapshot,
official-aligned road geometry, and official signal locations.  It never
changes production signal state: results are proposals awaiting human approval.
"""
from __future__ import annotations

import heapq
import json
import math
from functools import lru_cache
from pathlib import Path

from ..config import PROJECT_ROOT
from ..data_loader import format_ts, parse_ts
from .coordinator import DataBundle


ROADS_GEOJSON = PROJECT_ROOT / "frontend" / "src" / "data" / "roads.json"
SIGNALS_GEOJSON = PROJECT_ROOT / "frontend" / "public" / "data" / "signals.geojson"

BASE_SIGNAL_DELAY_SECONDS = 24
CORRIDOR_SIGNAL_DELAY_SECONDS = 4
SIGNAL_PREEMPT_LEAD_SECONDS = 25
SIGNAL_RESTORE_BUFFER_SECONDS = 12
PEDESTRIAN_CLEARANCE_SECONDS = 8
MIN_CORRIDOR_SPEED_KMH = 32.0
MAX_CORRIDOR_SPEED_KMH = 50.0


def _distance_m(start: tuple[float, float], end: tuple[float, float]) -> float:
    latitude = math.radians((start[1] + end[1]) / 2)
    dx = (end[0] - start[0]) * 111_320 * math.cos(latitude)
    dy = (end[1] - start[1]) * 110_540
    return math.hypot(dx, dy)


def _line_length_m(coordinates: list[list[float]]) -> float:
    return sum(
        _distance_m(tuple(start), tuple(end))
        for start, end in zip(coordinates, coordinates[1:])
    )


def _point_progress(
    point: tuple[float, float], coordinates: list[list[float]]
) -> float:
    """Return the approximate 0..1 progress of a point along a LineString."""
    lengths = [
        _distance_m(tuple(start), tuple(end))
        for start, end in zip(coordinates, coordinates[1:])
    ]
    total = sum(lengths)
    if total <= 0:
        return 0.0

    latitude = math.radians(point[1])
    scale_x, scale_y = 111_320 * math.cos(latitude), 110_540
    px, py = point[0] * scale_x, point[1] * scale_y
    best_distance = float("inf")
    best_progress = 0.0
    travelled = 0.0
    for index, (start, end) in enumerate(zip(coordinates, coordinates[1:])):
        ax, ay = start[0] * scale_x, start[1] * scale_y
        bx, by = end[0] * scale_x, end[1] * scale_y
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator)) if denominator else 0.0
        distance = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if distance < best_distance:
            best_distance = distance
            best_progress = (travelled + lengths[index] * t) / total
        travelled += lengths[index]
    return best_progress


def _closest_coordinate_pair(
    first: list[list[float]], second: list[list[float]]
) -> tuple[int, int]:
    return min(
        (
            _distance_m(tuple(first_point), tuple(second_point)),
            first_index,
            second_index,
        )
        for first_index, first_point in enumerate(first)
        for second_index, second_point in enumerate(second)
    )[1:]


def _route_coordinate_parts(
    route_ids: list[str], roads: dict[str, dict]
) -> dict[str, list[list[float]]]:
    """Trim each road to the entry/exit junctions and orient it in travel order."""
    if not route_ids:
        return {}
    junctions = [
        _closest_coordinate_pair(
            roads[first_id]["coordinates"], roads[second_id]["coordinates"]
        )
        for first_id, second_id in zip(route_ids, route_ids[1:])
    ]
    parts: dict[str, list[list[float]]] = {}
    for route_index, segment_id in enumerate(route_ids):
        coordinates = roads[segment_id]["coordinates"]
        if len(route_ids) == 1:
            entry_index, exit_index = 0, len(coordinates) - 1
        elif route_index == 0:
            exit_index = junctions[0][0]
            distance_to_start = _line_length_m(coordinates[: exit_index + 1])
            distance_to_end = _line_length_m(coordinates[exit_index:])
            entry_index = 0 if distance_to_start >= distance_to_end else len(coordinates) - 1
        elif route_index == len(route_ids) - 1:
            entry_index = junctions[-1][1]
            distance_to_start = _line_length_m(coordinates[: entry_index + 1])
            distance_to_end = _line_length_m(coordinates[entry_index:])
            exit_index = 0 if distance_to_start >= distance_to_end else len(coordinates) - 1
        else:
            entry_index = junctions[route_index - 1][1]
            exit_index = junctions[route_index][0]
        if entry_index <= exit_index:
            part = coordinates[entry_index : exit_index + 1]
        else:
            part = list(reversed(coordinates[exit_index : entry_index + 1]))
        parts[segment_id] = [list(point) for point in part]
    return parts


def _oriented_route_coordinates(route_ids: list[str], roads: dict[str, dict]) -> list[list[float]]:
    parts = _route_coordinate_parts(route_ids, roads)
    joined: list[list[float]] = []
    for segment_id in route_ids:
        for point in parts[segment_id]:
            if not joined or point != joined[-1]:
                joined.append(point)
    return joined


def _point_line_distance_m(point: tuple[float, float], coordinates: list[list[float]]) -> float:
    if not coordinates:
        return float("inf")
    if len(coordinates) == 1:
        return _distance_m(point, tuple(coordinates[0]))
    latitude = math.radians(point[1])
    scale_x, scale_y = 111_320 * math.cos(latitude), 110_540
    px, py = point[0] * scale_x, point[1] * scale_y
    best = float("inf")
    for start, end in zip(coordinates, coordinates[1:]):
        ax, ay = start[0] * scale_x, start[1] * scale_y
        bx, by = end[0] * scale_x, end[1] * scale_y
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator)) if denominator else 0.0
        best = min(best, math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy)))
    return best


def _point_at_fraction(coordinates: list[list[float]], fraction: float) -> list[float] | None:
    if not coordinates:
        return None
    if len(coordinates) == 1:
        return list(coordinates[0])
    lengths = [_distance_m(tuple(a), tuple(b)) for a, b in zip(coordinates, coordinates[1:])]
    total = sum(lengths)
    target = _clamped_fraction(fraction) * total
    travelled = 0.0
    for length, start, end in zip(lengths, coordinates, coordinates[1:]):
        if travelled + length >= target:
            ratio = 0.0 if length == 0 else (target - travelled) / length
            return [round(start[0] + (end[0] - start[0]) * ratio, 7),
                    round(start[1] + (end[1] - start[1]) * ratio, 7)]
        travelled += length
    return list(coordinates[-1])


def _clamped_fraction(value: float) -> float:
    return max(0.0, min(1.0, value))


@lru_cache(maxsize=1)
def _map_assets() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    roads_data = json.loads(ROADS_GEOJSON.read_text(encoding="utf-8"))
    signals_data = json.loads(SIGNALS_GEOJSON.read_text(encoding="utf-8"))
    roads = {
        feature["properties"]["segment_id"]: {
            "coordinates": feature["geometry"]["coordinates"],
            "length_m": _line_length_m(feature["geometry"]["coordinates"]),
        }
        for feature in roads_data["features"]
    }
    signals: dict[str, list[dict]] = {}
    for feature in signals_data["features"]:
        signal = {
            **feature["properties"],
            "coordinates": feature["geometry"]["coordinates"],
        }
        signals.setdefault(signal["segment_id"], []).append(signal)
    for segment_id, rows in signals.items():
        coordinates = roads[segment_id]["coordinates"]
        for signal in rows:
            signal["progress"] = _point_progress(tuple(signal["coordinates"]), coordinates)
        rows.sort(key=lambda row: (row["progress"], row["device_id"]))
    return roads, signals


def _graph(network) -> dict[str, set[str]]:
    by_name = {segment.name: segment.segment_id for segment in network.values()}
    graph = {segment_id: set() for segment_id in network}
    for segment_id, segment in network.items():
        for road_name in segment.intersections:
            other_id = by_name.get(road_name)
            if other_id and other_id != segment_id:
                graph[segment_id].add(other_id)
                graph[other_id].add(segment_id)
    return graph


def _traffic_row(bundle: DataBundle, snapshot, segment_id: str) -> dict:
    record = snapshot.get(segment_id)
    if record:
        return {
            "avg_speed": record.avg_speed,
            "saturation_score": record.saturation_score,
            "lane_status": record.lane_status,
            "source": "observed_or_last_known",
            "data_time": format_ts(record.timestamp),
        }
    return {
        "avg_speed": 30.0,
        "saturation_score": 0.55,
        "lane_status": "Estimated",
        "source": "estimated_fallback",
        "data_time": None,
    }


def _segment_metrics(bundle: DataBundle, snapshot) -> dict[str, dict]:
    roads, signals = _map_assets()
    result = {}
    for segment_id, segment in bundle.network.items():
        traffic = _traffic_row(bundle, snapshot, segment_id)
        speed = max(5.0, traffic["avg_speed"])
        corridor_speed = min(
            MAX_CORRIDOR_SPEED_KMH,
            max(speed, MIN_CORRIDOR_SPEED_KMH + (1 - min(1.0, traffic["saturation_score"])) * 10),
        )
        length_m = roads[segment_id]["length_m"]
        signal_count = len(signals.get(segment_id, []))
        baseline_seconds = length_m / (speed / 3.6) + signal_count * BASE_SIGNAL_DELAY_SECONDS
        corridor_seconds = length_m / (corridor_speed / 3.6) + signal_count * CORRIDOR_SIGNAL_DELAY_SECONDS
        result[segment_id] = {
            "segment_id": segment_id,
            "name": segment.name,
            "length_m": round(length_m),
            "signal_count": signal_count,
            "baseline_speed_kmh": round(speed, 1),
            "corridor_speed_kmh": round(corridor_speed, 1),
            "saturation_score": traffic["saturation_score"],
            "lane_status": traffic["lane_status"],
            "source": traffic["source"],
            "data_time": traffic["data_time"],
            "baseline_seconds": baseline_seconds,
            "corridor_seconds": corridor_seconds,
        }
    return result


def _shortest_path(
    graph: dict[str, set[str]], metrics: dict[str, dict], origin: str,
    destination: str, blocked: set[str]
) -> list[str]:
    queue: list[tuple[float, str, tuple[str, ...]]] = [(0.0, origin, ())]
    best: dict[str, float] = {}
    while queue:
        cost, current, prefix = heapq.heappop(queue)
        if current in best and best[current] <= cost:
            continue
        best[current] = cost
        path = (*prefix, current)
        if current == destination:
            return list(path)
        for neighbor in sorted(graph[current]):
            if neighbor in blocked or neighbor in path:
                continue
            heapq.heappush(
                queue,
                (cost + metrics[neighbor]["baseline_seconds"], neighbor, path),
            )
    raise ValueError("找不到避開封閉路段的連續救援路徑")


def _messages(vehicle_label: str, route_names: list[str], eta_after: int) -> dict[str, str]:
    route = " → ".join(route_names)
    return {
        "zh": f"緊急救援車輛正行經 {route}，請靠邊避讓並遵循現場指示；預估通過時間約 {eta_after} 分鐘。",
        "en": f"Emergency {vehicle_label.lower()} corridor active via {route}. Pull over and follow instructions. Estimated passage: {eta_after} min.",
        "ja": f"緊急車両が {route} を通行します。道路脇に寄り、現場の指示に従ってください。通過予定は約 {eta_after} 分です。",
        "ko": f"긴급 차량이 {route} 경로로 이동 중입니다. 우측으로 양보하고 현장 안내를 따라주십시오. 예상 통과 시간은 약 {eta_after}분입니다.",
    }


def corridor_state_at(plan: dict, elapsed_seconds: int, approved: bool | None = None) -> dict:
    """Return deterministic rolling preemption state; at most one intersection is green."""
    elapsed = max(0, int(elapsed_seconds))
    is_approved = approved if approved is not None else plan.get("approval_status") == "APPROVED_FOR_SIMULATION"
    actions = plan.get("signal_actions", [])
    intersection_rows: dict[str, list[dict]] = {}
    for action in actions:
        intersection_rows.setdefault(action["intersection_id"], []).append(action)
    groups = sorted(
        intersection_rows.items(),
        key=lambda item: (min(row["prepare_at_seconds"] for row in item[1]), item[0]),
    )
    states = []
    current_intersection_id = None
    active_device_ids: list[str] = []
    clearance_device_ids: list[str] = []
    for intersection_id, rows in groups:
        prepare = min(row["prepare_at_seconds"] for row in rows)
        activate = min(row["activate_at_seconds"] for row in rows)
        passage = max(row["passage_at_seconds"] for row in rows)
        restore = max(row["restore_at_seconds"] for row in rows)
        if not is_approved:
            state = "PLANNED"
        elif elapsed < prepare:
            state = "WAITING"
        elif elapsed < activate:
            state = "PEDESTRIAN_CLEARANCE"
        elif elapsed <= passage:
            state = "EMERGENCY_GREEN"
        elif elapsed <= restore:
            state = "RESTORING"
        else:
            state = "NORMAL"
        device_ids = sorted(row["device_id"] for row in rows)
        if state == "EMERGENCY_GREEN":
            current_intersection_id = intersection_id
            active_device_ids = device_ids
        elif state == "PEDESTRIAN_CLEARANCE":
            current_intersection_id = intersection_id
            clearance_device_ids = device_ids
        states.append({
            "intersection_id": intersection_id,
            "name": rows[0]["name"],
            "state": state,
            "device_ids": device_ids,
            "prepare_at_seconds": prepare,
            "activate_at_seconds": activate,
            "passage_at_seconds": passage,
            "restore_at_seconds": restore,
        })
    total = max((row["restore_at_seconds"] for row in actions), default=0)
    passage_total = max((row["passage_at_seconds"] for row in actions), default=total)
    vehicle_fraction = _clamped_fraction(elapsed / max(1, passage_total)) if is_approved else 0.0
    vehicle_position = _point_at_fraction(plan.get("route_geometry", []), vehicle_fraction)
    next_intersection = next(
        (row for row in states if row["state"] in {"PEDESTRIAN_CLEARANCE", "EMERGENCY_GREEN", "WAITING"}),
        None,
    )
    return {
        "elapsed_seconds": elapsed,
        "total_seconds": total,
        "completed": bool(is_approved and elapsed > total),
        "current_intersection_id": current_intersection_id,
        "active_signal_device_ids": active_device_ids,
        "clearance_signal_device_ids": clearance_device_ids,
        "vehicle_position": vehicle_position,
        "vehicle_progress_pct": round(vehicle_fraction * 100, 1),
        "vehicle_position_source": "simulated_from_route_geometry_and_corridor_elapsed_time",
        "next_intersection_id": next_intersection["intersection_id"] if next_intersection else None,
        "intersection_states": states,
        "invariant": "different intersections emergency-green count <= 1",
    }


def simulate_green_corridor(bundle: DataBundle, scenario: dict) -> dict:
    at = parse_ts(scenario["at"])
    origin = scenario["origin_segment_id"]
    destination = scenario["destination_segment_id"]
    vehicle_type = scenario.get("vehicle_type", "Ambulance")
    blocked = set(scenario.get("blocked_segment_ids") or [])

    if origin not in bundle.network or destination not in bundle.network:
        raise KeyError("起點或終點路段不存在於主辦方路網")
    if origin == destination:
        raise ValueError("救援起點與目的路段不可相同")
    unknown_blocked = blocked - set(bundle.network)
    if unknown_blocked:
        raise KeyError(f"封閉路段不存在：{', '.join(sorted(unknown_blocked))}")
    if origin in blocked or destination in blocked:
        raise ValueError("起點與目的路段不可設為封閉")

    snapshot = bundle.traffic_at(at)
    metrics = _segment_metrics(bundle, snapshot)
    route_ids = _shortest_path(_graph(bundle.network), metrics, origin, destination, blocked)
    roads, signals = _map_assets()
    route_parts = _route_coordinate_parts(route_ids, roads)
    route_geometry = _oriented_route_coordinates(route_ids, roads)
    route_signals: dict[str, list[dict]] = {}
    route_details = []
    for segment_id in route_ids:
        part = route_parts[segment_id]
        segment_signals = [
            {
                **signal,
                "route_progress": _point_progress(tuple(signal["coordinates"]), part),
            }
            for signal in signals.get(segment_id, [])
            if _point_line_distance_m(tuple(signal["coordinates"]), part) <= 80
        ]
        route_signals[segment_id] = segment_signals
        base = metrics[segment_id]
        length_m = _line_length_m(part)
        baseline_seconds = length_m / (base["baseline_speed_kmh"] / 3.6) + len(segment_signals) * BASE_SIGNAL_DELAY_SECONDS
        corridor_seconds = length_m / (base["corridor_speed_kmh"] / 3.6) + len(segment_signals) * CORRIDOR_SIGNAL_DELAY_SECONDS
        route_details.append({
            **base,
            "length_m": round(length_m),
            "signal_count": len(segment_signals),
            "baseline_seconds": baseline_seconds,
            "corridor_seconds": corridor_seconds,
        })
    eta_before_seconds = sum(row["baseline_seconds"] for row in route_details)
    eta_after_seconds = sum(row["corridor_seconds"] for row in route_details)
    eta_before = max(1, round(eta_before_seconds / 60))
    eta_after = max(1, round(eta_after_seconds / 60))

    signal_actions = []
    elapsed = 0.0
    previous_passage = 0
    for row in route_details:
        segment_id = row["segment_id"]
        segment_travel = row["length_m"] / (row["corridor_speed_kmh"] / 3.6)
        grouped_signals: dict[str, list[dict]] = {}
        for signal in route_signals.get(segment_id, []):
            intersection_id = signal.get("icid") or signal.get("group") or signal["device_id"]
            grouped_signals.setdefault(intersection_id, []).append(signal)
        for intersection_id, intersection_signals in sorted(
            grouped_signals.items(), key=lambda item: min(signal["route_progress"] for signal in item[1])
        ):
            raw_passage = elapsed + segment_travel * min(signal["route_progress"] for signal in intersection_signals)
            prepare = max(previous_passage, round(raw_passage - SIGNAL_PREEMPT_LEAD_SECONDS))
            activate = prepare + PEDESTRIAN_CLEARANCE_SECONDS
            passage = max(round(raw_passage), activate + 1)
            restore = passage + SIGNAL_RESTORE_BUFFER_SECONDS
            previous_passage = passage
            for signal in intersection_signals:
                signal_actions.append({
                    "intersection_id": intersection_id,
                    "device_id": signal["device_id"],
                    "name": signal["name"],
                    "segment_id": segment_id,
                    "coordinates": signal["coordinates"],
                    "action": "EMERGENCY_GREEN",
                    "prepare_at_seconds": prepare,
                    "activate_at_seconds": activate,
                    "passage_at_seconds": passage,
                    "restore_at_seconds": restore,
                    "pedestrian_clearance_seconds": PEDESTRIAN_CLEARANCE_SECONDS,
                    "reason": "救援車抵達前完成行人清空；只允許下一路口優先，通過後恢復",
                })
        elapsed += row["corridor_seconds"]

    critical_segments = [
        row["segment_id"] for row in route_details if row["saturation_score"] >= 0.95
    ]
    police_units = min(3, max(1, len(critical_segments)))
    route_names = [row["name"] for row in route_details]
    improvement = max(0.0, (eta_before_seconds - eta_after_seconds) / eta_before_seconds * 100)
    vehicle_labels = {"Ambulance": "Ambulance", "FireEngine": "Fire engine"}

    result = {
        "scenario_id": f"GC-{format_ts(at).replace('-', '').replace(':', '').replace(' ', 'T')}-{origin[-3:]}-{destination[-3:]}",
        "as_of": format_ts(at),
        "vehicle_type": vehicle_type,
        "priority": "EMERGENCY",
        "route_segment_ids": route_ids,
        "route_names": route_names,
        "route_details": [
            {
                **row,
                "baseline_minutes": round(row["baseline_seconds"] / 60, 2),
                "corridor_minutes": round(row["corridor_seconds"] / 60, 2),
            }
            for row in route_details
        ],
        "blocked_segment_ids": sorted(blocked),
        "route_geometry": route_geometry,
        "eta": {
            "before_minutes": eta_before,
            "after_minutes": eta_after,
            "saved_minutes": max(0, eta_before - eta_after),
            "improvement_pct": round(improvement, 1),
            "formula": "ETA = Σ(道路長度 ÷ 速度) + Σ號誌平均延誤；走廊方案以預控後速度與 4 秒號誌延誤重算",
        },
        "signal_actions": signal_actions,
        "dispatch_recommendation": {
            "resource_type": "Police",
            "requested_units": police_units,
            "critical_segment_ids": critical_segments,
            "reason": "於高飽和或關鍵轉向路口維持救援通道",
        },
        "messages": _messages(vehicle_labels.get(vehicle_type, vehicle_type), route_names, eta_after),
        "evidence": {
            "road_topology_source": "road_network_geometry.json",
            "geometry_source": "臺北市寬度超過8公尺道路 GIS 圖資",
            "route_geometry_method": "trim_each_road_between_actual_entry_and_exit_junctions",
            "signal_source": "臺北市政府交通局路口時制號誌資料",
            "traffic_snapshot": format_ts(at),
            "selected_signal_count": len(signal_actions),
            "estimated_segment_ids": [row["segment_id"] for row in route_details if row["source"] == "estimated_fallback"],
            "constants": {
                "baseline_signal_delay_seconds": BASE_SIGNAL_DELAY_SECONDS,
                "corridor_signal_delay_seconds": CORRIDOR_SIGNAL_DELAY_SECONDS,
                "minimum_corridor_speed_kmh": MIN_CORRIDOR_SPEED_KMH,
                "maximum_corridor_speed_kmh": MAX_CORRIDOR_SPEED_KMH,
                "pedestrian_clearance_seconds": PEDESTRIAN_CLEARANCE_SECONDS,
            },
        },
        "decision_trace": [
            {"step": "EMERGENCY_DETECTED", "detail": {"vehicle_type": vehicle_type}},
            {"step": "TRAFFIC_SNAPSHOT_LOCKED", "detail": {"at": format_ts(at)}},
            {"step": "ROUTE_OPTIMIZED", "detail": {"segments": route_ids, "blocked": sorted(blocked)}},
            {"step": "SIGNALS_PREEMPTION_PLANNED", "detail": {"signals": len(signal_actions)}},
            {"step": "ETA_RECALCULATED", "detail": {"before": eta_before, "after": eta_after}},
            {"step": "HUMAN_APPROVAL_REQUIRED", "detail": {"status": "READY_FOR_APPROVAL"}},
        ],
        "model": "deterministic-green-corridor-v1",
        "approval_status": "READY_FOR_APPROVAL",
        "production_state_modified": False,
        "limitations": "號誌燈相、救援車位置與 ETA 為決策沙盒推估；未連接真實車聯網或號誌控制器。",
    }
    result["runtime_state"] = corridor_state_at(result, 0, approved=False)
    result["evidence_contract"] = {
        "data": ["road_network_geometry.json", "city_traffic_flow.csv", "signals.geojson", "roads.json"],
        "formula": result["eta"]["formula"],
        "rules": ["行人清空 8 秒", "不同路口任一時刻最多一個優先綠燈", "通過後 12 秒恢復"],
        "simulation": {"model": result["model"], "production_state_modified": False},
    }
    return result
