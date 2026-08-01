"""通報內容生成（確定性模板版）。

依技術文件 20.3：即使 LLM 失敗，仍須以模板產出 CMS 與多語訊息，
因此模板為第一層實作；LLM 潤飾屬 Phase 2 加分。
時間格式統一 YYYY-MM-DD HH:MM（SOP 第 6 條）。
"""
from __future__ import annotations

from datetime import datetime

from .data_loader import format_ts


def cms_reroute_message(
    affected_name: str, primary_name: str | None, ete_minutes_display: int
) -> str:
    """SOP 第 2 條 CMS 格式。"""
    if primary_name is None:
        return f"{affected_name}封閉，請依現場指揮改道，預計延誤 {ete_minutes_display} 分鐘"
    return f"{affected_name}封閉，請改道 {primary_name}，預計延誤 {ete_minutes_display} 分鐘"


def cms_signal_failure_note(road_name: str) -> str:
    """SOP 第 5 條 CMS 加註。"""
    return f"{road_name} 號誌故障，請依現場指揮通行"


# 事故原因四語對照（key 為 live_incidents.json 的 type）
# 未知類型以中性描述保底，確保訊息永遠說得出「發生什麼事」。
# `ko_particle` 為 ko 詞尾接的「로/으로」：尾音為母音或 ㄹ 用「로」，其餘用「으로」。
# 預先寫定而非程式推導，避免助詞錯用（如「함몰으로」）。
CAUSE_TEXT: dict[str, dict[str, str]] = {
    "Road_Collapse_Accident": {
        "zh": "路面塌陷",
        "en": "a road collapse",
        "ja": "路面陥没",
        "ko": "도로 함몰",
        "ko_particle": "로",      # 함몰 → ㄹ 尾音
    },
    "Crowd_Surge_Injury": {
        "zh": "人群推擠事故",
        "en": "a crowd surge incident",
        "ja": "群衆事故",
        "ko": "군중 밀집 사고",
        "ko_particle": "로",      # 사고 → 母音尾音
    },
    "Power_Failure": {
        "zh": "號誌故障",
        "en": "a traffic signal failure",
        "ja": "信号故障",
        "ko": "신호기 고장",
        "ko_particle": "으로",    # 고장 → ㅇ 尾音
    },
}
_CAUSE_FALLBACK = {
    "zh": "交通事故", "en": "an incident", "ja": "交通障害",
    "ko": "교통 사고", "ko_particle": "로",
}

# 求援／避開提醒（四要素之一，固定句）。英日韓註明號碼用途——
# 外籍旅客不知道台灣 110/119 各自對應什麼。
_ASSIST_TEXT = {
    "zh": "請避開該區域，緊急事故請撥 110 或 119。",
    "en": "Please avoid the area. In an emergency, call 110 (police) or 119 (fire/ambulance).",
    "ja": "周辺を避けてください。緊急の場合は 110（警察）または 119（消防・救急）へ。",
    "ko": "해당 지역을 피해 주시기 바랍니다. 긴급 시 110(경찰) 또는 119(소방·구급)로 신고하십시오.",
}


def cause_text(incident_type: str | None) -> dict[str, str]:
    """取事故原因四語文字；未知類型回中性描述。"""
    return CAUSE_TEXT.get(incident_type or "", _CAUSE_FALLBACK)


def multilingual_reroute(
    affected_name: str,
    affected_name_en: str,
    primary_name: str | None,
    primary_name_en: str | None,
    ete_minutes_display: int,
    at: datetime,
    incident_type: str | None = None,
    rules: set[int] | None = None,
) -> dict[str, str]:
    """SOP 第 6 條：中英必做、日韓加分，同一回應內產出。

    四要素（事故位置／改道指引／預計延誤／求援或避開提醒）以骨架逐句組裝：
    缺值只跳過該句，不整段換成一句空話——確保無疏散路徑的事件
    （SOP 3/5）訊息仍說得出發生什麼事、延誤多久、如何求援。
    """
    ts = format_ts(at)
    rules = rules or set()
    cause = cause_text(incident_type)
    closed = 2 in rules  # 第 2 條成立才是「封閉」，否則為「交通管制」

    out: dict[str, str] = {}

    # zh
    parts = [f"[{ts}] {affected_name}因{cause['zh']}{'封閉' if closed else '交通管制中'}。"]
    if primary_name:
        parts.append(f"請改道 {primary_name}。")
    elif 5 in rules:
        parts.append("請依現場指揮通行。")
    if ete_minutes_display > 0:
        parts.append(f"預計延誤 {ete_minutes_display} 分鐘。")
    parts.append(_ASSIST_TEXT["zh"])
    out["zh"] = "".join(parts)

    # en
    verb = "is closed" if closed else "is under traffic control"
    parts = [f"[{ts}] {affected_name_en} {verb} due to {cause['en']}."]
    if primary_name_en:
        parts.append(f"Please detour via {primary_name_en}.")
    elif 5 in rules:
        parts.append("Please follow on-site instructions.")
    if ete_minutes_display > 0:
        parts.append(f"Expected delay: {ete_minutes_display} minutes.")
    parts.append(_ASSIST_TEXT["en"])
    out["en"] = " ".join(parts)

    # ja
    parts = [f"[{ts}] {affected_name}は{cause['ja']}のため{'通行止め' if closed else '交通規制中'}です。"]
    if primary_name:
        parts.append(f"{primary_name}へ迂回してください。")
    elif 5 in rules:
        parts.append("現場の指示に従ってください。")
    if ete_minutes_display > 0:
        parts.append(f"予想遅延：約{ete_minutes_display}分。")
    parts.append(_ASSIST_TEXT["ja"])
    out["ja"] = "".join(parts)

    # ko
    # 路名維持中文，韓語助詞（이/가、으로）無法依尾音正確變化，
    # 故改用冒號句式避開助詞，不輸出「松高路이(가)」這種機械式並列。
    state_ko = "통제" if closed else "교통 통제"
    parts = [
        f"[{ts}] {affected_name}: {cause['ko']}{cause['ko_particle']} 인해 {state_ko} 중입니다."
    ]
    if primary_name:
        parts.append(f"우회 도로: {primary_name}.")
    elif 5 in rules:
        parts.append("현장 안내에 따라 주시기 바랍니다.")
    if ete_minutes_display > 0:
        parts.append(f"예상 지연: 약 {ete_minutes_display}분.")
    parts.append(_ASSIST_TEXT["ko"])
    out["ko"] = " ".join(parts)

    return out


# 路段英文名（主辦資料無英文名，Demo 用固定對照表）
ROAD_NAME_EN = {
    "RD_TPE_001": "Zhongxiao E. Rd. Sec. 4",
    "RD_TPE_002": "Guangfu S. Rd.",
    "RD_TPE_003": "Keelung Rd. Sec. 1",
    "RD_TPE_004": "Civic Blvd. Sec. 4",
    "RD_TPE_005": "Ren'ai Rd. Sec. 4",
    "RD_TPE_006": "Dunhua S. Rd. Sec. 1",
    "RD_TPE_007": "Songgao Rd.",
    "RD_TPE_008": "Yanji St.",
    "RD_TPE_009": "Keelung Rd. Underpass",
    "RD_TPE_010": "Shifu Rd.",
    "RD_TPE_011": "Songshou Rd.",
    "RD_TPE_012": "Dunhua S. Rd. Sec. 2",
    "RD_TPE_013": "Xinyi Rd. Sec. 5",
    "RD_TPE_014": "Songzhi Rd.",
    "RD_TPE_015": "Fuxing S. Rd. Sec. 1",
}
