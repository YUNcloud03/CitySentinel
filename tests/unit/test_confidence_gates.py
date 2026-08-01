from app.coordinator.coordinator import Coordinator, DataBundle


def _incident(event_id: str, source_type: str, human_confirmed: bool = False):
    return {
        "event_id": event_id,
        "type": "Citizen_Report",
        "affected_segment": "RD_TPE_002",
        "status": "Closed",
        "severity": "Low",
        "location": "test",
        "description": "confidence gate test",
        "timestamp": "2026-05-20 17:00",
        "source_type": source_type,
        "source_id": f"{source_type}-test",
        "human_confirmed": human_confirmed,
    }


def test_low_confidence_event_does_not_reserve_resources_or_enable_notification():
    coordinator = Coordinator(DataBundle())
    before = [resource.available_count for resource in coordinator.bundle.registry.list()]
    state = coordinator.process_incident(_incident("CITIZEN-LOW", "citizen"))
    after = [resource.available_count for resource in coordinator.bundle.registry.list()]

    assert state["confidence"]["execution_policy"]["code"] == "MONITOR_ONLY"
    assert state["dispatch"] is None
    assert before == after
    notification = coordinator.bundle.notification_center.get(state["notification_id"])
    assert notification["status"] == "MONITOR_ONLY"
    assert notification["channels"] == ["Dashboard"]


def test_medium_confidence_requires_confirmation_without_resource_reservation():
    coordinator = Coordinator(DataBundle())
    state = coordinator.process_incident(_incident("CAMERA-MEDIUM", "camera", human_confirmed=True))
    assert state["confidence"]["confidence_score"] == 0.5
    assert state["confidence"]["execution_policy"]["code"] == "HUMAN_CONFIRMATION_REQUIRED"
    assert state["dispatch"] is None
    notification = coordinator.bundle.notification_center.get(state["notification_id"])
    assert notification["status"] == "PENDING_CONFIRMATION"


def test_high_confidence_organizer_event_keeps_human_approval_gate():
    coordinator = Coordinator(DataBundle())
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    assert state["confidence"]["execution_policy"]["code"] == "ACTION_PROPOSED"
    assert state["dispatch"] is not None
    notification = coordinator.bundle.notification_center.get(state["notification_id"])
    assert notification["status"] == "READY_FOR_APPROVAL"
