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


def test_citizen_not_reached_while_sms_failed():
    """SMS 是唯一的民眾通道：它失敗時民眾端不得顯示警報——即使 CMS 成功。"""
    center = _center()
    nid = center.create_from_incident(_fake_state())["notification_id"]
    center.approve(nid)
    noti = center.dispatch(nid)

    assert noti["citizen_reached"] == []
    by_channel = {d["channel"]: d["status"] for d in noti["deliveries"]}
    assert by_channel["CMS"] == "DELIVERY_CONFIRMED"  # CMS 成功不代表民眾收到
    assert "民眾端未收到警報" in noti["history"][-1]["note"]

    # 重試成功後民眾才收得到
    noti = center.retry(nid)
    assert noti["citizen_reached"] == ["SMS"]


def test_draft_has_empty_citizen_reached():
    """未發送的草稿不得讓民眾端顯示警報。"""
    center = _center()
    noti = center.create_from_incident(_fake_state())
    assert noti["citizen_reached"] == []


def test_cms_alone_never_reaches_citizens():
    """CMS 是路側看板，不屬民眾手機通道。"""
    center = NotificationCenter(MockDeliveryAdapter(fail_once=set()))
    nid = center.create_from_incident(_fake_state())["notification_id"]
    center.approve(nid)
    noti = center.dispatch(nid)
    assert "CMS" not in noti["citizen_reached"]


def test_cannot_retry_when_confirmed():
    center = NotificationCenter(MockDeliveryAdapter(fail_once=set()))
    nid = center.create_from_incident(_fake_state())["notification_id"]
    center.approve(nid)
    noti = center.dispatch(nid)
    assert noti["status"] == "DELIVERY_CONFIRMED"
    with pytest.raises(ValueError):
        center.retry(nid)


def test_reinject_updates_draft_instead_of_duplicating():
    """重複注入同一事件不得產生第二則待核准通報（民眾會收到兩則相同推播）。"""
    center = _center()
    first = center.create_from_incident(_fake_state())

    updated = dict(_fake_state())
    updated["notifications"] = {**updated["notifications"], "cms": "更新後的 CMS"}
    second = center.create_from_incident(updated)

    assert second["notification_id"] == first["notification_id"]
    assert len(center.list()) == 1
    assert second["cms"] == "更新後的 CMS"          # 內容就地更新
    assert second["history"][-1]["note"] == "事件重新注入，草稿內容已更新"


def test_reinject_after_dispatch_creates_new_notification():
    """已發送的通報不可被覆寫——另建一則以保留稽核軌跡。"""
    center = _center()
    first = center.create_from_incident(_fake_state())
    center.approve(first["notification_id"])
    center.dispatch(first["notification_id"])

    second = center.create_from_incident(_fake_state())
    assert second["notification_id"] != first["notification_id"]
    assert len(center.list()) == 2


def test_reinject_different_incidents_are_separate():
    """不同事件各自獨立，不會互相覆寫。"""
    center = _center()
    a = center.create_from_incident(_fake_state())
    other = dict(_fake_state())
    other["incident_id"] = "TEST_002"
    b = center.create_from_incident(other)

    assert a["notification_id"] != b["notification_id"]
    assert len(center.list()) == 2


def test_approve_records_operator():
    center = _center()
    nid = center.create_from_incident(_fake_state())["notification_id"]
    noti = center.approve(nid, operator="traffic_commander_01")
    assert "traffic_commander_01" in noti["history"][-1]["note"]
