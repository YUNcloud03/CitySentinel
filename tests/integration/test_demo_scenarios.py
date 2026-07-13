"""三個官方 Demo 事件的端到端整合測試（使用真實主辦資料）。"""
import pytest

from app.coordinator.coordinator import Coordinator, DataBundle
from app.coordinator.whatif import run_what_if


@pytest.fixture(scope="module")
def coordinator():
    return Coordinator(DataBundle())


def test_data_loaded(coordinator):
    b = coordinator.bundle
    assert len(b.network) == 15
    assert len(b.traffic) == 112
    assert len(b.crowd) == 36
    assert len(b.sop.rules) == 7
    # 漫遊率已清洗為數值
    assert all(isinstance(r.roaming_user_pct, float) for r in b.crowd)


def test_acc_001_road_collapse(coordinator):
    """場景 2：光復南路塌陷（Closed / Critical / 22:10）。"""
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    assert state["workflow_status"] == "completed"
    assert 2 in state["triggered_rules"]

    routing = state["routing_result"]
    # 上游相交且容量足夠者中飽和度最低 → 市民大道四段（22:00 快照 0.78）
    assert routing["primary_route"]["segment_id"] == "RD_TPE_004"
    excluded = {e["segment_id"]: e["reason_code"] for e in routing["excluded_routes"]}
    assert excluded["RD_TPE_008"] == "CAPACITY_BELOW_1000"       # 延吉街 600 vph
    assert excluded["RD_TPE_006"] == "NOT_DIRECT_INTERSECTION"   # 敦化南路一段不相交
    # 仁愛路四段在事故點（忠孝東路口南側）下游 → 僅次要疏散
    roles = {s["segment_id"]: s["role_reason"] for s in routing["secondary_routes"]}
    assert roles["RD_TPE_005"] == "DOWNSTREAM"

    # ETE：Critical=60 + (1.00-0.5)*60 = 90
    assert state["ete_result"]["ete_minutes"] == pytest.approx(90.0)

    # CMS 依 SOP 2b 格式
    cms = state["notifications"]["cms"]
    assert "光復南路" in cms and "市民大道四段" in cms and "90" in cms


def test_evt_002_crowd_surge(coordinator):
    """場景 3：BL17 人群推擠（BS_ 事件 → 走第 3 條，不觸發第 2 條）。"""
    state = coordinator.inject_incident("TPE_2026_EVT_002")
    assert state["workflow_status"] == "completed"
    assert 2 not in state["triggered_rules"]
    assert 3 in state["triggered_rules"]  # 22:15 快照 BL17 = 31,000 > 25,000
    rule3 = next(t for t in state["trigger_details"] if t["rule_id"] == 3)
    assert rule3["evidence"]["user_count"] == 31_000
    assert any("BL18" in a for a in rule3["actions"])
    # ETE 用 affected_road RD_TPE_001（High=40 + (1.00-0.5)*60 = 70）
    assert state["ete_result"]["ete_minutes"] == pytest.approx(70.0)


def test_evt_003_power_failure(coordinator):
    """場景 4：松高路號誌故障（Power_Failure / Medium / 22:30）。"""
    state = coordinator.inject_incident("TPE_2026_EVT_003")
    assert state["workflow_status"] == "completed"
    assert 5 in state["triggered_rules"]
    assert 2 not in state["triggered_rules"]  # status=Caution 不符第 2 條
    # ETE：Medium=20 + (0.85-0.5)*60 = 41
    assert state["ete_result"]["ete_minutes"] == pytest.approx(41.0)
    assert "號誌故障" in state["notifications"]["cms"]
    assert "現場指揮" in state["notifications"]["cms"]


def test_what_if_bl17_40000(coordinator):
    """場景 6：如果 BL17 人數增加到 40,000 人會怎樣？（於 17:00，基準未觸發第 3 條）"""
    result = run_what_if(coordinator.bundle, {
        "at": "2026-05-20 17:00",
        "crowd_overrides": {"BS_MRT_BL17": {"user_count": 40_000}},
    })
    assert 3 not in result["baseline"]["triggered_rules"]
    assert 3 in result["sandbox"]["triggered_rules"]
    assert 3 in result["diff"]["newly_triggered_rules"]
    assert result["production_state_modified"] is False
    # 正式資料未被改動
    snap = coordinator.bundle.crowd_at(__import__("datetime").datetime(2026, 5, 20, 17, 0))
    assert snap["BS_MRT_BL17"].user_count != 40_000


def test_active_monitoring_thresholds(coordinator):
    """場景 1：主動監測——21:00 忠孝東路達 B 級、21:30 達 A 級。"""
    from datetime import datetime
    from app.engines import rule_engine

    snap_2100 = coordinator.bundle.traffic_at(datetime(2026, 5, 20, 21, 0))
    eval_2100 = rule_engine.evaluate_traffic(snap_2100)
    assert eval_2100["levels"]["RD_TPE_001"] == "B"

    snap_2130 = coordinator.bundle.traffic_at(datetime(2026, 5, 20, 21, 30))
    eval_2130 = rule_engine.evaluate_traffic(snap_2130)
    assert eval_2130["levels"]["RD_TPE_001"] == "A"
    rd001 = next(t for t in eval_2130["triggers"] if t["entity_id"] == "RD_TPE_001")
    assert any("替代路徑引導" in a for a in rd001["actions"])
