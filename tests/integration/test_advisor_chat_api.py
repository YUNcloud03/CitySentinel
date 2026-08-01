"""顧問對話 API 路由測試（LLM 層 mock，不打真 API）。"""
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main


@pytest.fixture()
def client(monkeypatch):
    # 阻斷真 LLM 呼叫：一般問答回 None → 走 help fallback
    monkeypatch.setattr(api_main.advisor, "answer_question", lambda *a, **k: None)
    monkeypatch.setattr(api_main.advisor, "parse_what_if_with_llm", lambda *a, **k: None)
    return TestClient(api_main.app)


def test_whatif_route(client):
    res = client.post("/api/advisor/chat", json={"question": "如果 17:00 BL17 人數增加到 40000 人會怎樣？"})
    body = res.json()
    assert body["kind"] == "whatif"
    assert body["parsed_by"] == "regex"
    assert 3 in body["whatif_result"]["diff"]["newly_triggered_rules"]
    assert "SOP 3" in body["answer"]


def test_sop_lookup_route(client):
    res = client.post("/api/advisor/chat", json={"question": "SOP 2 的內容是什麼？"})
    body = res.json()
    assert body["kind"] == "sop"
    assert body["cited_rule_ids"] == [2]
    assert "車禍" in body["answer"]


def test_fallback_help(client):
    res = client.post("/api/advisor/chat", json={"question": "今天天氣如何？"})
    body = res.json()
    assert body["kind"] == "help"


def test_provenance(client):
    body = client.get("/api/provenance").json()
    files = {f["file"]: f for f in body["data_sources"]}
    assert files["road_network_geometry.json"]["records"] == 15
    # provenance 必須回報它實際載入那份檔的雜湊，而不是寫死的字串。
    # 現行採用版為 741D2535…（2026-08-02 主辦方更新版，見 data/DATA_NOTES.md）。
    road_json = Path(__file__).resolve().parents[2] / "data" / "raw" / "road_network_geometry.json"
    expected = hashlib.sha256(road_json.read_bytes()).hexdigest()
    assert files["road_network_geometry.json"]["sha256"] == expected
    assert body["engine_constants"]["ETE"]["base_clearance"]["Critical"] == 60


def test_confidence_endpoint(client):
    client.post("/api/incidents/inject", json={"event_id": "TPE_2026_ACC_001"})
    body = client.get("/api/confidence").json()
    entry = next(e for e in body if e["incident_id"] == "TPE_2026_ACC_001")
    assert entry["confidence_score"] >= 0.75
    assert entry["level"] == "高"
    assert len(entry["evidence"]) >= 3
