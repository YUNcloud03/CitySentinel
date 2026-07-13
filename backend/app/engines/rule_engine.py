"""確定性 SOP 規則引擎（SOP 1–6）。

每個觸發結果為 dict：
{
    "rule_id": int,
    "entity_id": str,
    "evidence": {...原始數值...},
    "actions": [str, ...],
}
LLM 不參與任何判定，只在下游做文字解釋。
"""
from __future__ import annotations

import re
from datetime import datetime

from ..data_loader import CrowdRecord, TrafficRecord, crowd_peak

# SOP 1
LEVEL_B_THRESHOLD = 0.85
LEVEL_A_THRESHOLD = 0.95
CONGESTION_TRIGGER_SEGMENTS = ("RD_TPE_001", "RD_TPE_002")

# SOP 2
INCIDENT_STATUSES = {"Closed", "Blocked", "Restricted"}
INCIDENT_SEVERITIES = {"High", "Critical"}

# SOP 3
MRT_STATION = "BS_MRT_BL17"
MRT_WALK_TARGET = "BS_MRT_BL18"
MRT_GROWTH_THRESHOLD = 0.30
MRT_USER_THRESHOLD = 25_000

# SOP 4
DOME_STATION = "BS_TPE_DOME"
DOME_PEAK_THRESHOLD = 30_000
DOME_DISPERSAL_GROWTH = -0.20

# SOP 6
ROAMING_THRESHOLD_PCT = 30.0

_SIGNAL_FAILURE_PATTERN = re.compile(r"號誌失效|故障")


def classify_congestion(saturation_score: float) -> str:
    """SOP 1：回傳 'A'（癱瘓/紅燈）、'B'（壅擠/黃燈）或 'Normal'。"""
    if saturation_score >= LEVEL_A_THRESHOLD:
        return "A"
    if saturation_score >= LEVEL_B_THRESHOLD:
        return "B"
    return "Normal"


def evaluate_traffic(snapshot: dict[str, TrafficRecord]) -> dict:
    """SOP 1：全 15 路段分級 + 城市應變觸發路段動作。"""
    levels = {
        seg_id: classify_congestion(rec.saturation_score)
        for seg_id, rec in snapshot.items()
    }
    triggers = []
    for seg_id in CONGESTION_TRIGGER_SEGMENTS:
        rec = snapshot.get(seg_id)
        if rec is None:
            continue
        level = levels[seg_id]
        if level == "Normal":
            continue
        actions = [
            "通報交控中心啟動長綠燈時制",
            "替代道路綠燈配時 +25%",
            "調度警力淨空路口",
        ]
        if level == "A":
            actions.append("觸發替代路徑引導（SOP 第 2 條）")
        triggers.append(
            {
                "rule_id": 1,
                "entity_id": seg_id,
                "evidence": {
                    "saturation_score": rec.saturation_score,
                    "congestion_level": level,
                    "timestamp": rec.timestamp,
                },
                "actions": actions,
            }
        )
    return {"levels": levels, "triggers": triggers}


def evaluate_crowd(
    snapshot: dict[str, CrowdRecord],
    history: list[CrowdRecord],
    at: datetime,
) -> list[dict]:
    """SOP 3（捷運分流）、SOP 4（大巨蛋散場）、SOP 6（多語通報）。"""
    triggers: list[dict] = []

    # SOP 3：BL17 Growth_Rate > 0.30 或 User_Count > 25,000（任一成立）
    bl17 = snapshot.get(MRT_STATION)
    if bl17 is not None:
        conditions = []
        if bl17.growth_rate > MRT_GROWTH_THRESHOLD:
            conditions.append(f"Growth_Rate {bl17.growth_rate} > {MRT_GROWTH_THRESHOLD}")
        if bl17.user_count > MRT_USER_THRESHOLD:
            conditions.append(f"User_Count {bl17.user_count} > {MRT_USER_THRESHOLD}")
        if conditions:
            triggers.append(
                {
                    "rule_id": 3,
                    "entity_id": MRT_STATION,
                    "evidence": {
                        "user_count": bl17.user_count,
                        "growth_rate": bl17.growth_rate,
                        "matched_conditions": conditions,
                        "timestamp": bl17.timestamp,
                    },
                    "actions": [
                        "建議北捷過站不停",
                        "通知公車處調度接駁專車",
                        f"引導群眾步行至 {MRT_WALK_TARGET}（捷運市政府站）",
                    ],
                }
            )

    # SOP 4：大巨蛋歷史峰值 >= 30,000 且當前 Growth_Rate <= -0.20
    dome = snapshot.get(DOME_STATION)
    if dome is not None:
        peak = crowd_peak(history, DOME_STATION, at)
        if peak >= DOME_PEAK_THRESHOLD and dome.growth_rate <= DOME_DISPERSAL_GROWTH:
            triggers.append(
                {
                    "rule_id": 4,
                    "entity_id": DOME_STATION,
                    "evidence": {
                        "historical_peak": peak,
                        "current_growth_rate": dome.growth_rate,
                        "current_user_count": dome.user_count,
                        "timestamp": dome.timestamp,
                    },
                    "actions": ["標記散場啟動", "提前連動第 3 條接駁分流機制"],
                }
            )

    # SOP 6：任一基地台 Roaming_User_Pct >= 30%
    for bs_id, rec in sorted(snapshot.items()):
        if rec.roaming_user_pct >= ROAMING_THRESHOLD_PCT:
            triggers.append(
                {
                    "rule_id": 6,
                    "entity_id": bs_id,
                    "evidence": {
                        "roaming_user_pct": rec.roaming_user_pct,
                        "location_name": rec.location_name,
                        "timestamp": rec.timestamp,
                    },
                    "actions": ["啟動多語通報（中文、英文，加分：日文、韓文）"],
                }
            )
    return triggers


def evaluate_incident(incident: dict) -> list[dict]:
    """SOP 2（車禍與路障）、SOP 5（號誌故障）。"""
    triggers: list[dict] = []

    status = incident.get("status", "")
    severity = incident.get("severity", "")
    segment = incident.get("affected_segment", "")
    description = incident.get("description", "")

    # SOP 2：三項條件須同時成立
    rule2_checks = {
        "status_in_scope": status in INCIDENT_STATUSES,
        "severity_in_scope": severity in INCIDENT_SEVERITIES,
        "segment_is_road": segment.startswith("RD_"),
    }
    if all(rule2_checks.values()):
        triggers.append(
            {
                "rule_id": 2,
                "entity_id": segment,
                "evidence": {
                    "status": status,
                    "severity": severity,
                    "affected_segment": segment,
                    "checks": rule2_checks,
                },
                "actions": ["啟動替代路徑規劃（Routing Engine）", "產出 CMS 改道文字"],
            }
        )

    # SOP 5：type = Power_Failure 或描述含「號誌失效／故障」
    is_power_failure = incident.get("type") == "Power_Failure"
    keyword_hit = bool(_SIGNAL_FAILURE_PATTERN.search(description))
    if is_power_failure or keyword_hit:
        triggers.append(
            {
                "rule_id": 5,
                "entity_id": segment or incident.get("event_id", ""),
                "evidence": {
                    "type": incident.get("type"),
                    "matched_keyword": keyword_hit,
                    "description": description,
                },
                "actions": [
                    "產出人工交通指揮派遣建議",
                    "每路口配置警力 2 人",
                    "CMS 加註「請依現場指揮通行」",
                ],
            }
        )
    return triggers
