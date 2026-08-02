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
from ..simulation.incident_effects import project_incident
from .coordinator import DataBundle


ROADS_GEOJSON = PROJECT_ROOT / "frontend" / "src" / "data" / "roads.json"
SIGNALS_GEOJSON = PROJECT_ROOT / "frontend" / "public" / "data" / "signals.geojson"
HOSPITALS_GEOJSON = PROJECT_ROOT / "frontend" / "public" / "data" / "hospitals.geojson"

BASE_SIGNAL_DELAY_SECONDS = 24
CORRIDOR_SIGNAL_DELAY_SECONDS = 4
SIGNAL_PREEMPT_LEAD_SECONDS = 25
SIGNAL_RESTORE_BUFFER_SECONDS = 12
PEDESTRIAN_CLEARANCE_SECONDS = 8
MIN_CORRIDOR_SPEED_KMH = 32.0
MAX_CORRIDOR_SPEED_KMH = 50.0
SATURATION_ROUTE_PENALTY = 1.6
ON_SCENE_SERVICE_SECONDS = 45

# 醫院位置來自官方清冊；下列「可用救護車／急診負載」是 Demo 沙盒營運狀態，
# 不可冒充真實醫療量能。正式環境應由 119 與醫院急診介面即時提供。
HOSPITAL_OPERATIONS = {
    "H_TPE_RENAI": {"ambulances": ["AMB-RENAI-01", "AMB-RENAI-02"], "ed_load": 0.58, "accepting": True},
    "H_TPE_CATHAY": {"ambulances": ["AMB-CATHAY-01"], "ed_load": 0.64, "accepting": True},
    "H_TPE_TMUH": {"ambulances": ["AMB-TMUH-01", "AMB-TMUH-02"], "ed_load": 0.51, "accepting": True},
    "H_TPE_SHOWCHWAN": {"ambulances": ["AMB-SHOWCHWAN-01"], "ed_load": 0.78, "accepting": True},
    "H_TPE_CENTER": {"ambulances": ["AMB-CENTER-01"], "ed_load": 0.83, "accepting": True},
}


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


@lru_cache(maxsize=1)
def _hospital_assets() -> list[dict]:
    """Attach each official hospital point to its nearest challenge road."""
    hospitals_data = json.loads(HOSPITALS_GEOJSON.read_text(encoding="utf-8"))
    roads, _ = _map_assets()
    hospitals = []
    for feature in hospitals_data["features"]:
        hospital_id = feature.get("id") or feature["properties"].get("hospital_id")
        operations = HOSPITAL_OPERATIONS.get(hospital_id)
        if not operations:
            continue
        coordinate = feature["geometry"]["coordinates"]
        segment_id, distance = min(
            (
                (segment_id, _point_line_distance_m(tuple(coordinate), road["coordinates"]))
                for segment_id, road in roads.items()
            ),
            key=lambda row: (row[1], row[0]),
        )
        hospitals.append({
            "hospital_id": hospital_id,
            "name": feature["properties"]["name"],
            "address": feature["properties"].get("address"),
            "coordinates": coordinate,
            "segment_id": segment_id,
            "road_distance_m": round(distance),
            "source": feature["properties"].get("source"),
            **operations,
        })
    return sorted(hospitals, key=lambda row: row["hospital_id"])


def _route_cost(route_ids: list[str], metrics: dict[str, dict]) -> float:
    return round(sum(metrics[segment_id]["route_cost_seconds"] for segment_id in route_ids), 2)


def _candidate_route(
    graph: dict[str, set[str]], metrics: dict[str, dict], origin: str,
    destination: str, blocked: set[str],
) -> list[str] | None:
    if origin == destination:
        return None
    try:
        return _shortest_path(graph, metrics, origin, destination, blocked - {origin, destination})
    except ValueError:
        return None


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
        congestion_multiplier = 1 + max(0.0, traffic["saturation_score"] - 0.5) * SATURATION_ROUTE_PENALTY
        route_cost_seconds = baseline_seconds * congestion_multiplier
        lane_status = str(traffic["lane_status"]).lower()
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
            "congestion_multiplier": round(congestion_multiplier, 3),
            "route_cost_seconds": round(route_cost_seconds, 2),
            "impassable": "closed" in lane_status or "blocked" in lane_status,
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
            if neighbor != destination and metrics[neighbor]["impassable"]:
                continue
            heapq.heappush(
                queue,
                (cost + metrics[neighbor]["route_cost_seconds"], neighbor, path),
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


def _mission_messages(
    dispatch_name: str, receiving_name: str, ambulance_id: str, eta_after: int
) -> dict[str, str]:
    return {
        "zh": f"{dispatch_name} 的救護車 {ambulance_id} 將先前往事故現場，完成現場處置後送往 {receiving_name}；雙程預估 {eta_after} 分鐘。沿線請靠邊避讓並遵循號誌與現場指示。",
        "en": f"Ambulance {ambulance_id} from {dispatch_name} is responding to the scene and will then transport the patient to {receiving_name}. Estimated round-trip mission time: {eta_after} min. Please pull over.",
        "ja": f"{dispatch_name} の救急車 {ambulance_id} が事故現場へ向かい、処置後に {receiving_name} へ搬送します。所要時間は約 {eta_after} 分です。道を譲ってください。",
        "ko": f"{dispatch_name} 소속 구급차 {ambulance_id}가 사고 현장으로 출동한 뒤 환자를 {receiving_name}으로 이송합니다. 예상 임무 시간은 {eta_after}분입니다. 길을 양보해 주십시오.",
    }


def corridor_state_at(plan: dict, elapsed_seconds: int, approved: bool | None = None) -> dict:
    """Return deterministic rolling preemption state; at most one intersection is green."""
    elapsed = max(0, int(elapsed_seconds))
    is_approved = approved if approved is not None else plan.get("approval_status") == "APPROVED_FOR_SIMULATION"
    actions = plan.get("signal_actions", [])
    intersection_rows: dict[str, list[dict]] = {}
    for action in actions:
        execution_id = action.get("execution_id") or action["intersection_id"]
        intersection_rows.setdefault(execution_id, []).append(action)
    groups = sorted(
        intersection_rows.items(),
        key=lambda item: (min(row["prepare_at_seconds"] for row in item[1]), item[0]),
    )
    states = []
    current_intersection_id = None
    current_intersection_name = None
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
            current_intersection_name = rows[0]["name"]
            active_device_ids = device_ids
        elif state == "PEDESTRIAN_CLEARANCE":
            current_intersection_id = intersection_id
            current_intersection_name = rows[0]["name"]
            clearance_device_ids = device_ids
        states.append({
            "intersection_id": intersection_id,
            "source_intersection_id": rows[0]["intersection_id"],
            "name": rows[0]["name"],
            "mission_leg_id": rows[0].get("mission_leg_id"),
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
    mission_phase = "SINGLE_LEG"
    current_leg_id = None
    current_leg_progress = round(vehicle_fraction * 100, 1)
    mission = plan.get("mission")
    if mission and mission.get("legs"):
        first, second = mission["legs"]
        first_start, first_end = first["start_seconds"], first["travel_end_seconds"]
        second_start, second_end = second["start_seconds"], second["travel_end_seconds"]
        total = second["end_seconds"]
        if not is_approved:
            mission_phase, current_leg_id, vehicle_fraction = "AWAITING_APPROVAL", first["leg_id"], 0.0
            current_leg_progress = 0.0
            vehicle_position = first["route_geometry"][0]
        elif elapsed <= first_end:
            fraction = _clamped_fraction((elapsed - first_start) / max(1, first_end - first_start))
            mission_phase, current_leg_id = "TO_SCENE", first["leg_id"]
            current_leg_progress = round(fraction * 100, 1)
            vehicle_fraction = fraction * .45
            vehicle_position = _point_at_fraction(first["route_geometry"], fraction)
        elif elapsed < second_start:
            mission_phase, current_leg_id = "ON_SCENE", None
            current_leg_progress, vehicle_fraction = 100.0, .5
            vehicle_position = first["route_geometry"][-1]
        elif elapsed <= second_end:
            fraction = _clamped_fraction((elapsed - second_start) / max(1, second_end - second_start))
            mission_phase, current_leg_id = "TO_HOSPITAL", second["leg_id"]
            current_leg_progress = round(fraction * 100, 1)
            vehicle_fraction = .55 + fraction * .45
            vehicle_position = _point_at_fraction(second["route_geometry"], fraction)
        else:
            mission_phase, current_leg_id = "COMPLETED", second["leg_id"]
            current_leg_progress, vehicle_fraction = 100.0, 1.0
            vehicle_position = second["route_geometry"][-1]
    next_intersection = next(
        (row for row in states if row["state"] in {"PEDESTRIAN_CLEARANCE", "EMERGENCY_GREEN", "WAITING"}),
        None,
    )
    return {
        "elapsed_seconds": elapsed,
        "total_seconds": total,
        "completed": bool(is_approved and elapsed > total),
        "current_intersection_id": current_intersection_id,
        "current_intersection_name": current_intersection_name,
        "active_signal_device_ids": active_device_ids,
        "clearance_signal_device_ids": clearance_device_ids,
        "vehicle_position": vehicle_position,
        "vehicle_progress_pct": round(vehicle_fraction * 100, 1),
        "current_leg_progress_pct": current_leg_progress,
        "mission_phase": mission_phase,
        "current_leg_id": current_leg_id,
        "vehicle_position_source": "simulated_from_route_geometry_and_corridor_elapsed_time",
        "next_intersection_id": next_intersection["intersection_id"] if next_intersection else None,
        "next_intersection_name": next_intersection["name"] if next_intersection else None,
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
    incident_context = {"active": False}
    if scenario.get("_incident_state"):
        snapshot, incident_context = project_incident(
            at=at,
            baseline=snapshot,
            incident_state=scenario["_incident_state"],
            network=bundle.network,
        )
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
            "traffic_source": "incident_projection" if incident_context.get("active") else "organizer_snapshot",
            "incident_id": incident_context.get("incident_id"),
            "route_score_formula": "travel_time_seconds × (1 + max(0, saturation_score - 0.5) × 1.6)",
            "selected_signal_count": len(signal_actions),
            "estimated_segment_ids": [row["segment_id"] for row in route_details if row["source"] == "estimated_fallback"],
            "constants": {
                "baseline_signal_delay_seconds": BASE_SIGNAL_DELAY_SECONDS,
                "corridor_signal_delay_seconds": CORRIDOR_SIGNAL_DELAY_SECONDS,
                "minimum_corridor_speed_kmh": MIN_CORRIDOR_SPEED_KMH,
                "maximum_corridor_speed_kmh": MAX_CORRIDOR_SPEED_KMH,
                "pedestrian_clearance_seconds": PEDESTRIAN_CLEARANCE_SECONDS,
                "saturation_route_penalty": SATURATION_ROUTE_PENALTY,
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
        "model": "deterministic-green-corridor-v2-traffic-weighted",
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


def simulate_rescue_mission(bundle: DataBundle, scenario: dict) -> dict:
    """Automatically select an available ambulance and build hospital→scene→hospital legs."""
    incident_state = scenario.get("_incident_state")
    if not incident_state:
        raise ValueError("自動雙程救援需要先注入進行中的事件")
    event = incident_state.get("event") or {}
    scene_segment_id = event.get("affected_segment")
    if not isinstance(scene_segment_id, str) or not scene_segment_id.startswith("RD_"):
        raise ValueError("自動雙程救援目前僅適用具有道路位置的事件")
    if scene_segment_id not in bundle.network:
        raise KeyError(f"事件路段 {scene_segment_id} 不存在於主辦方路網")

    at = parse_ts(scenario.get("at") or event.get("timestamp"))
    blocked = set(scenario.get("blocked_segment_ids") or [])
    unavailable_units = set(scenario.get("_unavailable_unit_ids") or [])
    baseline = bundle.traffic_at(at)
    snapshot, incident_context = project_incident(
        at=at, baseline=baseline, incident_state=incident_state, network=bundle.network,
    )
    metrics = _segment_metrics(bundle, snapshot)
    graph = _graph(bundle.network)
    roads, _ = _map_assets()
    scene_coordinate = _point_at_fraction(roads[scene_segment_id]["coordinates"], .5)

    dispatch_candidates = []
    receiving_candidates = []
    for hospital in _hospital_assets():
        available_units = [unit for unit in hospital["ambulances"] if unit not in unavailable_units]
        to_scene = _candidate_route(
            graph, metrics, hospital["segment_id"], scene_segment_id, blocked,
        )
        if available_units and to_scene:
            dispatch_candidates.append({
                **hospital,
                "available_units": available_units,
                "route": to_scene,
                "score_seconds": _route_cost(to_scene, metrics),
            })
        to_hospital = _candidate_route(
            graph, metrics, scene_segment_id, hospital["segment_id"], blocked,
        )
        if hospital["accepting"] and to_hospital:
            route_seconds = _route_cost(to_hospital, metrics)
            receiving_candidates.append({
                **hospital,
                "route": to_hospital,
                "route_seconds": route_seconds,
                "score_seconds": round(route_seconds * (1 + hospital["ed_load"] * .25), 2),
            })
    if not dispatch_candidates:
        raise ValueError("事件周邊沒有可用且可達的救護車")
    if not receiving_candidates:
        raise ValueError("找不到可由事故現場抵達且可收治的醫院")

    dispatch = min(dispatch_candidates, key=lambda row: (row["score_seconds"], row["hospital_id"]))
    receiving = min(receiving_candidates, key=lambda row: (row["score_seconds"], row["hospital_id"]))
    ambulance_id = dispatch["available_units"][0]
    common = {
        "at": format_ts(at), "vehicle_type": "Ambulance",
        "blocked_segment_ids": sorted(blocked), "_incident_state": incident_state,
    }
    first = simulate_green_corridor(bundle, {
        **common,
        "origin_segment_id": dispatch["segment_id"],
        "destination_segment_id": scene_segment_id,
    })
    second = simulate_green_corridor(bundle, {
        **common,
        "origin_segment_id": scene_segment_id,
        "destination_segment_id": receiving["segment_id"],
    })

    first_geometry = [dispatch["coordinates"], *first["route_geometry"]]
    if scene_coordinate and first_geometry[-1] != scene_coordinate:
        first_geometry.append(scene_coordinate)
    second_geometry = [scene_coordinate, *second["route_geometry"]] if scene_coordinate else list(second["route_geometry"])
    if second_geometry[-1] != receiving["coordinates"]:
        second_geometry.append(receiving["coordinates"])

    first_passage = max((row["passage_at_seconds"] for row in first["signal_actions"]), default=first["eta"]["after_minutes"] * 60)
    first_end = max((row["restore_at_seconds"] for row in first["signal_actions"]), default=first_passage)
    second_offset = first_end + ON_SCENE_SERVICE_SECONDS
    second_passage = second_offset + max(
        (row["passage_at_seconds"] for row in second["signal_actions"]),
        default=second["eta"]["after_minutes"] * 60,
    )
    second_end = second_offset + max(
        (row["restore_at_seconds"] for row in second["signal_actions"]),
        default=second["eta"]["after_minutes"] * 60,
    )

    signal_actions = []
    for leg_id, rows, offset in (
        ("TO_SCENE", first["signal_actions"], 0),
        ("TO_HOSPITAL", second["signal_actions"], second_offset),
    ):
        for action in rows:
            # 同一任務階段、同一實體路口的所有燈具必須共用 execution_id，
            # 才會在 runtime 中被視為一組同步清空、轉綠與恢復。
            shifted = {**action, "mission_leg_id": leg_id,
                       "execution_id": f"{leg_id}:{action['intersection_id']}"}
            for field in ("prepare_at_seconds", "activate_at_seconds", "passage_at_seconds", "restore_at_seconds"):
                shifted[field] = action[field] + offset
            signal_actions.append(shifted)

    service_minutes = ON_SCENE_SERVICE_SECONDS / 60
    before_minutes = math.ceil(first["eta"]["before_minutes"] + second["eta"]["before_minutes"] + service_minutes)
    after_minutes = math.ceil(first["eta"]["after_minutes"] + second["eta"]["after_minutes"] + service_minutes)
    mission = {
        "mode": "AUTO_HOSPITAL_ROUND_TRIP",
        "incident_id": incident_state.get("incident_id") or event.get("event_id"),
        "scene": {
            "name": event.get("location") or bundle.network[scene_segment_id].name,
            "segment_id": scene_segment_id,
            "coordinates": scene_coordinate,
        },
        "ambulance": {
            "unit_id": ambulance_id, "status": "RESERVED_FOR_APPROVAL",
            "inventory_source": "demo_sandbox_operations",
        },
        "dispatch_hospital": {
            key: dispatch[key] for key in ("hospital_id", "name", "address", "coordinates", "segment_id", "road_distance_m")
        },
        "receiving_hospital": {
            **{key: receiving[key] for key in ("hospital_id", "name", "address", "coordinates", "segment_id", "road_distance_m")},
            "ed_load": receiving["ed_load"], "accepting": receiving["accepting"],
            "operations_source": "demo_sandbox_operations",
        },
        "on_scene_service_seconds": ON_SCENE_SERVICE_SECONDS,
        "legs": [
            {
                "leg_id": "TO_SCENE", "label": "醫院 → 事故現場",
                "start_name": dispatch["name"], "end_name": event.get("location") or bundle.network[scene_segment_id].name,
                "route_segment_ids": first["route_segment_ids"], "route_names": first["route_names"],
                "route_geometry": first_geometry, "route_details": first["route_details"], "eta": first["eta"],
                "start_seconds": 0, "travel_end_seconds": first_passage, "end_seconds": first_end,
            },
            {
                "leg_id": "TO_HOSPITAL", "label": "事故現場 → 收治醫院",
                "start_name": event.get("location") or bundle.network[scene_segment_id].name, "end_name": receiving["name"],
                "route_segment_ids": second["route_segment_ids"], "route_names": second["route_names"],
                "route_geometry": second_geometry, "route_details": second["route_details"], "eta": second["eta"],
                "start_seconds": second_offset, "travel_end_seconds": second_passage, "end_seconds": second_end,
            },
        ],
    }
    combined_geometry = [*first_geometry]
    combined_geometry.extend(point for point in second_geometry if not combined_geometry or point != combined_geometry[-1])
    result = {
        "scenario_id": (
            f"RM-{at:%Y%m%d-%H%M}-{scene_segment_id[-3:]}-"
            f"{dispatch['hospital_id'].removeprefix('H_TPE_')}-{ambulance_id[-2:]}"
        ),
        "as_of": format_ts(at), "vehicle_type": "Ambulance", "priority": "EMERGENCY",
        "route_segment_ids": first["route_segment_ids"] + second["route_segment_ids"],
        "route_names": first["route_names"] + second["route_names"],
        "route_geometry": combined_geometry,
        "route_details": [
            *({**row, "mission_leg_id": "TO_SCENE"} for row in first["route_details"]),
            *({**row, "mission_leg_id": "TO_HOSPITAL"} for row in second["route_details"]),
        ],
        "blocked_segment_ids": sorted(blocked),
        "eta": {
            "before_minutes": before_minutes, "after_minutes": after_minutes,
            "saved_minutes": max(0, before_minutes - after_minutes),
            "improvement_pct": round(max(0, before_minutes - after_minutes) / max(1, before_minutes) * 100, 1),
            "formula": "雙程 ETA = 醫院至現場路線 + 現場處置 45 秒 + 現場至收治醫院路線；各段皆以 Σ(道路長度÷速度)+Σ號誌延誤計算",
        },
        "signal_actions": signal_actions,
        "dispatch_recommendation": {
            "resource_type": "Ambulance", "requested_units": 1, "unit_id": ambulance_id,
            "critical_segment_ids": sorted(set(first["dispatch_recommendation"]["critical_segment_ids"] + second["dispatch_recommendation"]["critical_segment_ids"])),
            "reason": f"自動選擇可最快抵達的 {dispatch['name']} {ambulance_id}",
        },
        "messages": _mission_messages(dispatch["name"], receiving["name"], ambulance_id, after_minutes),
        "mission": mission,
        "evidence": {
            "road_topology_source": "road_network_geometry.json",
            "geometry_source": "官方道路與醫院點位；醫院到道路含 last-mile connector",
            "hospital_source": "臺北市政府衛生局－臺北市公私立醫療院所（醫院清冊）",
            "ambulance_inventory_source": "demo_sandbox_operations_not_live_119",
            "hospital_selection_formula": "派車取可用救護車中路況成本最低者；收治醫院取路況成本×(1+急診模擬負載×0.25)最低者",
            "traffic_snapshot": format_ts(at),
            "traffic_source": "incident_projection" if incident_context.get("active") else "organizer_snapshot",
            "incident_id": incident_context.get("incident_id"),
            "route_score_formula": "travel_time_seconds × (1 + max(0, saturation_score - 0.5) × 1.6)",
            "selected_signal_count": len(signal_actions),
            "dispatch_candidates": [
                {"hospital_id": row["hospital_id"], "name": row["name"], "score_seconds": row["score_seconds"], "available_units": row["available_units"]}
                for row in sorted(dispatch_candidates, key=lambda row: row["score_seconds"])
            ],
            "receiving_candidates": [
                {"hospital_id": row["hospital_id"], "name": row["name"], "score_seconds": row["score_seconds"], "ed_load": row["ed_load"]}
                for row in sorted(receiving_candidates, key=lambda row: row["score_seconds"])
            ],
        },
        "decision_trace": [
            {"step": "INCIDENT_LOCATION_LOCKED", "detail": {"segment_id": scene_segment_id}},
            {"step": "AVAILABLE_AMBULANCE_SELECTED", "detail": {"hospital_id": dispatch["hospital_id"], "unit_id": ambulance_id}},
            {"step": "TO_SCENE_ROUTE_OPTIMIZED", "detail": {"segments": first["route_segment_ids"]}},
            {"step": "RECEIVING_HOSPITAL_SELECTED", "detail": {"hospital_id": receiving["hospital_id"], "ed_load": receiving["ed_load"]}},
            {"step": "TO_HOSPITAL_ROUTE_OPTIMIZED", "detail": {"segments": second["route_segment_ids"]}},
            {"step": "SIGNALS_PREEMPTION_PLANNED", "detail": {"signals": len(signal_actions)}},
            {"step": "HUMAN_APPROVAL_REQUIRED", "detail": {"status": "READY_FOR_APPROVAL"}},
        ],
        "model": "deterministic-rescue-mission-v3-round-trip",
        "approval_status": "READY_FOR_APPROVAL", "production_state_modified": False,
        "limitations": "醫院位置為官方資料；救護車庫存與急診負載為 Demo 沙盒資料。路線、燈相、位置與 ETA 為模擬，未連接 119、醫院 HIS、車聯網或正式號誌控制器。",
    }
    result["runtime_state"] = corridor_state_at(result, 0, approved=False)
    result["evidence_contract"] = {
        "data": ["road_network_geometry.json", "city_traffic_flow.csv", "signals.geojson", "hospitals.geojson"],
        "formula": result["eta"]["formula"],
        "rules": ["人工核准後才派車", "一次只預控下一路口", "到場處置後重新啟動送醫路線"],
        "simulation": {"model": result["model"], "production_state_modified": False},
    }
    return result
