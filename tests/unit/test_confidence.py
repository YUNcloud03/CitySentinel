"""信心分數引擎測試。"""
from datetime import datetime

from app.data_loader import CrowdRecord, RoadSegment, TrafficRecord
from app.engines.confidence import assess_confidence

AT = datetime(2026, 5, 20, 22, 10)


def _seg():
    return RoadSegment("RD_TPE_002", "光復南路", "南北向", ("忠孝東路四段",), 1800,
                       (), ("BS_MRT_BL17",))


def _traffic(speed=2, sat=1.0, lane="Accident_Impact"):
    return TrafficRecord(AT, "RD_TPE_002", "光復南路", speed, 1600, sat, lane)


def _crowd(growth=0.5):
    return CrowdRecord(AT, "BS_MRT_BL17", "捷運國父紀念館站", 28000, 55, growth, 15.0)


def test_official_event_all_signals_high():
    result = assess_confidence(
        {"event_id": "TPE_2026_ACC_001", "affected_segment": "RD_TPE_002"},
        {"RD_TPE_002": _traffic()}, {"BS_MRT_BL17": _crowd()},
        {"RD_TPE_002": _seg()},
    )
    # 0.5 官方 + 0.2 車速崩跌 + 0.15 車道異常 + 0.1 周邊人流 = 0.95
    assert result["confidence_score"] == 0.95
    assert result["level"] == "高"
    assert len(result["evidence"]) == 4


def test_custom_event_lower_base():
    result = assess_confidence(
        {"event_id": "CUSTOM_SIMRUN-001", "affected_segment": "RD_TPE_002"},
        {"RD_TPE_002": _traffic(speed=40, sat=0.5, lane="Normal")}, {},
        {"RD_TPE_002": _seg()},
    )
    # 舊版自訂事件視為已由操作員注入：來源 0.3 + 人工確認 0.2。
    assert result["confidence_score"] == 0.5
    assert result["level"] == "中"
    assert result["execution_policy"]["code"] == "ACTION_PROPOSED"


def test_no_traffic_data_noted_in_evidence():
    result = assess_confidence(
        {"event_id": "TPE_2026_EVT_002", "affected_segment": "BS_MRT_BL17",
         "affected_road": "RD_TPE_001"},
        {}, {}, {},
    )
    assert any("無同時段車流資料" in e for e in result["evidence"])


def test_score_capped_below_one():
    result = assess_confidence(
        {"event_id": "TPE_2026_ACC_001", "affected_segment": "RD_TPE_002"},
        {"RD_TPE_002": _traffic()}, {"BS_MRT_BL17": _crowd()},
        {"RD_TPE_002": _seg()},
    )
    assert result["confidence_score"] <= 0.99


def test_coordinator_integration():
    """事件處理後 state 應含 confidence 與 CONFIDENCE_ASSESSED 步驟。"""
    from app.coordinator.coordinator import Coordinator, DataBundle

    c = Coordinator(DataBundle())
    state = c.inject_incident("TPE_2026_ACC_001")
    assert state["confidence"]["confidence_score"] >= 0.75
    assert state["confidence"]["level"] == "高"
    assert any(t["step"] == "CONFIDENCE_ASSESSED" for t in state["decision_trace"])
