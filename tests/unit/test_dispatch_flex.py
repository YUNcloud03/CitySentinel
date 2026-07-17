"""調度彈性測試：優先權抽調建議、preempt 執行、釋出回填。

情境資料：預設警力 12（A 組 8 + B 組 4）。
    EVT_003（Medium）先占 6（3 路口×2）＋ ACC_001（Critical）占 4 → 剩 2
    再來一起 Critical 需 4 → 缺 2 → 應提出自 Medium 事件抽調的建議。
"""
import pytest

from app.coordinator.coordinator import Coordinator, DataBundle
from app.resources import registry as reg


def _third_critical(coordinator):
    """第三起 Critical 事件：基隆路一段封閉（需警力 4）。"""
    return coordinator.process_incident({
        "event_id": "CUSTOM_FLEX_TEST",
        "type": "Traffic_Accident",
        "location": "基隆路一段",
        "affected_segment": "RD_TPE_003",
        "status": "Closed",
        "severity": "Critical",
        "description": "測試資源競爭",
        "timestamp": "2026-05-20 22:00",
    })


@pytest.fixture()
def contested():
    """製造資源競爭：Medium 占 6、Critical 占 4、第三起 Critical 缺 2。"""
    c = Coordinator(DataBundle())
    c.inject_incident("TPE_2026_EVT_003")   # Medium：6 警力 + 搶修
    c.inject_incident("TPE_2026_ACC_001")   # Critical：4 警力 + 號誌控制
    third = _third_critical(c)              # Critical：需 4，只剩 2 → 缺 2
    return c, third


def _police_action(state):
    return next(a for a in state["dispatch"]["actions"] if a["resource_type"] == reg.POLICE)


def test_shortfall_proposes_preemption_from_lower_priority(contested):
    c, third = contested
    act = _police_action(third)
    assert act["gap"] == 2
    cands = act["preemption_candidates"]
    assert len(cands) == 1  # 只有 Medium 可抽（另一起 Critical 同級不可）
    assert cands[0]["source_incident_id"] == "TPE_2026_EVT_003"
    assert cands[0]["source_severity"] == "Medium"
    assert cands[0]["suggested_count"] == 2
    assert "可抽調建議" in act["escalation"]


def test_preempt_executes_with_dual_audit(contested):
    c, third = contested
    act = _police_action(third)
    src_state = c.incident_states["TPE_2026_EVT_003"]
    src_act = _police_action(src_state)
    before_src = src_act["fulfilled_count"]  # 6

    c.preempt("CUSTOM_FLEX_TEST", act["action_id"],
              "TPE_2026_EVT_003", src_act["action_id"], 2,
              reason="Critical 事故優先", operator="cmdr_01")

    # 目標補滿、來源減少、庫存守恆
    assert act["gap"] == 0 and act["status"] == "proposed"
    assert src_act["fulfilled_count"] == before_src - 2
    assert src_state["dispatch"]["has_shortfall"] is True
    total = sum(r.total_count for r in c.bundle.registry.list() if r.resource_type == reg.POLICE)
    held = sum(a["fulfilled_count"] for st, a in
               ((s, x) for s in c.incident_states.values()
                for x in (s.get("dispatch") or {}).get("actions", []))
               if a["resource_type"] == reg.POLICE)
    free = sum(r.available_count for r in c.bundle.registry.list() if r.resource_type == reg.POLICE)
    assert held + free == total  # 12
    # 雙邊稽核
    assert any(t["step"] == "DISPATCH_PREEMPTED" for t in src_state["decision_trace"])
    ho = next(t for t in third["decision_trace"]
              if t["step"] == "HUMAN_OVERRIDE" and t["detail"].get("op") == "preempt")
    assert ho["detail"]["source_incident_id"] == "TPE_2026_EVT_003"


def test_preempt_refuses_equal_or_higher_priority(contested):
    c, third = contested
    act = _police_action(third)
    acc_state = c.incident_states["TPE_2026_ACC_001"]
    acc_act = _police_action(acc_state)
    with pytest.raises(ValueError, match="高優先抽調低優先"):
        c.preempt("CUSTOM_FLEX_TEST", act["action_id"],
                  "TPE_2026_ACC_001", acc_act["action_id"], 2)  # Critical ≤ Critical


def test_reject_triggers_backfill_by_priority(contested):
    """Medium 事件的警力被拒絕釋出 → 自動回填 Critical 缺口。"""
    c, third = contested
    act = _police_action(third)
    assert act["gap"] == 2
    src_act = _police_action(c.incident_states["TPE_2026_EVT_003"])

    c.dispatch_action("TPE_2026_EVT_003", src_act["action_id"], "reject",
                      reason="改用義交", operator="cmdr_01")

    assert act["gap"] == 0  # 釋出 6 → 回填 2
    assert act["status"] == "proposed"
    assert any(t["step"] == "RESOURCE_REBALANCED" for t in third["decision_trace"])
    assert third["dispatch"]["has_shortfall"] is False


def test_reinject_downgrade_releases_and_backfills():
    """事故重新研判降級後（Critical→High，警力需求 4→2），釋出資源自動回填他案缺口。"""
    c = Coordinator(DataBundle())
    base = {
        "event_id": "CUSTOM_A", "type": "Traffic_Accident",
        "location": "基隆路一段", "affected_segment": "RD_TPE_003",
        "status": "Closed", "severity": "Critical",
        "description": "測試", "timestamp": "2026-05-20 22:00",
    }
    c.process_incident(dict(base))          # Critical：4 警力
    c.inject_incident("TPE_2026_EVT_003")   # Medium：6 警力
    acc = c.inject_incident("TPE_2026_ACC_001")  # Critical：需 4，只剩 2 → 缺 2
    assert _police_action(acc)["gap"] == 2

    # CUSTOM_A 降級為 High（需求 4 → 2）：重新注入釋出 2 名
    c.process_incident({**base, "severity": "High"})

    assert _police_action(acc)["gap"] == 0  # 釋出量回填 Critical 缺口
    assert any(t["step"] == "RESOURCE_REBALANCED" for t in acc["decision_trace"])
