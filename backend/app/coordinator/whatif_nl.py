"""What-if 自然語言 → 結構化 scenario（確定性 regex 版）。

技術文件定位：LLM 負責模糊理解，但 Demo 不能被 LLM 逾時卡死，
因此先以 regex 覆蓋常見問法作為保底；之後接 LLM 時只要輸出同一
scenario 格式，即共用 run_what_if() 同一套引擎。

支援問法範例：
    「如果 BL17 人數增加到 40000 人會怎樣？」
    「如果國父紀念館站成長率變成 0.5？」
    「假設台北101漫遊率 50%」
    「如果 22:30 光復南路飽和度 0.9」
    「如果封閉忠孝東路會怎樣？」
"""
from __future__ import annotations

import re

DEFAULT_AT = "2026-05-20 22:00"

STATION_ALIASES = {
    "BS_MRT_BL17": ["BL17", "國父紀念館"],
    "BS_MRT_BL18": ["BL18", "市政府站"],
    "BS_MRT_BL16": ["BL16", "忠孝敦化"],
    "BS_TPE_DOME": ["大巨蛋"],
    "BS_TPE_101": ["101"],
    "BS_XY_VIESHOW": ["威秀"],
    "BS_XY_ATT": ["ATT"],
    "BS_BUS_TERM": ["轉運站"],
    "BS_SS_PARK": ["松山文創", "文創園區"],
}

ROAD_ALIASES = {
    "RD_TPE_001": ["忠孝東路"],
    "RD_TPE_002": ["光復南路"],
    "RD_TPE_003": ["基隆路一段"],
    "RD_TPE_004": ["市民大道"],
    "RD_TPE_005": ["仁愛路"],
    "RD_TPE_006": ["敦化南路一段"],
    "RD_TPE_007": ["松高路"],
    "RD_TPE_008": ["延吉街"],
    "RD_TPE_009": ["基隆路地下道", "地下道"],
    "RD_TPE_010": ["市府路"],
    "RD_TPE_011": ["松壽路"],
    "RD_TPE_012": ["敦化南路二段"],
    "RD_TPE_013": ["信義路"],
    "RD_TPE_014": ["松智路"],
    "RD_TPE_015": ["復興南路"],
}

_NUM = r"([0-9][0-9,\.]*)\s*(萬)?"


def _find_entity(question: str, aliases: dict[str, list[str]]) -> str | None:
    # 別名長的優先比對（避免「敦化南路一段」被「敦化南路二段」誤配之類）
    matches = []
    for entity_id, names in aliases.items():
        for name in names + [entity_id]:
            if name and name in question:
                matches.append((len(name), entity_id))
    return max(matches)[1] if matches else None


def _parse_number(m: re.Match) -> float:
    value = float(m.group(1).replace(",", ""))
    if m.group(2):  # 萬
        value *= 10_000
    return value


def parse_question(question: str) -> dict:
    """把自然語言問題轉為 run_what_if() 的 scenario。解析不到覆寫時 raise ValueError。"""
    scenario: dict = {}

    # 時間切面：問題中出現 HH:MM 就用，否則預設高峰 22:00
    t = re.search(r"([01]?\d|2[0-3]):([0-5]\d)", question)
    scenario["at"] = f"2026-05-20 {int(t.group(1)):02d}:{t.group(2)}" if t else DEFAULT_AT

    station = _find_entity(question, STATION_ALIASES)
    road = _find_entity(question, ROAD_ALIASES)

    crowd_fields: dict = {}
    traffic_fields: dict = {}

    m = re.search(r"人[數数流]?\D{0,8}?" + _NUM, question)
    if m and station:
        crowd_fields["user_count"] = int(_parse_number(m))
    m = re.search(r"成長率\D{0,8}?(-?[0-9.]+)", question)
    if m and station:
        crowd_fields["growth_rate"] = float(m.group(1))
    m = re.search(r"漫遊\D{0,8}?([0-9.]+)\s*%?", question)
    if m and station:
        crowd_fields["roaming_user_pct"] = float(m.group(1))
    m = re.search(r"飽和\D{0,8}?([0-9.]+)", question)
    if m and road:
        traffic_fields["saturation_score"] = float(m.group(1))

    if crowd_fields and station:
        scenario["crowd_overrides"] = {station: crowd_fields}
    if traffic_fields and road:
        scenario["traffic_overrides"] = {road: traffic_fields}

    # 封閉／封鎖路段 → 模擬事故（走 SOP 2 全流程）
    if road and re.search(r"封[閉鎖]|全線封|坍|塌", question):
        scenario["simulated_incident"] = {
            "event_id": "WHATIF_SIM",
            "type": "Simulated_Closure",
            "affected_segment": road,
            "status": "Closed",
            "severity": "Critical",
            "location": "",
            "description": f"What-if 模擬封閉 {road}",
            "timestamp": scenario["at"],
        }

    if not any(k in scenario for k in ("crowd_overrides", "traffic_overrides", "simulated_incident")):
        raise ValueError(
            "無法從問題解析出假設條件。支援：人數／成長率／漫遊率／飽和度覆寫，或「封閉某路段」。"
        )
    return scenario
