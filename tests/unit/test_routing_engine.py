"""技術文件 19.2 Routing 測試案例。"""
from datetime import datetime

from app.data_loader import RoadSegment, TrafficRecord
from app.engines import routing_engine

AT = datetime(2026, 5, 20, 22, 10)


def _seg(seg_id, name, intersections, capacity, alternatives):
    return RoadSegment(
        segment_id=seg_id, name=name, flow_direction="南北向",
        intersections=tuple(intersections), capacity_vph=capacity,
        alternatives=tuple(alternatives), nearby_stations=(),
    )


def _traffic(seg_id, sat):
    return TrafficRecord(
        timestamp=AT, segment_id=seg_id, road_name=seg_id, avg_speed=30,
        vehicle_count=1000, saturation_score=sat, lane_status="Normal",
    )


def _demo_network():
    """光復南路事故的真實拓撲縮影 + 一條容量 999 的假路。"""
    return {
        "RD_X": _seg("RD_X", "主事故路", ["甲路", "乙路", "丙路"], 1800,
                     ["RD_A", "RD_B", "RD_C", "RD_D"]),
        "RD_A": _seg("RD_A", "甲路", ["主事故路"], 2500, []),      # 上游相交
        "RD_B": _seg("RD_B", "丙路", ["主事故路"], 4000, []),      # 下游相交
        "RD_C": _seg("RD_C", "丁路", ["別的路"], 3200, []),        # 不相交
        "RD_D": _seg("RD_D", "乙路", ["主事故路"], 999, []),       # 容量不足
    }


def test_capacity_999_excluded():
    net = _demo_network()
    snap = {k: _traffic(k, 0.5) for k in net}
    result = routing_engine.plan_evacuation("RD_X", net, snap, "主事故路與乙路口南側")
    excluded = {e["segment_id"]: e["reason_code"] for e in result["excluded_routes"]}
    assert excluded["RD_D"] == routing_engine.EXCL_CAPACITY


def test_not_intersecting_excluded():
    net = _demo_network()
    snap = {k: _traffic(k, 0.5) for k in net}
    result = routing_engine.plan_evacuation("RD_X", net, snap, "主事故路與乙路口南側")
    excluded = {e["segment_id"]: e["reason_code"] for e in result["excluded_routes"]}
    assert excluded["RD_C"] == routing_engine.EXCL_NOT_INTERSECTING


def test_downstream_cannot_be_primary():
    net = _demo_network()
    # 下游（丙路）飽和度最低，但仍不得成為主疏散
    snap = {"RD_A": _traffic("RD_A", 0.70), "RD_B": _traffic("RD_B", 0.10)}
    result = routing_engine.plan_evacuation("RD_X", net, snap, "主事故路與乙路口南側")
    assert result["primary_route"]["segment_id"] == "RD_A"
    roles = {s["segment_id"]: s["role_reason"] for s in result["secondary_routes"]}
    assert roles["RD_B"] == "DOWNSTREAM"


def test_congested_primary_kept_with_advisory():
    net = _demo_network()
    snap = {"RD_A": _traffic("RD_A", 0.90), "RD_B": _traffic("RD_B", 0.10)}
    result = routing_engine.plan_evacuation("RD_X", net, snap, "主事故路與乙路口南側")
    primary = result["primary_route"]
    assert primary["segment_id"] == "RD_A"  # 已壅塞仍維持
    assert primary["congested"] is True
    assert "長綠燈" in primary["advisory"]
    assert "大眾運輸" in primary["advisory"]


def test_alternatives_not_expanded_bidirectionally():
    """候選只來自事故路段自己的 alternatives，不得反向推導。"""
    net = _demo_network()
    snap = {k: _traffic(k, 0.5) for k in net}
    result = routing_engine.plan_evacuation("RD_X", net, snap, None)
    mentioned = {result["primary_route"]["segment_id"]} \
        | {s["segment_id"] for s in result["secondary_routes"]} \
        | {e["segment_id"] for e in result["excluded_routes"]}
    assert mentioned <= set(net["RD_X"].alternatives)


def test_unknown_intersection_defaults_all_upstream():
    net = _demo_network()
    snap = {k: _traffic(k, 0.5) for k in net}
    result = routing_engine.plan_evacuation("RD_X", net, snap, "無法辨識的位置")
    assert result["incident_intersection_index"] is None
    assert result["primary_route"] is not None
