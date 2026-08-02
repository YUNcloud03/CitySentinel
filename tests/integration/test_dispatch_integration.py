"""調度整合測試：三個官方事件的調度與人工覆寫。"""
import pytest

from app.coordinator.coordinator import Coordinator, DataBundle
from app.resources import registry as reg


@pytest.fixture()
def coordinator():
    # 每個測試獨立 registry，避免庫存互相影響
    return Coordinator(DataBundle())


def test_acc_001_dispatches_police_and_signal(coordinator):
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    dispatch = state["dispatch"]
    assert dispatch is not None
    types = {a["resource_type"] for a in dispatch["actions"]}
    assert reg.POLICE in types
    assert reg.SIGNAL_CONTROL in types
    police = next(a for a in dispatch["actions"] if a["resource_type"] == reg.POLICE)
    assert police["requested_count"] == 4  # Critical
    # 每個動作都有證據包
    assert police["challenge_question"]
    assert police["deterministic_result"]
    assert police["input_snapshot_id"].startswith("SNAP-")
    assert police["allocation_state"] == "reserved"


def test_accept_commits_reserved_resource_and_records_simulation_time(coordinator):
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    action = state["dispatch"]["actions"][0]
    coordinator.dispatch_action(
        state["incident_id"], action["action_id"], "accept",
        operator="cmdr_01", simulation_time="2026-05-20 22:10",
    )
    assert action["status"] == "accepted"
    assert action["allocation_state"] == "committed"
    assert action["accepted_sim_time"] == "2026-05-20 22:10"


def test_acc_001_does_not_dispatch_mrt(coordinator):
    """光復南路塌陷不應調度捷運資源（規則歸因：SOP3 只是環境參考）。"""
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    types = {a["resource_type"] for a in state["dispatch"]["actions"]}
    assert reg.MRT_LIAISON not in types
    # 規則歸因欄位：SOP 3/4/6 屬 context 而非事件造成
    attr = state["rule_attribution"]
    assert 2 in attr["caused_by_incident"]
    assert set(attr["context_rules"]) & {3, 4, 6}


def test_evt_002_dispatches_mrt_shuttle_police(coordinator):
    """BL17 人群推擠：事件本身就是 BL17，SOP3 屬事件造成，應調度捷運分流資源。"""
    state = coordinator.inject_incident("TPE_2026_EVT_002")
    types = {a["resource_type"] for a in state["dispatch"]["actions"]}
    assert reg.MRT_LIAISON in types
    assert reg.SHUTTLE in types
    assert 3 in state["rule_attribution"]["caused_by_incident"]


def test_evt_003_signal_failure_six_police(coordinator):
    """松高路號誌故障：3 個路口 × 2 = 6 名警力 + 搶修。"""
    state = coordinator.inject_incident("TPE_2026_EVT_003")
    police = next(a for a in state["dispatch"]["actions"] if a["resource_type"] == reg.POLICE)
    assert police["requested_count"] == 6
    assert any(a["resource_type"] == reg.SIGNAL_MAINT for a in state["dispatch"]["actions"])


def test_reinject_releases_prior_allocation(coordinator):
    """重新注入同一事件不應把庫存重複扣光。"""
    coordinator.inject_incident("TPE_2026_ACC_001")
    after_first = sum(r.available_count for r in coordinator.bundle.registry.list())
    coordinator.inject_incident("TPE_2026_ACC_001")
    after_second = sum(r.available_count for r in coordinator.bundle.registry.list())
    assert after_first == after_second


def test_reject_returns_resources_and_audits(coordinator):
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    action = state["dispatch"]["actions"][0]
    before = sum(r.available_count for r in coordinator.bundle.registry.list())
    coordinator.dispatch_action(
        "TPE_2026_ACC_001", action["action_id"], "reject",
        reason="現場已有警力", operator="cmdr_01",
    )
    after = sum(r.available_count for r in coordinator.bundle.registry.list())
    assert after > before  # 資源已歸還
    updated = next(a for a in state["dispatch"]["actions"] if a["action_id"] == action["action_id"])
    assert updated["status"] == "rejected"
    assert updated["override"]["override_by"] == "cmdr_01"
    # 稽核寫入決策鏈
    assert any(t["step"] == "HUMAN_OVERRIDE" for t in state["decision_trace"])


def test_adjust_keeps_original_recommendation(coordinator):
    state = coordinator.inject_incident("TPE_2026_ACC_001")
    action = next(a for a in state["dispatch"]["actions"] if a["resource_type"] == reg.POLICE)
    coordinator.dispatch_action(
        "TPE_2026_ACC_001", action["action_id"], "adjust", count=2,
        reason="現場已有 2 名警員", operator="cmdr_01",
    )
    updated = next(a for a in state["dispatch"]["actions"] if a["action_id"] == action["action_id"])
    assert updated["requested_count"] == 2
    assert updated["agent_recommended_count"] == 4  # 保留原始 Agent 建議
    assert updated["status"] == "adjusted"
