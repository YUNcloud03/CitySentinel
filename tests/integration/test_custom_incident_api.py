"""自訂事件模擬器 + 通報 API 整合測試（TestClient）。"""
import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main


@pytest.fixture()
def client():
    return TestClient(api_main.app)


def test_custom_incident_unknown_segment_rejected(client):
    res = client.post("/api/incidents/custom", json={
        "type": "Road_Collapse", "affected_segment": "RD_TPE_999",
        "status": "Closed", "severity": "Critical",
        "timestamp": "2026-05-20 22:00",
    })
    assert res.status_code == 422
    assert "不存在" in res.json()["detail"]


def test_custom_incident_bad_timestamp_rejected(client):
    res = client.post("/api/incidents/custom", json={
        "type": "Road_Collapse", "affected_segment": "RD_TPE_003",
        "status": "Closed", "severity": "Critical",
        "timestamp": "2026-99-99 99:99",
    })
    assert res.status_code == 422  # pydantic pattern 驗證


def test_custom_incident_bad_enum_rejected(client):
    res = client.post("/api/incidents/custom", json={
        "type": "Road_Collapse", "affected_segment": "RD_TPE_003",
        "status": "Exploded", "severity": "Critical",
        "timestamp": "2026-05-20 22:00",
    })
    assert res.status_code == 422


def test_custom_incident_full_flow(client):
    """合法自訂事件：基隆路一段封閉 → 走完整 Coordinator 流程並建立 run 紀錄。"""
    res = client.post("/api/incidents/custom", json={
        "type": "Road_Collapse", "affected_segment": "RD_TPE_003",
        "status": "Closed", "severity": "High",
        "location": "基隆路一段", "description": "自訂模擬事件",
        "timestamp": "2026-05-20 22:00",
    })
    assert res.status_code == 200
    state = res.json()
    assert state["workflow_status"] == "completed"
    assert 2 in state["triggered_rules"]
    assert state["simulation_run_id"].startswith("SIMRUN-")
    # 事件會產生待核准的通報
    assert state["notification_id"].startswith("NOTI-")

    runs = client.get("/api/simulation-runs").json()
    assert any(r["simulation_run_id"] == state["simulation_run_id"] for r in runs)


def test_notification_lifecycle_via_api(client):
    """注入官方事件 → 通報待核准 → 核准 → 發布 → 重試 → 全通道確認。"""
    state = client.post("/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"}).json()
    nid = state["notification_id"]

    # 未核准直接發布 → 409
    res = client.post(f"/api/notifications/{nid}/dispatch")
    assert res.status_code == 409

    assert client.post(f"/api/notifications/{nid}/approve").json()["status"] == "APPROVED"
    noti = client.post(f"/api/notifications/{nid}/dispatch").json()
    assert noti["status"] == "DELIVERY_FAILED"  # mock：SMS 首次失敗
    noti = client.post(f"/api/notifications/{nid}/retry").json()
    assert noti["status"] == "DELIVERY_CONFIRMED"


# ---- 漫遊率假設值（Demo 用，官方資料 20:00 後恆 >= 30%）----

def _custom(client, **extra):
    payload = {
        "type": "Road_Collapse", "affected_segment": "RD_TPE_003",
        "status": "Closed", "severity": "High",
        "timestamp": "2026-05-20 22:30",  # 實際漫遊率 45%
        **extra,
    }
    return client.post("/api/incidents/custom", json=payload)


def test_roaming_override_absent_uses_real_data(client):
    """不帶覆寫時行為與原本完全相同——22:30 實際 45% 觸發，且不標假設值。"""
    state = _custom(client).json()
    assert state.get("assumptions") is None
    noti = client.get("/api/notifications").json()[-1]
    d = noti["multilingual_decision"]
    assert d["triggered"] is True
    assert d["assumed"] is False
    assert d["max_roaming_pct"] == 45.0
    assert noti["languages"] == ["zh", "en", "ja", "ko"]


def test_roaming_override_below_threshold_is_chinese_only(client):
    """覆寫為門檻以下 → SOP 6 未觸發，僅中文，且判定說明沿用假設值而非實際值。"""
    state = _custom(client, roaming_override_pct=8).json()
    noti = client.get("/api/notifications").json()[-1]
    d = noti["multilingual_decision"]
    assert d["triggered"] is False
    assert d["max_roaming_pct"] == 8.0      # 非實際的 45
    assert d["actual_max_pct"] == 45.0      # 實際值仍可查
    assert noti["languages"] == ["zh"]
    assert "模擬假設值" in d["reason"]
    # 事件標示假設值，供稽核區分
    assumption = state["assumptions"][0]
    assert assumption["field"] == "roaming_user_pct"
    assert assumption["applied_pct"] == 8.0


def test_roaming_override_at_threshold_triggers(client):
    """門檻含等號：正好 30% 應觸發。"""
    _custom(client, roaming_override_pct=30)
    d = client.get("/api/notifications").json()[-1]["multilingual_decision"]
    assert d["triggered"] is True
    assert d["assumed"] is True


def test_roaming_override_does_not_mutate_source_data(client):
    """覆寫只作用於快照副本——之後不帶覆寫注入，仍讀到實際資料。"""
    _custom(client, roaming_override_pct=8)
    after = _custom(client).json()
    assert after.get("assumptions") is None
    d = client.get("/api/notifications").json()[-1]["multilingual_decision"]
    assert d["max_roaming_pct"] == 45.0  # 未被前一次覆寫污染
    assert d["triggered"] is True


def test_roaming_override_out_of_range_rejected(client):
    assert _custom(client, roaming_override_pct=101).status_code == 422
    assert _custom(client, roaming_override_pct=-1).status_code == 422
