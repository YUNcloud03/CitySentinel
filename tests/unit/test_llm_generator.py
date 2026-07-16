"""LLM 內容生成器 guardrail 測試（mock，不打真 API）。

驗證核心原則：LLM 生成文字、程式驗證數字——必含 token 缺一即退回模板。
"""
from datetime import datetime

from app.llm import generator
from app.llm.generator import CmsText, MultilingualAlert

AT = datetime(2026, 5, 20, 22, 10)
TS = "2026-05-20 22:10"
INCIDENT = {"type": "Road_Collapse_Accident", "location": "光復南路", "status": "Closed",
            "severity": "Critical", "description": "路面塌陷"}
FALLBACK_CMS = "光復南路封閉，請改道 市民大道四段，預計延誤 90 分鐘"
FALLBACK_MSGS = {"zh": "模板zh", "en": "模板en", "ja": "模板ja", "ko": "模板ko"}


def _patch(monkeypatch, ret):
    monkeypatch.setattr(generator.llm_client, "structured_completion", lambda *a, **k: ret)


# ---- CMS 導引文字 ----

def test_cms_llm_success_with_all_tokens(monkeypatch):
    _patch(monkeypatch, CmsText(cms="光復南路塌陷封閉，請提前改道市民大道四段，預計延誤 90 分鐘"))
    text, meta = generator.generate_cms_text("光復南路", "市民大道四段", 90, INCIDENT, [], FALLBACK_CMS)
    assert "市民大道四段" in text
    assert meta["source"].startswith("llm:")
    assert meta["guardrail_rejected"] is None


def test_cms_guardrail_rejects_missing_route(monkeypatch):
    """LLM 漏掉主疏散路名 → 整段棄用退回模板。"""
    _patch(monkeypatch, CmsText(cms="光復南路封閉，請改道其他道路，預計延誤 90 分鐘"))
    text, meta = generator.generate_cms_text("光復南路", "市民大道四段", 90, INCIDENT, [], FALLBACK_CMS)
    assert text == FALLBACK_CMS
    assert "市民大道四段" in meta["guardrail_rejected"]


def test_cms_guardrail_rejects_altered_ete(monkeypatch):
    """LLM 改寫 ETE 數字（90 → 約一個半小時）→ 退回模板。"""
    _patch(monkeypatch, CmsText(cms="光復南路封閉，請改道市民大道四段，預計延誤約一個半小時"))
    text, meta = generator.generate_cms_text("光復南路", "市民大道四段", 90, INCIDENT, [], FALLBACK_CMS)
    assert text == FALLBACK_CMS
    assert "90" in meta["guardrail_rejected"]


def test_cms_fallback_when_llm_unavailable(monkeypatch):
    _patch(monkeypatch, None)
    text, meta = generator.generate_cms_text("光復南路", "市民大道四段", 90, INCIDENT, [], FALLBACK_CMS)
    assert text == FALLBACK_CMS
    assert meta["source"] == "template"


# ---- 多語告警 ----

def _msgs(**overrides):
    base = {
        "zh": f"[{TS}] 光復南路封閉，請改道市民大道四段，延誤 90 分鐘。",
        "en": f"[{TS}] Guangfu S. Rd. closed. Detour via Civic Blvd. Sec. 4. Delay 90 min.",
        "ja": f"[{TS}] 光復南路は通行止め。迂回してください。遅延 90 分。",
        "ko": f"[{TS}] 도로 통제 중입니다. 우회하세요. 지연 90 분.",
    }
    return MultilingualAlert(**{**base, **overrides})


def test_multilingual_llm_success(monkeypatch):
    _patch(monkeypatch, _msgs())
    msgs, meta = generator.generate_multilingual(
        "光復南路", "Guangfu S. Rd.", "市民大道四段", "Civic Blvd. Sec. 4",
        90, AT, INCIDENT, FALLBACK_MSGS)
    assert meta["source"].startswith("llm:")
    assert all(TS in m for m in msgs.values())


def test_multilingual_rejects_missing_number_in_any_language(monkeypatch):
    """韓文版漏掉 90 → 四語整包退回模板（數字語言不變性）。"""
    _patch(monkeypatch, _msgs(ko=f"[{TS}] 도로 통제 중입니다. 우회하세요."))
    msgs, meta = generator.generate_multilingual(
        "光復南路", "Guangfu S. Rd.", "市民大道四段", "Civic Blvd. Sec. 4",
        90, AT, INCIDENT, FALLBACK_MSGS)
    assert msgs == FALLBACK_MSGS
    assert "ko" in meta["guardrail_rejected"]


def test_multilingual_rejects_missing_timestamp(monkeypatch):
    _patch(monkeypatch, _msgs(en="Guangfu S. Rd. closed. Delay 90 min."))
    msgs, meta = generator.generate_multilingual(
        "光復南路", "Guangfu S. Rd.", "市民大道四段", "Civic Blvd. Sec. 4",
        90, AT, INCIDENT, FALLBACK_MSGS)
    assert msgs == FALLBACK_MSGS


# ---- 預警摘要 ----

def test_alert_summary_fallback(monkeypatch):
    _patch(monkeypatch, None)
    result = generator.generate_alert_summary({
        "rule_id": 1, "entity_id": "RD_TPE_001", "sim_time": "2026-05-20 21:30",
        "evidence": {"saturation_score": 0.99}, "actions": ["通報交控中心", "綠燈+25%"],
    })
    assert result["source"] == "template"
    assert "RD_TPE_001" in result["summary"]
    assert "SOP 1" in result["summary"]


# ---- Coordinator 整合（LLM 停用時全模板、流程不中斷） ----

def test_coordinator_content_meta_present():
    from app.coordinator.coordinator import Coordinator, DataBundle

    c = Coordinator(DataBundle())
    state = c.inject_incident("TPE_2026_ACC_001")
    noti = state["notifications"]
    assert noti["cms_meta"]["source"] == "template"  # 測試環境 LLM 停用
    assert noti["messages_meta"]["source"] == "template"
    assert "光復南路" in noti["cms"] and "90" in noti["cms"]
    # 決策鏈記錄生成來源
    content_step = next(t for t in state["decision_trace"] if t["step"] == "CONTENT_GENERATED")
    assert content_step["detail"]["cms_source"] == "template"
