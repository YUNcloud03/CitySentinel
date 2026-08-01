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

ASSIST = "緊急請撥 110 或 119。"  # 四語皆須含 110 與 119


def _msgs(**overrides):
    base = {
        "zh": f"[{TS}] 光復南路因塌陷封閉，請改道市民大道四段，延誤 90 分鐘。{ASSIST}",
        "en": f"[{TS}] Guangfu S. Rd. closed. Detour via Civic Blvd. Sec. 4. "
              f"Delay 90 min. Call 110 or 119.",
        "ja": f"[{TS}] 光復南路は通行止め。迂回してください。遅延 90 分。110 か 119 へ。",
        "ko": f"[{TS}] 도로 통제 중입니다. 우회하세요. 지연 90 분. 110 또는 119.",
    }
    return MultilingualAlert(**{**base, **overrides})


def _gen(msgs_obj, monkeypatch):
    _patch(monkeypatch, msgs_obj)
    return generator.generate_multilingual(
        "光復南路", "Guangfu S. Rd.", "市民大道四段", "Civic Blvd. Sec. 4",
        90, AT, INCIDENT, FALLBACK_MSGS)


def test_multilingual_llm_success(monkeypatch):
    msgs, meta = _gen(_msgs(), monkeypatch)
    assert meta["source"].startswith("llm:")
    assert all(TS in m for m in msgs.values())


def test_multilingual_rejects_missing_number_in_any_language(monkeypatch):
    """韓文版漏掉 90 → 四語整包退回模板（數字語言不變性）。

    刻意保留求援號碼，確保退回原因是 ETE 90 而非 110/119。
    """
    _, meta = _gen(
        _msgs(ko=f"[{TS}] 도로 통제 중입니다. 우회하세요. 110 또는 119."), monkeypatch)
    assert "ko" in meta["guardrail_rejected"]
    assert "90" in meta["guardrail_rejected"]


def test_multilingual_rejects_missing_timestamp(monkeypatch):
    msgs, _ = _gen(
        _msgs(en="Guangfu S. Rd. closed. Delay 90 min. Call 110 or 119."), monkeypatch)
    assert msgs == FALLBACK_MSGS


def test_multilingual_rejects_missing_assistance_numbers(monkeypatch):
    """求援提醒是官方四要素之一：任一語言缺 110/119 → 整包退回模板。"""
    msgs, meta = _gen(
        _msgs(ja=f"[{TS}] 光復南路は通行止め。迂回してください。遅延 90 分。"), monkeypatch)
    assert msgs == FALLBACK_MSGS
    assert "ja" in meta["guardrail_rejected"]


def test_multilingual_rejects_internal_jargon(monkeypatch):
    """民眾訊息不得出現內部代號（可讀性要求）。

    必含路名仍保留，確保退回原因是術語而非缺 token。
    """
    msgs, meta = _gen(
        _msgs(zh=f"[{TS}] 光復南路（RD_TPE_002）因塌陷封閉，請改道市民大道四段，"
                 f"延誤 90 分鐘。{ASSIST}"), monkeypatch)
    assert msgs == FALLBACK_MSGS
    assert "RD_" in meta["guardrail_rejected"]


def test_multilingual_rejects_overlong_message(monkeypatch):
    """超過簡訊長度上限 → 退回模板（適合手機簡訊呈現）。"""
    padding = "另外請注意周邊道路壅塞情形並提前規劃替代路線避免耽誤行程" * 6
    msgs, meta = _gen(
        _msgs(zh=f"[{TS}] 光復南路因塌陷封閉，請改道市民大道四段，"
                 f"延誤 90 分鐘。{ASSIST}{padding}"), monkeypatch)
    assert msgs == FALLBACK_MSGS
    assert "超過簡訊上限" in meta["guardrail_rejected"]


def test_template_within_sms_limits():
    """保底模板本身必須符合長度上限——否則系統執行不了自己訂的規則。

    掃過所有事故類型 × 有無改道 × 有無 ETE × SOP 組合的最壞情況。
    """
    from app import notifications as n

    long_road = max(n.ROAD_NAME_EN, key=lambda k: len(n.ROAD_NAME_EN[k]))
    for cause_type in list(n.CAUSE_TEXT) + ["Unknown_Type"]:
        for primary in (None, "市民大道四段"):
            for ete in (0, 120):
                for rules in ({2}, {5}, {2, 5}, set()):
                    msgs = n.multilingual_reroute(
                        "基隆路高架橋下車道", n.ROAD_NAME_EN[long_road],
                        primary, "Civic Blvd. Sec. 4" if primary else None,
                        ete, AT, incident_type=cause_type, rules=rules)
                    for lang, text in msgs.items():
                        limit = generator.SMS_MAX_CHARS[lang]
                        assert len(text) <= limit, (
                            f"{lang} 模板 {len(text)} 字超過上限 {limit}：{text}")


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
