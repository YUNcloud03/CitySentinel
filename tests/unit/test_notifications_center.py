"""推播生命週期狀態機測試。"""
import pytest

from app.notifications_center import MockDeliveryAdapter, NotificationCenter


def _center():
    return NotificationCenter(MockDeliveryAdapter(fail_once={"SMS"}))


def _fake_state():
    return {
        "incident_id": "TEST_001",
        "notifications": {
            "cms": "測試 CMS",
            "messages": {"zh": "測試", "en": "test"},
            "multilingual_required": True,
        },
    }


def test_create_starts_ready_for_approval():
    center = _center()
    noti = center.create_from_incident(_fake_state())
    assert noti["status"] == "READY_FOR_APPROVAL"
    # 歷史含 DRAFTED → READY_FOR_APPROVAL
    assert [h["status"] for h in noti["history"]] == ["DRAFTED", "READY_FOR_APPROVAL"]


def test_cannot_dispatch_before_approval():
    """生成 ≠ 可發布：未核准不得 dispatch。"""
    center = _center()
    noti = center.create_from_incident(_fake_state())
    with pytest.raises(ValueError, match="不允許操作 dispatch"):
        center.dispatch(noti["notification_id"])


def test_full_lifecycle_with_retry():
    center = _center()
    nid = center.create_from_incident(_fake_state())["notification_id"]

    center.approve(nid, operator="cmdr_01")
    noti = center.dispatch(nid)
    # SMS 首次失敗 → 整體 DELIVERY_FAILED
    assert noti["status"] == "DELIVERY_FAILED"
    by_channel = {d["channel"]: d["status"] for d in noti["deliveries"]}
    assert by_channel["SMS"] == "DELIVERY_FAILED"
    assert by_channel["CMS"] == "DELIVERY_CONFIRMED"

    # 重試只補失敗通道 → 全部確認
    noti = center.retry(nid)
    assert noti["status"] == "DELIVERY_CONFIRMED"
    assert all(d["status"] == "DELIVERY_CONFIRMED" for d in noti["deliveries"])
    # 稽核軌跡完整
    statuses = [h["status"] for h in noti["history"]]
    assert statuses == [
        "DRAFTED", "READY_FOR_APPROVAL", "APPROVED", "DISPATCHING",
        "DELIVERY_FAILED", "RETRYING", "DELIVERY_CONFIRMED",
    ]


def test_cannot_retry_when_confirmed():
    center = NotificationCenter(MockDeliveryAdapter(fail_once=set()))
    nid = center.create_from_incident(_fake_state())["notification_id"]
    center.approve(nid)
    noti = center.dispatch(nid)
    assert noti["status"] == "DELIVERY_CONFIRMED"
    with pytest.raises(ValueError):
        center.retry(nid)


def test_approve_records_operator():
    center = _center()
    nid = center.create_from_incident(_fake_state())["notification_id"]
    noti = center.approve(nid, operator="traffic_commander_01")
    assert "traffic_commander_01" in noti["history"][-1]["note"]
