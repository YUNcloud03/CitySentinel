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
