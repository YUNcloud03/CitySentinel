"""Coordinator 一句話決策摘要測試。"""
from app.coordinator.coordinator import Coordinator, DataBundle, build_coordinator_summary


def test_acc_001_summary_shape():
    c = Coordinator(DataBundle())
    state = c.inject_incident("TPE_2026_ACC_001")
    s = state["coordinator_summary"]
    assert "光復南路" in s["verdict"]
    assert "高" in s["verdict"]  # 可信度高
    assert any("市民大道四段" in a for a in s["actions"])  # 主疏散
    assert any("警力" in a for a in s["actions"])
    assert "SOP 2" in s["basis"]
    assert "ETE 90" in s["basis"]
    assert s["escalation"]  # 升級條件非空


def test_summary_reports_shortfall_escalation():
    """資源缺口時，升級條件必須點明缺口需人工升級。"""
    c = Coordinator(DataBundle())
    c.inject_incident("TPE_2026_EVT_003")   # Medium 占警力
    c.inject_incident("TPE_2026_ACC_001")   # Critical 占警力
    third = c.process_incident({
        "event_id": "CUSTOM_X", "type": "Traffic_Accident", "location": "基隆路一段",
        "affected_segment": "RD_TPE_003", "status": "Closed", "severity": "Critical",
        "description": "測試", "timestamp": "2026-05-20 22:00",
    })
    assert "缺口" in third["coordinator_summary"]["escalation"]


def test_summary_is_deterministic_no_llm():
    """摘要完全確定性，不呼叫 LLM（測試環境 LLM 已停用）。"""
    state = {
        "event": {"type": "號誌故障", "location": "松高路"},
        "confidence": {"level": "中", "confidence_score": 0.6, "evidence": ["a", "b"]},
        "rule_attribution": {"caused_by_incident": [5]},
        "triggered_rules": [5],
        "dispatch": {"actions": [{"resource_type": "Police", "fulfilled_count": 6}], "has_shortfall": False},
    }
    s = build_coordinator_summary(state)
    assert "號誌故障" in s["verdict"] and "中" in s["verdict"]
    assert any("人工指揮" in a for a in s["actions"])
    assert "SOP 5" in s["basis"]
