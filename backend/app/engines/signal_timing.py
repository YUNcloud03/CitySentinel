"""Deterministic, auditable next-cycle traffic signal allocation."""
from __future__ import annotations

from ..data_loader import format_ts

CYCLE_SECONDS = 90
LOST_SECONDS_PER_APPROACH = 4
MIN_GREEN_SECONDS = 10
MAX_GREEN_SECONDS = 50
REFERENCE_SPEED_KMH = 40.0
REFERENCE_CROWD_PER_STATION = 40_000
WEIGHTS = {"vehicle_flow": 0.35, "saturation": 0.25, "speed_pressure": 0.15,
           "waiting_time": 0.15, "pedestrian_demand": 0.10}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_signal_plan(bundle, at, segment_ids: list[str]) -> dict:
    ordered_ids = list(dict.fromkeys(segment_ids))
    if not 2 <= len(ordered_ids) <= 4:
        raise ValueError("號誌配時需提供 2 至 4 個不重複方向路段")
    unknown = set(ordered_ids) - set(bundle.network)
    if unknown:
        raise KeyError(f"未知號誌方向路段：{', '.join(sorted(unknown))}")

    traffic, crowd, rows = bundle.traffic_at(at), bundle.crowd_at(at), []
    for segment_id in ordered_ids:
        segment, record = bundle.network[segment_id], traffic.get(segment_id)
        if record:
            speed, count, saturation = record.avg_speed, record.vehicle_count, record.saturation_score
            data_time, source = format_ts(record.timestamp), "organizer_observation_or_last_known"
        else:
            speed, count, saturation = 30.0, round(segment.capacity_vph * 0.45), 0.55
            data_time, source = None, "estimated_fallback"
        nearby = [crowd[station] for station in segment.nearby_stations if station in crowd]
        users = sum(row.user_count for row in nearby)
        crowd_base = max(1, len(segment.nearby_stations)) * REFERENCE_CROWD_PER_STATION
        pedestrian = _clamp(users / crowd_base, 0.0, 1.0)
        flow = _clamp(count / segment.capacity_vph, 0.0, 1.5) / 1.5
        speed_pressure = _clamp((REFERENCE_SPEED_KMH - speed) / REFERENCE_SPEED_KMH, 0.0, 1.0)
        # 主辦方沒有等待時間欄位；此值必須明標為估計，不能冒充感測觀測。
        wait_seconds = round(10 + 50 * _clamp(saturation, 0.0, 1.0), 1)
        score = (WEIGHTS["vehicle_flow"] * flow + WEIGHTS["saturation"] * _clamp(saturation, 0, 1)
                 + WEIGHTS["speed_pressure"] * speed_pressure
                 + WEIGHTS["waiting_time"] * wait_seconds / 60
                 + WEIGHTS["pedestrian_demand"] * pedestrian)
        rows.append({
            "segment_id": segment_id, "name": segment.name,
            "inputs": {"vehicle_count": count, "capacity_vph": segment.capacity_vph,
                       "saturation_score": saturation, "avg_speed_kmh": speed,
                       "estimated_wait_seconds": wait_seconds, "nearby_user_count": users},
            "input_source": source, "traffic_data_time": data_time,
            "wait_time_source": "estimated_from_saturation_not_observed",
            "demand_score": round(score, 4),
            "safety_minimum_green_seconds": MIN_GREEN_SECONDS + round(5 * pedestrian),
        })

    budget = CYCLE_SECONDS - LOST_SECONDS_PER_APPROACH * len(rows)
    minimum_total = sum(row["safety_minimum_green_seconds"] for row in rows)
    score_total = sum(row["demand_score"] for row in rows) or len(rows)
    raw = [row["safety_minimum_green_seconds"] + (budget - minimum_total) * row["demand_score"] / score_total
           for row in rows]
    seconds = [min(MAX_GREEN_SECONDS, int(value)) for value in raw]
    remaining = budget - sum(seconds)
    order = sorted(range(len(rows)), key=lambda i: (raw[i] - int(raw[i]), rows[i]["demand_score"]), reverse=True)
    while remaining > 0:
        changed = False
        for index in order:
            if remaining and seconds[index] < MAX_GREEN_SECONDS:
                seconds[index] += 1
                remaining -= 1
                changed = True
        if not changed:
            break
    for row, green in zip(rows, seconds):
        row["next_green_seconds"] = green

    return {
        "as_of": format_ts(at), "cycle_seconds": CYCLE_SECONDS,
        "lost_seconds": LOST_SECONDS_PER_APPROACH * len(rows), "green_budget_seconds": budget,
        "approaches": rows,
        "formula": "demand=0.35×車流容量比+0.25×飽和度+0.15×低速壓力+0.15×等待+0.10×行人需求；綠燈=行人安全下限+剩餘秒數×需求占比",
        "weights": WEIGHTS,
        "safety_constraints": {"minimum_green_seconds": MIN_GREEN_SECONDS,
                               "maximum_green_seconds": MAX_GREEN_SECONDS,
                               "pedestrian_adjusted_minimum_range_seconds": [10, 15]},
        "model": "deterministic-signal-timing-v1",
        "limitations": ["主辦方資料不是逐車道/逐方向資料，路段在此作為方向代理",
                        "等待時間由飽和度估計，接入排隊感測器後應替換",
                        "結果只供下一輪模擬，不直接控制正式號誌"],
    }
