"""載入與清洗主辦方資料集。

所有時間欄位統一為 datetime；Roaming_User_Pct 由 "40%" 字串清洗為 float(40.0)。
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime

from .config import (
    CROWD_CSV,
    INCIDENTS_JSON,
    ROAD_NETWORK_JSON,
    SOP_TXT,
    TIME_FMT,
    TRAFFIC_CSV,
)


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value.strip(), TIME_FMT)


def format_ts(value: datetime) -> str:
    return value.strftime(TIME_FMT)


@dataclass(frozen=True)
class RoadSegment:
    segment_id: str
    name: str
    flow_direction: str
    intersections: tuple[str, ...]  # 依上游至下游排序
    capacity_vph: int
    alternatives: tuple[str, ...]  # 單向建議，不可假設對稱
    nearby_stations: tuple[str, ...]


@dataclass(frozen=True)
class TrafficRecord:
    timestamp: datetime
    segment_id: str
    road_name: str
    avg_speed: float
    vehicle_count: int
    saturation_score: float
    lane_status: str


@dataclass(frozen=True)
class CrowdRecord:
    timestamp: datetime
    bs_id: str
    location_name: str
    user_count: int
    stay_time_avg: float
    growth_rate: float
    roaming_user_pct: float  # 已清洗為數值，單位：百分比（30% -> 30.0）


def load_road_network(path=ROAD_NETWORK_JSON) -> dict[str, RoadSegment]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    network = {}
    for item in raw:
        seg = RoadSegment(
            segment_id=item["segment_id"],
            name=item["name"],
            flow_direction=item["flow_direction"],
            intersections=tuple(item["intersections"]),
            capacity_vph=int(item["capacity_vph"]),
            alternatives=tuple(item["alternatives"]),
            nearby_stations=tuple(item["nearby_stations"]),
        )
        network[seg.segment_id] = seg
    return network


def load_traffic(path=TRAFFIC_CSV) -> list[TrafficRecord]:
    records = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            records.append(
                TrafficRecord(
                    timestamp=parse_ts(row["Timestamp"]),
                    segment_id=row["Segment_ID"].strip(),
                    road_name=row["Road_Name"].strip(),
                    avg_speed=float(row["Avg_Speed"]),
                    vehicle_count=int(row["Vehicle_Count"]),
                    saturation_score=float(row["Saturation_Score"]),
                    lane_status=row["Lane_Status"].strip(),
                )
            )
    records.sort(key=lambda r: r.timestamp)
    return records


def _parse_pct(value: str) -> float:
    m = re.match(r"^\s*([0-9.]+)\s*%?\s*$", value)
    if not m:
        raise ValueError(f"無法解析百分比欄位: {value!r}")
    return float(m.group(1))


def load_crowd(path=CROWD_CSV) -> list[CrowdRecord]:
    records = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            records.append(
                CrowdRecord(
                    timestamp=parse_ts(row["Timestamp"]),
                    bs_id=row["BS_ID"].strip(),
                    location_name=row["Location_Name"].strip(),
                    user_count=int(row["User_Count"]),
                    stay_time_avg=float(row["Stay_Time_Avg"]),
                    growth_rate=float(row["Growth_Rate"]),
                    roaming_user_pct=_parse_pct(row["Roaming_User_Pct"]),
                )
            )
    records.sort(key=lambda r: r.timestamp)
    return records


def load_incidents(path=INCIDENTS_JSON) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_SOP_HEADER = re.compile(r"^(\d+)\.\s*(.+)$")


def load_sop_rules(path=SOP_TXT) -> dict[int, dict]:
    """把 SOP 文字檔切成 7 條規則，key 為 rule_id。"""
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    rules: dict[int, dict] = {}
    current = None
    for i, line in enumerate(lines):
        if set(line.strip()) == {"="} and line.strip():
            # 分隔線的下一行若是 "N. 標題" 則開新規則
            if i + 1 < len(lines):
                m = _SOP_HEADER.match(lines[i + 1].strip())
                if m:
                    current = int(m.group(1))
                    rules[current] = {
                        "rule_id": current,
                        "title": m.group(2).strip(),
                        "lines": [],
                    }
            continue
        if current is not None:
            m = _SOP_HEADER.match(line.strip())
            if m and int(m.group(1)) == current and not rules[current]["lines"]:
                continue  # 標題行本身
            rules[current]["lines"].append(line)
    for rule in rules.values():
        rule["text"] = "\n".join(rule.pop("lines")).strip()
    return rules


# ---- 快照工具 ----

def traffic_snapshot(records: list[TrafficRecord], at: datetime) -> dict[str, TrafficRecord]:
    """取每一路段在 at 時刻（含）之前的最新一筆紀錄。"""
    snap: dict[str, TrafficRecord] = {}
    for rec in records:
        if rec.timestamp <= at:
            snap[rec.segment_id] = rec
    return snap


def crowd_snapshot(records: list[CrowdRecord], at: datetime) -> dict[str, CrowdRecord]:
    snap: dict[str, CrowdRecord] = {}
    for rec in records:
        if rec.timestamp <= at:
            snap[rec.bs_id] = rec
    return snap


def crowd_peak(records: list[CrowdRecord], bs_id: str, until: datetime) -> int:
    """bs_id 在 until（含）之前的歷史峰值 User_Count；無資料回傳 0。"""
    counts = [r.user_count for r in records if r.bs_id == bs_id and r.timestamp <= until]
    return max(counts, default=0)


def all_timestamps(traffic: list[TrafficRecord], crowd: list[CrowdRecord]) -> list[datetime]:
    stamps = {r.timestamp for r in traffic} | {r.timestamp for r in crowd}
    return sorted(stamps)
