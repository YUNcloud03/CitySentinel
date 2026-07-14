"""調度引擎：依「事件造成的規則」產生資源需求並向 registry 配置。

關鍵設計（同時修正 review 指出的規則歸因問題）：
    調度只看「事件本身造成」的規則，不把同一時間切面的環境人流
    SOP 3/4/6 誤算進來。例如光復南路塌陷不應調度大巨蛋散場的資源。

    - 事件規則（SOP 2 車禍路障、SOP 5 號誌故障）→ 一律屬事件造成。
    - 人流規則（SOP 3 捷運分流）→ 僅當該事件的 affected_segment 就是
      觸發的基地台時，才視為事件造成並納入調度。

資源不足時回傳缺口與人工升級需求，不得標示任務已完成（SOP 調度規則 4）。
"""
from __future__ import annotations

from ..data_loader import RoadSegment
from . import registry as reg

POLICY_SOURCE = "Coordinator Resource Policy v1.0"


def build_requirements(
    incident: dict,
    incident_rule_ids: set[int],
    crowd_rule_ids_for_incident: set[int],
    routing_result: dict | None,
    network: dict[str, RoadSegment],
) -> list[dict]:
    """產生資源需求清單（尚未配置）。每筆含 challenge 問題與確定性依據。"""
    reqs: list[dict] = []
    severity = incident.get("severity", "")
    seg_id = incident.get("affected_segment", "")

    # SOP 2：車禍與路障
    if 2 in incident_rule_ids:
        police = 4 if severity == "Critical" else 2
        detail = (
            "Critical 路段封閉，需 2 人封鎖 + 2 人上游路口淨空"
            if severity == "Critical"
            else "路段受阻，需 2 人現場管制"
        )
        reqs.append(_req(2, reg.POLICE, police, "事故封鎖與上游路口淨空", detail))
        primary = (routing_result or {}).get("primary_route")
        if primary:
            reqs.append(_req(
                2, reg.SIGNAL_CONTROL, 1,
                f"替代道路「{primary['name']}」長綠燈時制",
                "主疏散路徑啟動長綠燈配時 +25%",
            ))

    # SOP 3：捷運與接駁分流（僅當事件本身就是該基地台）
    if 3 in crowd_rule_ids_for_incident:
        reqs.append(_req(3, reg.MRT_LIAISON, 1, "協調北捷過站不停", "BL17 人流達門檻，需北捷行控協調"))
        reqs.append(_req(3, reg.SHUTTLE, 2, "調度接駁專車", "公車處調度接駁專車疏運"))
        reqs.append(_req(3, reg.POLICE, 2, "出口引導與步行分流至 BL18", "引導群眾步行至捷運市政府站"))

    # SOP 5：號誌故障（每受影響路口配置 2 名警力）
    if 5 in incident_rule_ids:
        seg = network.get(seg_id)
        n_intersections = len(seg.intersections) if seg else 1
        reqs.append(_req(
            5, reg.POLICE, 2 * n_intersections,
            f"人工交通指揮（每路口 2 人 × {n_intersections} 路口）",
            f"號誌失效，{n_intersections} 個受影響路口各需 2 名警力現場指揮",
        ))
        reqs.append(_req(5, reg.SIGNAL_MAINT, 1, "號誌搶修", "派遣號誌維修組排除故障"))

    return reqs


def _req(rule_id: int, rtype: str, count: int, purpose: str, deterministic_result: str) -> dict:
    return {
        "rule_id": rule_id,
        "resource_type": rtype,
        "requested_count": count,
        "purpose": purpose,
        "deterministic_result": deterministic_result,
    }


def plan_dispatch(
    registry: reg.ResourceRegistry,
    requirements: list[dict],
    snapshot_id: str,
) -> dict:
    """依需求向 registry 配置，產生帶證據包的動作清單。

    每個動作即一份「證據包」，可供管理者 Challenge / 接受 / 拒絕 / 覆寫。
    """
    actions: list[dict] = []
    gaps: list[dict] = []
    for i, req in enumerate(requirements, start=1):
        assignments, gap = registry.allocate(req["resource_type"], req["requested_count"])
        fulfilled = req["requested_count"] - gap
        type_label = reg.TYPE_LABELS.get(req["resource_type"], req["resource_type"])
        action = {
            "action_id": f"ACT-{i:03d}",
            "action": f"派遣 {req['requested_count']} 單位 {type_label}：{req['purpose']}",
            "rule_id": req["rule_id"],
            "resource_type": req["resource_type"],
            "requested_count": req["requested_count"],
            "fulfilled_count": fulfilled,
            "gap": gap,
            "input_snapshot_id": snapshot_id,
            "source": POLICY_SOURCE,
            "deterministic_result": req["deterministic_result"],
            "challenge_question": (
                f"確認 {type_label} 是否仍有 {req['requested_count']} 單位可於 ETA 內抵達？"
            ),
            "assignments": assignments,
            "status": "shortfall" if gap > 0 else "proposed",
            "override": None,
        }
        if gap > 0:
            action["escalation"] = (
                f"資源不足：{type_label} 尚缺 {gap} 單位，需人工升級調度或跨區支援；"
                f"此任務未完成，不得標示為已達成。"
            )
            gaps.append({
                "action_id": action["action_id"],
                "resource_type": req["resource_type"],
                "gap": gap,
                "purpose": req["purpose"],
            })
        actions.append(action)

    return {
        "snapshot_id": snapshot_id,
        "actions": actions,
        "gaps": gaps,
        "has_shortfall": bool(gaps),
        "policy_source": POLICY_SOURCE,
    }
