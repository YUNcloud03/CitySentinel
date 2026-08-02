"""交控中心建議書 API 測試：確認官方要求的五項內容齊全且可回溯。"""
import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main


@pytest.fixture()
def client():
    return TestClient(api_main.app)


@pytest.fixture()
def rec(client):
    """注入車禍事件（會走完整路徑規劃與資源調度）後取得建議書。"""
    state = client.post("/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"}).json()
    res = client.get(f"/api/incidents/{state['incident_id']}/recommendation")
    assert res.status_code == 200
    return res.json()


def test_unprocessed_incident_returns_404(client):
    assert client.get("/api/incidents/NO_SUCH_EVENT/recommendation").status_code == 404


def test_section_1_identification(rec):
    """事件辨識：event_id 與對應 SOP 條款編號。"""
    ident = rec["identification"]
    assert ident["event_id"] == "TPE_2026_ACC_001"
    assert 2 in ident["triggered_rules"]  # 車禍與路障應變
    assert any("SOP 第 2 條" in label for label in ident["triggered_rule_labels"])
    # 事件造成 vs 環境既有須分開，處置責任不同
    assert 2 in ident["caused_by_incident"]


def test_section_2_grading_cites_saturation(rec):
    """交通分級判定：須引用飽和度數值與門檻，而非只給等級。"""
    grading = rec["grading"]
    assert grading["graded_segments"], "分級區塊不得為空"
    seg = grading["graded_segments"][0]
    assert seg["congestion_level"] in ("A", "B")
    assert isinstance(seg["saturation_score"], (int, float))
    assert str(seg["saturation_score"]) in seg["basis"]  # 判定依據引用實際數值
    assert seg.get("name"), "須補上路段名稱供閱讀"
    assert grading["thresholds"]["level_a"] == 0.95
    assert grading["ete_minutes"] and grading["ete_formula"]


def test_section_3_routing_includes_exclusion_reasons(rec):
    """替代路徑建議：主疏散、次要替代，及排除其他候選之理由。"""
    routing = rec["routing"]
    assert routing["primary_route"]["name"]
    assert routing["excluded_routes"], "排除理由為官方明確要求，不得為空"
    for ex in routing["excluded_routes"]:
        assert ex["reason_code"]
        assert ex["detail"]


def test_section_4_signal_plan_has_timing_and_period(rec):
    """號誌調整建議：須有具體配時與適用時段。"""
    plan = rec["signal_plan"]
    assert plan["items"], "號誌調整區塊不得為空"
    # 具體配時（如 +25%）來自 dispatch，須被納入而非只有規則泛稱
    assert any("+25%" in (i.get("detail") or "") or "+25%" in i["action"]
               for i in plan["items"])
    assert plan["effective_from"] and plan["duration_minutes"]


def test_section_5_interagency_requests(rec):
    """跨系統聯動：觸發第 3 條時須列出對北捷、公車處、警力之請求。"""
    inter = rec["interagency"]
    assert inter["required"] is True  # 本事件觸發 SOP 3
    agencies = {r["agency"] for r in inter["requests"]}
    assert "臺北捷運公司" in agencies
    assert "公共運輸處" in agencies
    assert "警察局交通警察大隊" in agencies
    # 警力請求須帶實際核配數量，供指揮官判斷缺口
    police = [r for r in inter["requests"] if r.get("requested_count") is not None]
    assert police and police[0]["fulfilled_count"] is not None
    assert inter["external_system_connected"] is False
    assert "模擬" in inter["execution_disclaimer"]
    assert any(r.get("status_code") == "READY_FOR_APPROVAL" for r in inter["requests"])


def test_interagency_status_follows_commander_approval(client):
    state = client.post("/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"}).json()
    action = state["dispatch"]["actions"][0]
    approved = client.post(
        f"/api/incidents/{state['incident_id']}/dispatch/{action['action_id']}",
        json={"op": "accept", "operator": "test_commander", "simulation_time": state["as_of"]},
    )
    assert approved.status_code == 200
    rec = client.get(f"/api/incidents/{state['incident_id']}/recommendation").json()
    linked = next(row for row in rec["interagency"]["requests"] if row.get("action_id") == action["action_id"])
    assert linked["status_code"] == "AUTHORIZED_FOR_SIMULATION"


def test_recommendation_reflects_assumptions(client):
    """漫遊率假設值須隨建議書揭露，避免與實際資料混淆。"""
    state = client.post("/api/incidents/custom", json={
        "type": "Road_Collapse", "affected_segment": "RD_TPE_003",
        "status": "Closed", "severity": "High", "location": "x", "description": "x",
        "timestamp": "2026-05-20 22:30", "roaming_override_pct": 8,
    }).json()
    rec = client.get(f"/api/incidents/{state['incident_id']}/recommendation").json()
    assert rec["assumptions"]
    assert rec["assumptions"][0]["field"] == "roaming_user_pct"


def test_recommendation_does_not_invent_values(rec):
    """建議書只重組既有結果——ETE 須與事件處理結果一致。"""
    assert rec["grading"]["ete_minutes"] == 90  # 與 ete_result 相同
    assert rec["generated_from"]["workflow_status"] == "completed"
