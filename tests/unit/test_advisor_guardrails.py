"""LLM Advisory guardrail 測試（全部 mock，不呼叫真實 API）。"""
from app.llm import advisor
from app.llm.advisor import DecisionSummary


def _fake_state():
    return {
        "incident_id": "TPE_2026_ACC_001",
        "event": {"type": "Road_Collapse_Accident", "location": "光復南路",
                  "severity": "Critical", "status": "Closed", "description": "測試"},
        "triggered_rules": [2, 3, 4, 6],
        "rule_attribution": {
            "caused_by_incident": [2],
            "context_rules": [3, 4, 6],
            "calculation_rules": [7],
        },
        "trigger_details": [
            {"rule_id": 2, "entity_id": "RD_TPE_002", "evidence": {},
             "actions": ["啟動替代路徑規劃", "產出 CMS"]},
        ],
        "routing_result": {
            "primary_route": {"name": "市民大道四段", "capacity_vph": 2500, "saturation_score": 0.78},
            "secondary_routes": [], "excluded_routes": [],
        },
        "ete_result": {"formula": "ETE = 90", "ete_minutes_display": 90},
        "dispatch": {"actions": [], "has_shortfall": False},
    }


def test_fallback_when_llm_unavailable(monkeypatch):
    """LLM 不可用時走確定性模板，主流程不失敗。"""
    monkeypatch.setattr(advisor.llm_client, "structured_completion", lambda *a, **k: None)
    result = advisor.generate_decision_summary(_fake_state())
    assert result["llm_generated"] is False
    assert result["requires_human_approval"] is True
    assert "市民大道四段" in result["summary"]
    assert set(result["cited_rule_ids"]) == {2}


def test_guardrail_rejects_uncited_rules(monkeypatch):
    """LLM 引用未觸發的條款（幻覺）→ 整包棄用，改走模板。"""
    hallucinated = DecisionSummary(
        summary="假摘要", cited_rule_ids=[2, 5, 99],  # 5 與 99 未觸發
        recommended_actions=["假動作"], requires_human_approval=False,
    )
    monkeypatch.setattr(advisor.llm_client, "structured_completion", lambda *a, **k: hallucinated)
    result = advisor.generate_decision_summary(_fake_state())
    assert result["llm_generated"] is False
    assert "guardrail_rejected" in result
    assert "99" in result["guardrail_rejected"]


def test_valid_llm_output_forces_human_approval(monkeypatch):
    """即使 LLM 聲稱不需人工核准，也強制為 True。"""
    ok = DecisionSummary(
        summary="正常摘要", cited_rule_ids=[2, 7],
        recommended_actions=["改道市民大道四段"], requires_human_approval=False,
    )
    monkeypatch.setattr(advisor.llm_client, "structured_completion", lambda *a, **k: ok)
    result = advisor.generate_decision_summary(_fake_state())
    assert result["llm_generated"] is True
    assert result["requires_human_approval"] is True  # 強制覆寫


def test_whatif_llm_rejects_fabricated_ids(monkeypatch):
    """LLM 編造不存在的基地台 ID → 拒絕，回 None。"""
    from app.llm.advisor import WhatIfScenarioSchema

    fabricated = WhatIfScenarioSchema(
        at="2026-05-20 22:00",
        crowd_overrides={"BS_FAKE_STATION": {"user_count": 99999}},
    )
    monkeypatch.setattr(advisor.llm_client, "structured_completion", lambda *a, **k: fabricated)
    result = advisor.parse_what_if_with_llm(
        "隨便問", station_ids=["BS_MRT_BL17"], segment_ids=["RD_TPE_001"]
    )
    assert result is None


def test_whatif_llm_accepts_valid_ids(monkeypatch):
    from app.llm.advisor import WhatIfScenarioSchema

    valid = WhatIfScenarioSchema(
        at="2026-05-20 17:00",
        crowd_overrides={"BS_MRT_BL17": {"user_count": 40000}},
    )
    monkeypatch.setattr(advisor.llm_client, "structured_completion", lambda *a, **k: valid)
    result = advisor.parse_what_if_with_llm(
        "BL17 四萬人", station_ids=["BS_MRT_BL17"], segment_ids=["RD_TPE_001"]
    )
    assert result == {"at": "2026-05-20 17:00",
                      "crowd_overrides": {"BS_MRT_BL17": {"user_count": 40000}}}
