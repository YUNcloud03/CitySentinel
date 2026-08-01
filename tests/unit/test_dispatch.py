"""Resource Registry 與調度引擎測試。"""
import pytest

from app.data_loader import RoadSegment
from app.resources import dispatch_engine as de
from app.resources import registry as reg
from app.resources.registry import Resource, ResourceRegistry


def _small_registry():
    return ResourceRegistry([
        Resource("POL-01", reg.POLICE, "警力A", 4, 4, "分局", 6),
        Resource("POL-02", reg.POLICE, "警力B", 4, 4, "分局", 9),
        Resource("SIGC-01", reg.SIGNAL_CONTROL, "號誌控制", 3, 3, "交控", 1),
        Resource("SIG-01", reg.SIGNAL_MAINT, "搶修組", 1, 1, "交工處", 12),
    ])


def test_allocate_deducts_available():
    r = _small_registry()
    assignments, gap = r.allocate(reg.POLICE, 3)
    assert gap == 0
    # 依 ETA 由近至遠，先扣 POL-01
    assert assignments[0]["resource_id"] == "POL-01"
    assert assignments[0]["count"] == 3
    assert r.get("POL-01").available_count == 1


def test_allocate_spans_multiple_and_marks_full():
    r = _small_registry()
    assignments, gap = r.allocate(reg.POLICE, 6)  # 4 + 2
    assert gap == 0
    assert r.get("POL-01").available_count == 0
    assert r.get("POL-01").status == "Fully_Assigned"
    assert r.get("POL-02").available_count == 2


def test_allocate_reports_gap_when_insufficient():
    r = _small_registry()
    assignments, gap = r.allocate(reg.POLICE, 10)  # 只有 8
    assert gap == 2
    assert sum(a["count"] for a in assignments) == 8


def test_release_restores_available():
    r = _small_registry()
    assignments, _ = r.allocate(reg.POLICE, 4)
    r.release(assignments)
    assert r.get("POL-01").available_count == 4
    assert r.get("POL-01").status == "Available"


def test_reset_restores_all():
    r = _small_registry()
    r.allocate(reg.POLICE, 8)
    r.reset()
    assert r.get("POL-01").available_count == 4
    assert r.get("POL-02").available_count == 4


# ---- 調度政策 ----

def _seg(seg_id, intersections):
    return RoadSegment(seg_id, seg_id, "東西向", tuple(intersections), 1200, (), ())


def test_sop2_critical_needs_4_police_plus_signal():
    reqs = de.build_requirements(
        {"severity": "Critical", "affected_segment": "RD_TPE_002"},
        incident_rule_ids={2},
        crowd_rule_ids_for_incident=set(),
        routing_result={"primary_route": {"name": "市民大道四段", "segment_id": "RD_TPE_004"}},
        network={},
    )
    police = next(r for r in reqs if r["resource_type"] == reg.POLICE)
    assert police["requested_count"] == 4
    assert any(r["resource_type"] == reg.SIGNAL_CONTROL for r in reqs)


def test_sop5_two_police_per_intersection():
    net = {"RD_TPE_007": _seg("RD_TPE_007", ["基隆路一段", "市府路", "松智路"])}
    reqs = de.build_requirements(
        {"severity": "Medium", "affected_segment": "RD_TPE_007"},
        incident_rule_ids={5},
        crowd_rule_ids_for_incident=set(),
        routing_result=None,
        network=net,
    )
    police = next(r for r in reqs if r["resource_type"] == reg.POLICE)
    assert police["requested_count"] == 6  # 3 路口 × 2
    assert any(r["resource_type"] == reg.SIGNAL_MAINT for r in reqs)


def test_ambient_crowd_rules_do_not_drive_dispatch():
    """環境人流 SOP 3 若非事件本身，不得產生調度需求（規則歸因）。"""
    reqs = de.build_requirements(
        {"severity": "Critical", "affected_segment": "RD_TPE_002"},
        incident_rule_ids={2},
        crowd_rule_ids_for_incident=set(),  # 事件不是 BS，故無 SOP3
        routing_result={"primary_route": {"name": "市民大道四段", "segment_id": "RD_TPE_004"}},
        network={},
    )
    assert all(r["resource_type"] != reg.MRT_LIAISON for r in reqs)


def test_venue_crowd_dispatch_does_not_invent_mrt_bypass():
    reqs = de.build_requirements(
        {"severity": "High", "affected_segment": "BS_XY_ATT"},
        incident_rule_ids=set(),
        crowd_rule_ids_for_incident={3},
        routing_result=None,
        network={},
    )
    assert all(r["resource_type"] != reg.MRT_LIAISON for r in reqs)
    assert {r["resource_type"] for r in reqs} == {reg.POLICE, reg.SHUTTLE}
    assert any("場館出入口" in r["purpose"] for r in reqs)


def test_plan_dispatch_marks_shortfall_not_complete():
    r = ResourceRegistry([Resource("POL-01", reg.POLICE, "警力", 2, 2, "分局", 6)])
    reqs = [de._req(2, reg.POLICE, 4, "封鎖", "需 4 人")]
    plan = de.plan_dispatch(r, reqs, "SNAP-TEST")
    action = plan["actions"][0]
    assert action["status"] == "shortfall"
    assert action["gap"] == 2
    assert "未完成" in action["escalation"]
    assert plan["has_shortfall"] is True
