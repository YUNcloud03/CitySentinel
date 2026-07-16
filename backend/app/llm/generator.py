"""LLM 內容生成器：預警摘要、CMS 導引文字、多語告警（官方要求三處由 LLM 生成）。

核心原則：**LLM 生成文字，程式驗證數字。**
每次生成都附「必含 token 清單」（路名、ETE 數字、時間戳）——這些由確定性
引擎算出、不可竄改；LLM 輸出缺任何一個 token 即整段棄用、退回模板。
LLM 不可用或被 guardrail 攔下時一律走確定性模板，主流程永不中斷。

回傳格式統一：(text 或 dict, meta)
    meta = {"source": "llm:openai" | "template", "guardrail_rejected": str | None}
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .. import notifications
from ..data_loader import format_ts
from . import client as llm_client
from .advisor import RULE_NAMES


def _provider_tag() -> str:
    provider, _ = llm_client.get_provider()
    return f"llm:{provider}"


def _missing_tokens(text: str, required: list[str]) -> list[str]:
    return [t for t in required if t and t not in text]


# ---- 1. 預警摘要（監測門檻觸發彈窗，官方：摘要由 LLM 生成） ----

class AlertSummary(BaseModel):
    summary: str = Field(description="2-3 句情勢分析摘要，繁體中文，80 字內")


_ALERT_SYSTEM = """你是交控中心的 AI 監測分析員。根據「程式已判定觸發」的 SOP 預警，
為指揮官撰寫簡短情勢摘要（2-3 句、80 字內）。嚴格遵守：
1. 門檻判定已由程式完成，你只解釋情勢，不得重新判定或質疑門檻。
2. 所有數值必須與提供的證據完全一致，不可改寫、換算或省略關鍵數字。
3. 說明「發生什麼、為何觸發、建議關注什麼」。禁止編造資料中沒有的資訊。"""


def generate_alert_summary(alert: dict) -> dict:
    """預警彈窗摘要。alert 含 rule_id/entity_id/evidence/actions/sim_time。"""
    rule_id = alert.get("rule_id")
    rule_name = RULE_NAMES.get(rule_id, "")
    fallback = (
        f"{alert.get('entity_id')} 於 {alert.get('sim_time', '')} 觸發 SOP {rule_id}"
        f"（{rule_name}），已達處置門檻。建議處置：{'；'.join(alert.get('actions', [])[:2])}。"
    )
    result = llm_client.structured_completion(
        _ALERT_SYSTEM,
        f"觸發條款：SOP {rule_id}（{rule_name}）\n"
        f"觸發實體:{alert.get('entity_id')}\n"
        f"模擬時間：{alert.get('sim_time')}\n"
        f"證據數值：{alert.get('evidence')}\n"
        f"SOP 規定動作：{alert.get('actions')}",
        AlertSummary,
        max_tokens=300,
        purpose="alert_summary",
    )
    if result is None:
        return {"summary": fallback, "source": "template", "guardrail_rejected": None}
    return {"summary": result.summary, "source": _provider_tag(), "guardrail_rejected": None}


# ---- 2. CMS 導引文字（事件處置後，官方：導引文字由 LLM 生成） ----

class CmsText(BaseModel):
    cms: str = Field(description="CMS 電子看板導引文字，繁體中文，80 字內，單行")


_CMS_SYSTEM = """你是交控中心的 CMS 看板文字撰寫員。根據「確定性引擎已算出」的處置結果，
撰寫給駕駛人看的導引文字（80 字內、單行、明確可執行）。嚴格遵守：
1. 「必含字串」清單中的每一項都必須原封不動出現在文字中（路名、數字不可改寫）。
2. 不可新增清單外的路名、數字或指示。
3. 語氣專業簡潔，適合電子看板顯示。"""


def generate_cms_text(
    affected_name: str,
    primary_name: str | None,
    ete_display: int,
    incident: dict,
    extra_notes: list[str],
    fallback: str,
) -> tuple[str, dict]:
    required = [affected_name]
    if primary_name:
        required.append(primary_name)
    if ete_display > 0:
        required.append(str(ete_display))

    result = llm_client.structured_completion(
        _CMS_SYSTEM,
        f"事件：{incident.get('type')}｜{incident.get('location')}｜"
        f"狀態 {incident.get('status')}｜嚴重度 {incident.get('severity')}\n"
        f"受影響路段：{affected_name}\n"
        f"主疏散路徑：{primary_name or '（無，依現場指揮）'}\n"
        f"預計延誤：{ete_display} 分鐘\n"
        f"附加註記：{extra_notes or '無'}\n"
        f"必含字串（一字不差）：{required}",
        CmsText,
        max_tokens=300,
        purpose="cms_guidance",
    )
    if result is None:
        return fallback, {"source": "template", "guardrail_rejected": None}
    missing = _missing_tokens(result.cms, required)
    if missing:
        return fallback, {"source": "template",
                          "guardrail_rejected": f"LLM 導引文字缺必含字串 {missing}，退回模板"}
    return result.cms, {"source": _provider_tag(), "guardrail_rejected": None}


# ---- 3. 多語告警（SOP 6，官方：多語告警文字由 LLM 生成） ----

class MultilingualAlert(BaseModel):
    zh: str = Field(description="繁體中文告警")
    en: str = Field(description="英文告警")
    ja: str = Field(description="日文告警")
    ko: str = Field(description="韓文告警")


_MULTI_SYSTEM = """你是交控中心的多語通報撰寫員。根據已確認的中文處置內容，
撰寫四語（繁中/英/日/韓）公眾告警，給該區域的本國民眾與外籍旅客。嚴格遵守：
1. 每一語言開頭必須含時間戳 [YYYY-MM-DD HH:MM]（與提供的完全一致）。
2. 延誤分鐘數等數字必須原樣出現在每一語言中，不可換算或省略。
3. 中文版必含提供的中文路名；英文版必含提供的英文路名。
4. 語句自然在地化（非逐字翻譯），語氣清楚、可立即行動。
5. 不可新增提供內容以外的指示或資訊。"""


def generate_multilingual(
    affected_name: str,
    affected_name_en: str,
    primary_name: str | None,
    primary_name_en: str | None,
    ete_display: int,
    at: datetime,
    incident: dict,
    fallback: dict[str, str],
) -> tuple[dict[str, str], dict]:
    ts = format_ts(at)
    result = llm_client.structured_completion(
        _MULTI_SYSTEM,
        f"時間戳：[{ts}]\n"
        f"事件：{incident.get('type')}｜{incident.get('description', '')}\n"
        f"受影響路段：{affected_name}（英文名 {affected_name_en}）\n"
        f"主疏散路徑：{primary_name or '無'}（英文名 {primary_name_en or '無'}）\n"
        f"預計延誤：{ete_display} 分鐘",
        MultilingualAlert,
        max_tokens=900,
        purpose="multilingual_alert",
    )
    if result is None:
        return fallback, {"source": "template", "guardrail_rejected": None}

    messages = result.model_dump()
    # Guardrail：每語言必含時間戳；數字語言不變性——ETE 必須原樣出現在每一語言
    for lang, text in messages.items():
        required = [ts]
        if ete_display > 0:
            required.append(str(ete_display))
        if lang == "zh":
            required.append(affected_name)
            if primary_name:
                required.append(primary_name)
        if lang == "en" and affected_name_en:
            required.append(affected_name_en)
        missing = _missing_tokens(text, required)
        if missing:
            return fallback, {"source": "template",
                              "guardrail_rejected": f"{lang} 版缺必含字串 {missing}，四語整包退回模板"}
    return messages, {"source": _provider_tag(), "guardrail_rejected": None}


# ---- Coordinator 用的組合入口 ----

def build_notification_content(
    state: dict, incident: dict, at: datetime,
    affected_id: str, affected_name: str,
) -> dict:
    """產生 CMS 與多語訊息（LLM 優先、模板保底），回傳 notifications dict。"""
    ete_display = state["ete_result"]["ete_minutes_display"] if state.get("ete_result") else 0
    primary = (state.get("routing_result") or {}).get("primary_route")
    primary_name = primary["name"] if primary else None
    primary_id = primary["segment_id"] if primary else None
    affected_en = notifications.ROAD_NAME_EN.get(affected_id, affected_name)
    primary_en = notifications.ROAD_NAME_EN.get(primary_id, primary_name) if primary else None

    result: dict = {}
    rules = set(state.get("triggered_rules", []))

    # CMS：模板為保底，LLM 生成經 token 驗證
    template_lines = []
    extra_notes = []
    if 2 in rules:
        template_lines.append(
            notifications.cms_reroute_message(affected_name, primary_name, ete_display))
    if 5 in rules:
        template_lines.append(notifications.cms_signal_failure_note(affected_name))
        extra_notes.append("號誌故障，請依現場指揮通行")
    if template_lines:
        fallback_cms = " / ".join(template_lines)
        cms, cms_meta = generate_cms_text(
            affected_name, primary_name if 2 in rules else None,
            ete_display, incident, extra_notes, fallback_cms)
        result["cms"] = cms
        result["cms_meta"] = cms_meta

    # 多語：模板為保底，LLM 生成經 token+數字驗證
    fallback_msgs = notifications.multilingual_reroute(
        affected_name, affected_en, primary_name, primary_en, ete_display, at)
    messages, msg_meta = generate_multilingual(
        affected_name, affected_en, primary_name, primary_en,
        ete_display, at, incident, fallback_msgs)
    result["messages_meta"] = msg_meta
    return result | {"_full_messages": messages}
