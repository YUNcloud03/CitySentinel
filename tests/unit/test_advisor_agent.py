"""Advisory Agent 測試：工具執行（真資料）+ 迴圈控制（mock LLM step）。"""
import pytest

from app.coordinator.coordinator import Coordinator, DataBundle
from app.llm.agent import MAX_ITERS, AdvisorAgent


@pytest.fixture(scope="module")
def agent():
    bundle = DataBundle()
    return AdvisorAgent(bundle, Coordinator(bundle), player=None)


# ---- 工具執行（唯讀 / sandbox） ----

def test_get_sop_single_and_all(agent):
    one = agent._execute_tool("get_sop", {"rule_id": 2})
    assert one["title"] == "車禍與路障應變"
    assert "capacity_vph" in one["text"]
    all_rules = agent._execute_tool("get_sop", {})
    assert len(all_rules["rules"]) == 7


def test_run_what_if_tool_is_sandboxed(agent):
    result = agent._execute_tool("run_what_if", {
        "at": "2026-05-20 17:00",
        "crowd_overrides": {"BS_MRT_BL17": {"user_count": 40000}},
    })
    assert result["newly_triggered"] == [3]
    assert result["production_state_modified"] is False


def test_run_what_if_with_simulated_incident(agent):
    result = agent._execute_tool("run_what_if", {
        "at": "2026-05-20 22:00",
        "simulated_incident": {"affected_segment": "RD_TPE_002",
                               "status": "Closed", "severity": "Critical",
                               "location": "光復南路與忠孝東路口南側"},
    })
    assert 2 in result["incident_rules"]
    assert result["simulated_primary_route"] == "市民大道四段"
    assert result["simulated_ete_minutes"] == 90


def test_unknown_tool_rejected(agent):
    """允許清單外的工具（如發布）不存在——物理性安全邊界。"""
    result = agent._execute_tool("dispatch_notification", {"id": "x"})
    assert "允許清單外" in result["error"]
    result2 = agent._execute_tool("approve_dispatch", {})
    assert "error" in result2


def test_tool_error_fed_back_not_raised(agent):
    result = agent._execute_tool("run_what_if", {"at": "亂寫的時間"})
    assert "error" in result  # 錯誤回饋給 agent 自行調整，不炸主流程


def test_get_traffic_and_crowd(agent):
    t = agent._execute_tool("get_traffic", {"at": "2026-05-20 21:30"})
    top = t["segments"][0]
    assert top["level"] == "A"
    c = agent._execute_tool("get_crowd", {"at": "2026-05-20 22:30"})
    assert c["stations"][0]["users"] == 33000


# ---- 迴圈控制與引用推導（mock LLM step） ----

def _make_scripted_agent(agent, script):
    """script: 每次 _llm_step 依序回傳的 (kind, payload)。"""
    it = iter(script)
    agent_copy = AdvisorAgent(agent.bundle, agent.coordinator, None)
    agent_copy._llm_step = lambda messages: next(it)
    return agent_copy


def test_agent_loop_tool_then_final(agent, monkeypatch):
    monkeypatch.delenv("CITY_LLM_DISABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")  # 讓 get_provider 回報可用
    from app.llm import client as llm_client
    llm_client.reset_provider_cache()
    try:
        scripted = _make_scripted_agent(agent, [
            ("tools", [("c1", "get_sop", {"rule_id": 3})]),
            ("final", "依 SOP 3，BL17 超過門檻時啟動過站不停與接駁。"),
        ])
        result = scripted.run("BL17 爆量怎麼辦？")
        assert result["available"] is True
        assert result["tool_trace"][0]["tool"] == "get_sop"
        assert result["cited_rule_ids"] == [3]  # 軌跡 + 文字交叉推導
    finally:
        llm_client.reset_provider_cache()


def test_agent_max_iterations_enforced(agent, monkeypatch):
    monkeypatch.delenv("CITY_LLM_DISABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    from app.llm import client as llm_client
    llm_client.reset_provider_cache()
    try:
        scripted = _make_scripted_agent(
            agent, [("tools", [(f"c{i}", "get_resources", {})]) for i in range(MAX_ITERS + 2)])
        result = scripted.run("一直查資源")
        assert len(result["tool_trace"]) == MAX_ITERS  # 硬上限
        assert "上限" in result["answer"]
    finally:
        llm_client.reset_provider_cache()


def test_agent_unavailable_when_llm_disabled(agent):
    result = agent.run("任何問題")  # conftest 已設 CITY_LLM_DISABLED
    assert result == {"available": False}
