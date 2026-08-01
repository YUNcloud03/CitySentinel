"""多源事件可信度評估（信心分數）。

回答指揮官的問題：「為什麼相信這個事件是真的？」
融合多個獨立訊號，每個訊號都附上可驗證的證據字串：

    官方事件來源          +0.50（自訂注入 +0.30）
    同路段車速崩跌        +0.20（或飽和度 >= 0.95 時 +0.15）
    車道狀態與事件相符    +0.15
    周邊基地台人流異常    +0.10

完全確定性、可重算；分數同時控制資源保留與通知閘門。
"""
from __future__ import annotations

from ..data_loader import CrowdRecord, RoadSegment, TrafficRecord

SPEED_COLLAPSE_KMH = 10       # 車速低於此值視為崩跌
SATURATION_CRITICAL = 0.95    # A 級門檻
CROWD_ANOMALY_GROWTH = 0.30   # 周邊人流成長率絕對值門檻
ABNORMAL_LANE_STATUS = {"Accident_Impact", "Blocked", "Gridlock", "Closed"}

LEVELS = ((0.75, "高"), (0.50, "中"), (0.0, "低"))

SOURCE_PRIORS = {
    "official": 0.50,
    "organizer_dataset": 0.50,
    "operator": 0.30,
    "iot": 0.30,
    "camera": 0.30,
    "citizen": 0.10,
    "unknown": 0.10,
}


def _source_type(incident: dict) -> tuple[str, bool]:
    explicit = str(incident.get("source_type") or "").strip().lower()
    if explicit in SOURCE_PRIORS:
        return explicit, False
    # 主辦方事件檔沒有 provenance 欄位；保留舊資料相容性，但明示為推定。
    if incident.get("event_id", "").startswith("TPE_"):
        return "organizer_dataset", True
    return "operator", True


def _execution_policy(score: float, source_type: str, human_confirmed: bool) -> dict:
    trusted_source = source_type in {"official", "organizer_dataset"}
    authorized_operator = source_type == "operator" and human_confirmed
    if score >= 0.75 or ((trusted_source or authorized_operator) and score >= 0.50):
        return {"code": "ACTION_PROPOSED", "resource_reservation_allowed": True,
                "external_action_requires_human_approval": True}
    if score >= 0.50:
        return {"code": "HUMAN_CONFIRMATION_REQUIRED", "resource_reservation_allowed": False,
                "external_action_requires_human_approval": True}
    return {"code": "MONITOR_ONLY", "resource_reservation_allowed": False,
            "external_action_requires_human_approval": True}


def assess_confidence(
    incident: dict,
    traffic_snapshot: dict[str, TrafficRecord],
    crowd_snapshot: dict[str, CrowdRecord],
    network: dict[str, RoadSegment],
) -> dict:
    score = 0.0
    evidence: list[str] = []

    # 訊號 1：事件來源。來源種類與是否為推定都回傳供稽核。
    source_type, source_inferred = _source_type(incident)
    score += SOURCE_PRIORS[source_type]
    evidence.append(f"事件來源 {source_type}（權重 {SOURCE_PRIORS[source_type]:.2f}）")
    human_confirmed = bool(
        incident.get("human_confirmed", source_inferred and source_type == "operator")
    )
    if human_confirmed:
        score += 0.20
        evidence.append("事件已由值勤人員確認（+0.20）")

    # 受影響路段（BS_ 事件用 affected_road）
    seg_id = incident.get("affected_segment", "")
    if not seg_id.startswith("RD_"):
        seg_id = incident.get("affected_road", "")
    rec = traffic_snapshot.get(seg_id)
    seg = network.get(seg_id)
    seg_name = seg.name if seg else seg_id

    # 訊號 2：同路段車流異常
    if rec is not None:
        if rec.avg_speed <= SPEED_COLLAPSE_KMH:
            score += 0.20
            evidence.append(f"{seg_name} 車速降至 {rec.avg_speed} km/h（{rec.timestamp:%H:%M} 快照）")
        elif rec.saturation_score >= SATURATION_CRITICAL:
            score += 0.15
            evidence.append(f"{seg_name} 飽和度 {rec.saturation_score:.2f} 達 A 級")

        # 訊號 3：車道狀態與事件描述相符
        if rec.lane_status in ABNORMAL_LANE_STATUS:
            score += 0.15
            evidence.append(f"{seg_name} 車道狀態為 {rec.lane_status}，與事件通報一致")
    else:
        evidence.append(f"{seg_name or '受影響路段'} 無同時段車流資料可交叉驗證")

    # 訊號 4：周邊基地台人流異常（取一次，不重複加分）
    if seg is not None:
        for bs_id in seg.nearby_stations:
            c = crowd_snapshot.get(bs_id)
            if c is not None and abs(c.growth_rate) >= CROWD_ANOMALY_GROWTH:
                score += 0.10
                direction = "上升" if c.growth_rate > 0 else "下降"
                evidence.append(
                    f"周邊 {c.location_name} 人流{direction}"
                    f"（成長率 {c.growth_rate:+.2f}，{c.user_count:,} 人）"
                )
                break

    score = round(min(score, 0.99), 2)
    level = next(label for threshold, label in LEVELS if score >= threshold)
    return {
        "confidence_score": score,
        "level": level,
        "evidence": evidence,
        "source": {
            "type": source_type,
            "source_id": incident.get("source_id"),
            "inferred": source_inferred,
            "note": "inferred=true 表示來源由相容規則推定，並非數位簽章或外部查證",
        },
        "execution_policy": _execution_policy(score, source_type, human_confirmed),
        "note": "可信度控制資源保留與通知狀態；所有外部動作仍需人工核准。",
    }
