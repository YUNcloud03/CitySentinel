"""SOP 第 2 條：替代路徑（疏散路徑）規劃。

不是最短路徑演算法，而是 SOP 約束下的候選篩選：
    1. 候選僅來自事故路段的 alternatives（單向建議，不可反向擴展）。
    2. capacity_vph >= 1000。
    3. 必須與事故路段直接相交（出現在其 intersections 中）。
    4. 依事故位置與 intersections（上游→下游排序）判定上下游；
       上游候選取 Saturation_Score 最低者為主疏散，下游僅列次要疏散。
    5. 主疏散若已壅塞（>= 0.85）仍維持，但啟動長綠燈並建議併行大眾運輸。
所有被排除的候選都保留排除理由（reason_code）供決策鏈展示。
"""
from __future__ import annotations

from ..data_loader import RoadSegment, TrafficRecord

MIN_CAPACITY_VPH = 1000
CONGESTED_THRESHOLD = 0.85

# 排除理由代碼
EXCL_UNKNOWN_SEGMENT = "UNKNOWN_SEGMENT"
EXCL_CAPACITY = "CAPACITY_BELOW_1000"
EXCL_NOT_INTERSECTING = "NOT_DIRECT_INTERSECTION"


def locate_incident_intersection(
    segment: RoadSegment, incident_location: str | None
) -> int | None:
    """從事故位置文字找出對應的相交路口 index（上游→下游）。

    例：光復南路 intersections = (市民大道四段, 忠孝東路四段, 仁愛路四段)，
    位置「光復南路與忠孝東路口南側」→ 回傳 1（忠孝東路四段）。
    「南側」代表事故點在該路口的下游側，因此 index <= 1 的路口皆屬上游。
    找不到時回傳 None（此時所有相交候選一律視為上游）。
    """
    if not incident_location:
        return None
    for idx, name in enumerate(segment.intersections):
        # 路名常見簡寫（忠孝東路 vs 忠孝東路四段），雙向包含比對
        short = name.rstrip("一二三四五六七八九十段")
        if name in incident_location or (short and short in incident_location):
            return idx
    return None


def plan_evacuation(
    affected_segment_id: str,
    network: dict[str, RoadSegment],
    traffic_snapshot: dict[str, TrafficRecord],
    incident_location: str | None = None,
) -> dict:
    segment = network[affected_segment_id]
    incident_idx = locate_incident_intersection(segment, incident_location)

    upstream: list[dict] = []
    downstream: list[dict] = []
    excluded: list[dict] = []

    for alt_id in segment.alternatives:
        alt = network.get(alt_id)
        if alt is None:
            excluded.append(
                {"segment_id": alt_id, "reason_code": EXCL_UNKNOWN_SEGMENT,
                 "detail": "路網資料中不存在此路段"}
            )
            continue
        if alt.capacity_vph < MIN_CAPACITY_VPH:
            excluded.append(
                {"segment_id": alt_id, "name": alt.name,
                 "reason_code": EXCL_CAPACITY,
                 "detail": f"capacity_vph {alt.capacity_vph} < {MIN_CAPACITY_VPH}"}
            )
            continue
        if alt.name not in segment.intersections:
            excluded.append(
                {"segment_id": alt_id, "name": alt.name,
                 "reason_code": EXCL_NOT_INTERSECTING,
                 "detail": f"未出現在 {segment.name} 的 intersections 中，非直接相交"}
            )
            continue

        idx = segment.intersections.index(alt.name)
        rec = traffic_snapshot.get(alt_id)
        candidate = {
            "segment_id": alt_id,
            "name": alt.name,
            "capacity_vph": alt.capacity_vph,
            "intersection_index": idx,
            "saturation_score": rec.saturation_score if rec else None,
            "saturation_timestamp": rec.timestamp if rec else None,
        }
        if incident_idx is not None and idx > incident_idx:
            downstream.append(candidate)
        else:
            upstream.append(candidate)

    # 上游依飽和度由低至高排序；無即時資料者排最後
    upstream.sort(
        key=lambda c: (c["saturation_score"] is None, c["saturation_score"] or 0.0)
    )

    primary = None
    secondary: list[dict] = []
    if upstream:
        primary = dict(upstream[0])
        reasons = ["UPSTREAM", "DIRECT_INTERSECTION", "CAPACITY_OK", "LOWEST_SATURATION"]
        sat = primary["saturation_score"]
        primary["congested"] = sat is not None and sat >= CONGESTED_THRESHOLD
        if primary["congested"]:
            reasons.append("CONGESTED_KEEP_WITH_LONG_GREEN")
            primary["advisory"] = (
                "主疏散路段已壅塞（Saturation >= 0.85），仍維持該路徑，"
                "啟動長綠燈時制並建議併行大眾運輸"
            )
        primary["reason_codes"] = reasons
        for cand in upstream[1:]:
            secondary.append({**cand, "role_reason": "UPSTREAM_BACKUP"})
    for cand in downstream:
        secondary.append({**cand, "role_reason": "DOWNSTREAM"})

    return {
        "affected_segment": {
            "segment_id": segment.segment_id,
            "name": segment.name,
            "flow_direction": segment.flow_direction,
            "intersections": list(segment.intersections),
        },
        "incident_location": incident_location,
        "incident_intersection_index": incident_idx,
        "primary_route": primary,
        "secondary_routes": secondary,
        "excluded_routes": excluded,
    }
