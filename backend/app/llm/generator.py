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


# 可讀性守則（官方要求：適合 CMS 與手機簡訊、避免冗長技術術語）
CMS_MAX_CHARS = 80
# 簡訊上限依語言分開：中日文為表意文字，同樣資訊量字數遠少於拉丁字母；
# 韓文雖為音節文字但敬語詞尾偏長。上限以確定性模板的最壞情況實測值加裕度訂定
# （zh 88 / ja 112 / ko 145 / en 248）——模板是保底輸出，
# 若模板自身超標，等於系統執行不了自己訂的規則。
# 由 test_template_within_sms_limits 鎖住此不變量。
SMS_MAX_CHARS = {"zh": 110, "ja": 140, "ko": 175, "en": 290}
SMS_MAX_CHARS_DEFAULT = 175
# 內部識別碼與縮寫不得出現在民眾訊息中
_JARGON = ("RD_", "BS_", "SOP", "ETE", "saturation", "Roaming_User_Pct", "rule_id")
# 求援提醒必含的電話（四語皆須含兩者）
ASSIST_NUMBERS = ("110", "119")


def _found_jargon(text: str) -> list[str]:
    return [j for j in _JARGON if j in text]


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
3. 語氣專業簡潔，適合電子看板顯示。
4. 一律使用民眾看得懂的說法：禁止出現內部代號或術語
   （如 RD_TPE_002、BS_ 開頭代號、SOP、ETE、saturation）。"""


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
    jargon = _found_jargon(result.cms)
    if jargon:
        return fallback, {"source": "template",
                          "guardrail_rejected": f"LLM 導引文字含內部術語 {jargon}，退回模板"}
    if len(result.cms) > CMS_MAX_CHARS:
        return fallback, {"source": "template",
                          "guardrail_rejected": (
                              f"LLM 導引文字 {len(result.cms)} 字超過 CMS 上限 "
                              f"{CMS_MAX_CHARS} 字，退回模板")}
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
4. 每則訊息須涵蓋四要素：事故位置與原因、改道或通行指引、預計延誤時間、
   求援或避開提醒。提供的欄位為空者略過該項，其餘不可缺。
5. 每一語言結尾必須含求援提醒，且必須同時出現 110 與 119 兩個號碼。
   英日韓版請註明號碼用途（110 警察、119 消防救護），外籍旅客不知道台灣的號碼分工。
6. 除第 4、5 點要求的內容外，不可新增提供資料以外的路名、數字或指示。
7. 語句自然在地化（非逐字翻譯），語氣清楚、可立即行動。
8. 一律使用民眾看得懂的說法：禁止出現內部代號或術語
   （如 RD_TPE_002、BS_ 開頭代號、SOP、ETE、saturation）。
9. 長度須適合手機簡訊與 CMS 看板呈現：中文 110 字、日文 140 字、韓文 175 字、
   英文 290 字元以內，越簡短越好。"""


def generate_multilingual(
    affected_name: str,
    affected_name_en: str,
    primary_name: str | None,
    primary_name_en: str | None,
    ete_display: int,
    at: datetime,
    incident: dict,
    fallback: dict[str, str],
    extra_notes: list[str] | None = None,
) -> tuple[dict[str, str], dict]:
    ts = format_ts(at)
    cause = notifications.cause_text(incident.get("type"))
    result = llm_client.structured_completion(
        _MULTI_SYSTEM,
        f"時間戳：[{ts}]\n"
        f"事件：{incident.get('type')}｜{incident.get('description', '')}\n"
        f"事故原因（須在訊息中說明）：{cause['zh']}／{cause['en']}\n"
        f"受影響路段：{affected_name}（英文名 {affected_name_en}）\n"
        f"主疏散路徑：{primary_name or '無'}（英文名 {primary_name_en or '無'}）\n"
        f"預計延誤：{ete_display} 分鐘\n"
        f"現場處置注意事項：{extra_notes or '無'}\n"
        f"求援提醒必含號碼：110（警察）、119（消防救護）",
        MultilingualAlert,
        max_tokens=900,
        purpose="multilingual_alert",
    )
    if result is None:
        return fallback, {"source": "template", "guardrail_rejected": None}

    messages = result.model_dump()
    # Guardrail：每語言必含時間戳與求援號碼；數字語言不變性——ETE 必須原樣出現在每一語言
    for lang, text in messages.items():
        required = [ts, *ASSIST_NUMBERS]
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
        jargon = _found_jargon(text)
        if jargon:
            return fallback, {"source": "template",
                              "guardrail_rejected": f"{lang} 版含內部術語 {jargon}，四語整包退回模板"}
        limit = SMS_MAX_CHARS.get(lang, SMS_MAX_CHARS_DEFAULT)
        if len(text) > limit:
            return fallback, {"source": "template",
                              "guardrail_rejected": (
                                  f"{lang} 版 {len(text)} 字超過簡訊上限 {limit} 字，"
                                  f"四語整包退回模板")}
    return messages, {"source": _provider_tag(), "guardrail_rejected": None}


# ---- Coordinator 用的組合入口 ----

def build_notification_content(
    state: dict, incident: dict, at: datetime,
    affected_id: str, affected_name: str,
    multilingual: bool = True,
) -> dict:
    """產生 CMS 與多語訊息（LLM 優先、模板保底），回傳 notifications dict。

    multilingual=False（SOP 6 未觸發）時不呼叫四語 LLM，直接用模板——
    反正呼叫端只會取用中文，省下一次無謂的 LLM 呼叫。
    """
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
    # rules/extra_notes 一併傳入——否則多語訊息不知道號誌故障這類處置，
    # 無疏散路徑的事件會退化成一句「交通管制中」。
    fallback_msgs = notifications.multilingual_reroute(
        affected_name, affected_en, primary_name, primary_en, ete_display, at,
        incident_type=incident.get("type"), rules=rules)
    if multilingual:
        messages, msg_meta = generate_multilingual(
            affected_name, affected_en, primary_name, primary_en,
            ete_display, at, incident, fallback_msgs, extra_notes=extra_notes)
    else:
        messages, msg_meta = fallback_msgs, {"source": "template",
                                             "reason": "SOP 6 未觸發，僅需中文"}
    result["messages_meta"] = msg_meta
    return result | {"_full_messages": messages}
