"""SOP 第 7 條：預計恢復時間 (ETE)。

ETE_minutes = base_clearance + congestion_penalty
    base_clearance：Critical = 60、High = 40、Medium = 20（分鐘）
    congestion_penalty = max(0, (受影響路段平均 Saturation_Score - 0.5) * 60)

後端保留原始小數值，UI 顯示時再四捨五入。
"""
from __future__ import annotations

BASE_CLEARANCE = {"Critical": 60, "High": 40, "Medium": 20}
PENALTY_BASELINE = 0.5
PENALTY_FACTOR = 60


def calculate_ete(severity: str, saturation_scores: list[float]) -> dict:
    if severity not in BASE_CLEARANCE:
        raise ValueError(f"未知的 severity: {severity!r}（須為 Critical/High/Medium）")
    if not saturation_scores:
        raise ValueError("saturation_scores 不可為空：ETE 需要受影響路段的飽和度資料")

    avg_saturation = sum(saturation_scores) / len(saturation_scores)
    base = BASE_CLEARANCE[severity]
    penalty = max(0.0, (avg_saturation - PENALTY_BASELINE) * PENALTY_FACTOR)
    ete = base + penalty
    return {
        "severity": severity,
        "average_saturation": avg_saturation,
        "base_clearance_minutes": base,
        "congestion_penalty_minutes": penalty,
        "ete_minutes": ete,
        "ete_minutes_display": round(ete),
        "formula": (
            f"ETE = {base} + max(0, ({avg_saturation:.4f} - {PENALTY_BASELINE}) "
            f"× {PENALTY_FACTOR}) = {ete:.2f} 分鐘"
        ),
    }
