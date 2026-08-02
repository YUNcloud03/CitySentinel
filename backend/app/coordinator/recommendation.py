"""交控中心建議書：把已完成的事件處理結果重組為官方要求的五項內容。

**本模組不做任何判定**——不設門檻、不推論、不呼叫 LLM。所有數值與理由
均取自 Coordinator 已寫入 state 的引擎輸出，這裡只負責歸類與挑選，
確保建議書上的每個數字都能回溯到決策鏈中的同一筆資料。

官方要求（交控中心建議書應涵蓋內容）：
    1. 事件辨識：event_id／描述 + 對應 SOP 條款編號
    2. 交通分級判定：A 級／B 級判定依據（引用車流與飽和度數值）
    3. 替代路徑建議：主疏散、次要替代，及排除其他候選之理由
    4. 號誌調整建議：受影響路段配時調整與時段
    5. 跨系統聯動：觸發第 3 條（人流）或第 5 條（號誌故障）時，
       對北捷、公車處、警力之請求
"""
from __future__ import annotations

from ..engines import rule_engine

# 建議書用的 SOP 條款標題（取自 SOP 全文的簡稱，供列表顯示）
_RULE_TITLES = {
    1: "壅塞分級與應變",
    2: "車禍與路障應變",
    3: "捷運人流疏散",
    4: "大型場館散場",
    5: "號誌故障處置",
    6: "多語通報",
    7: "ETE 計算",
}

# 跨系統聯動的收件單位判斷依據：關鍵詞 → 單位。
# 動作文字由 rule_engine 產生，此處僅做歸類。
_AGENCY_KEYWORDS = (
    ("北捷", "臺北捷運公司"),
    ("捷運", "臺北捷運公司"),
    ("公車處", "公共運輸處"),
    ("接駁", "公共運輸處"),
    ("警力", "警察局交通警察大隊"),
    ("警察", "警察局交通警察大隊"),
)

_RESOURCE_AGENCIES = {
    "Police": "警察局交通警察大隊",
    "Shuttle": "臺北市公共運輸處",
    "MRTLiaison": "臺北捷運公司行控中心",
    "SignalControl": "臺北市交通管制工程處",
    "SignalMaintenance": "臺北市交通管制工程處",
}

_COORDINATION_STATUS = {
    "proposed": ("待指揮官核准", "READY_FOR_APPROVAL"),
    "accepted": ("已授權進入模擬", "AUTHORIZED_FOR_SIMULATION"),
    "adjusted": ("人工調整後已授權", "ADJUSTED_AND_AUTHORIZED"),
    "rejected": ("指揮官已拒絕", "REJECTED"),
    "shortfall": ("資源不足，待升級調度", "RESOURCE_SHORTFALL"),
}

# 號誌調整相關動作的關鍵詞
_SIGNAL_KEYWORDS = ("綠燈", "配時", "號誌", "時制")


def _rule_label(rule_id: int) -> str:
    title = _RULE_TITLES.get(rule_id)
    return f"SOP 第 {rule_id} 條（{title}）" if title else f"SOP 第 {rule_id} 條"


def _identification(state: dict) -> dict:
    """1. 事件辨識：event_id／描述 + 觸發的 SOP 條款。"""
    event = state.get("event") or {}
    attribution = state.get("rule_attribution") or {}
    return {
        "event_id": state.get("incident_id"),
        "type": event.get("type"),
        "location": event.get("location"),
        "description": event.get("description"),
        "occurred_at": event.get("timestamp"),
        "assessed_at": state.get("as_of"),
        "severity": event.get("severity"),
        "status": event.get("status"),
        "triggered_rules": state.get("triggered_rules") or [],
        "triggered_rule_labels": [
            _rule_label(r) for r in (state.get("triggered_rules") or [])
        ],
        # 由本事件直接引發 vs 當下環境既有——兩者處置責任不同，分開列出
        "caused_by_incident": attribution.get("caused_by_incident") or [],
        "context_rules": attribution.get("context_rules") or [],
    }


def _grading(state: dict) -> dict:
    """2. 交通分級判定：引用飽和度數值與門檻。"""
    graded = []
    # congestion_grading 為同一時間切面的 SOP 1 分級結果（不併入 triggered_rules，
    # 故不能只讀 trigger_details，否則車禍類事件的分級區塊會是空的）
    for t in state.get("congestion_grading") or []:
        ev = t.get("evidence") or {}
        level = ev.get("congestion_level")
        score = ev.get("saturation_score")
        graded.append({
            "segment_id": t.get("entity_id"),
            "congestion_level": level,
            "saturation_score": score,
            "basis": (
                f"飽和度 {score} ≥ {rule_engine.LEVEL_A_THRESHOLD}（A 級門檻）"
                if level == "A" else
                f"飽和度 {score} ≥ {rule_engine.LEVEL_B_THRESHOLD}（B 級門檻）"
                f"且 < {rule_engine.LEVEL_A_THRESHOLD}"
            ),
        })

    ete = state.get("ete_result") or {}
    return {
        "graded_segments": graded,
        "thresholds": {
            "level_a": rule_engine.LEVEL_A_THRESHOLD,
            "level_b": rule_engine.LEVEL_B_THRESHOLD,
        },
        # ETE 屬第 7 條計算結果，列於此處供分級判定佐證
        "ete_minutes": ete.get("ete_minutes_display"),
        "ete_formula": ete.get("formula"),
        "average_saturation": ete.get("average_saturation"),
    }


def _routing(state: dict) -> dict:
    """3. 替代路徑建議：主疏散、次要替代、排除理由。"""
    routing = state.get("routing_result") or {}
    primary = routing.get("primary_route")
    return {
        "affected_segment": routing.get("affected_segment"),
        "incident_location": routing.get("incident_location"),
        "primary_route": primary,
        "secondary_routes": routing.get("secondary_routes") or [],
        # 排除理由是官方明確要求的項目，逐筆保留 reason_code 與說明
        "excluded_routes": routing.get("excluded_routes") or [],
    }


def _signal_plan(state: dict) -> dict:
    """4. 號誌調整建議：彙整號誌相關的規則動作與實際調度。

    兩個來源都要納入：SOP 1 壅塞分級的規則動作（如「替代道路綠燈配時 +25%」），
    以及資源調度中的 SignalControl 項目（載明實際套用的路段與配時）。
    僅 SOP 1 觸發時才有前者，故只讀規則動作會在車禍類事件漏掉整個區塊。
    """
    items: list[dict] = []
    seen: set[tuple] = set()

    for t in state.get("trigger_details") or []:
        rule_id = t.get("rule_id")
        entity = t.get("entity_id")
        for action in t.get("actions") or []:
            if not any(k in action for k in _SIGNAL_KEYWORDS):
                continue
            key = (entity, action)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "segment_id": entity,
                "action": action,
                "rule_id": rule_id,
                "rule_label": _rule_label(rule_id),
                "source": "rule_engine",
            })

    # 資源調度的號誌控制：帶實際套用路段與配時說明，較規則動作具體
    for act in (state.get("dispatch") or {}).get("actions") or []:
        if act.get("resource_type") != "SignalControl":
            continue
        key = (act.get("action_id"), act.get("action"))
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "segment_id": None,
            "action": act.get("action"),
            "detail": act.get("deterministic_result"),
            "rule_id": act.get("rule_id"),
            "rule_label": _rule_label(act.get("rule_id")),
            "fulfilled_count": act.get("fulfilled_count"),
            "gap": act.get("gap"),
            "source": "dispatch_engine",
        })

    # 調整時段以事件評估時間起算至 ETE 完成，供建議書載明適用期間
    ete = (state.get("ete_result") or {}).get("ete_minutes_display")
    return {
        "items": items,
        "effective_from": state.get("as_of"),
        "duration_minutes": ete,
        "note": (
            f"建議自 {state.get('as_of')} 起實施，預計維持 {ete} 分鐘（依 ETE 估算）"
            if ete else "調整時段依現場狀況滾動檢討"
        ),
    }


def _interagency(state: dict) -> dict:
    """5. 跨系統聯動：第 3 條（人流）或第 5 條（號誌故障）觸發時的對外請求。"""
    triggered = set(state.get("triggered_rules") or [])
    required = bool(triggered & {3, 5})

    requests: list[dict] = []
    seen: set[tuple] = set()

    # 規則動作中的對外協調事項
    for t in state.get("trigger_details") or []:
        rule_id = t.get("rule_id")
        for action in t.get("actions") or []:
            agency = next(
                (name for kw, name in _AGENCY_KEYWORDS if kw in action), None
            )
            if agency is None:
                continue
            key = (agency, action)
            if key in seen:
                continue
            seen.add(key)
            requests.append({
                "agency": agency,
                "request": action,
                "rule_id": rule_id,
                "rule_label": _rule_label(rule_id),
                "status": "規則建議，尚未形成外部派令",
                "status_code": "RULE_RECOMMENDATION_ONLY",
                "execution_mode": "simulation_adapter",
            })

    # 資源調度是可核准的具體聯動請求；仍是模擬 Adapter，不宣稱已送真實外部系統。
    for act in (state.get("dispatch") or {}).get("actions") or []:
        agency = _RESOURCE_AGENCIES.get(act.get("resource_type"))
        if agency is None:
            continue
        status, status_code = _COORDINATION_STATUS.get(
            act.get("status"), (act.get("status") or "未知", "UNKNOWN")
        )
        requests.append({
            "agency": agency,
            "request": act.get("action"),
            "action_id": act.get("action_id"),
            "requested_count": act.get("requested_count"),
            "fulfilled_count": act.get("fulfilled_count"),
            "gap": act.get("gap"),
            "rule_id": act.get("rule_id"),
            "rule_label": _rule_label(act.get("rule_id")),
            "status": status,
            "status_code": status_code,
            "execution_mode": "simulation_adapter",
        })

    return {
        "required": required,
        "trigger_reason": (
            "、".join(_rule_label(r) for r in sorted(triggered & {3, 5}))
            + " 已觸發，須一併提出跨系統請求"
        ) if required else "未觸發第 3 條或第 5 條，無強制跨系統請求",
        "requests": requests,
        "external_system_connected": False,
        "execution_disclaimer": "依本次事件動態產生並隨核准狀態更新；目前僅寫入模擬聯動 Adapter，尚未串接真實外部派令 API。",
        # 資源缺口需指揮官裁示抽調，於建議書中一併列示
        "resource_gaps": (state.get("dispatch") or {}).get("gaps") or [],
    }


def _with_segment_names(rec: dict, network: dict | None) -> dict:
    """把路段 ID 補上名稱——建議書是給人看的，只有 RD_ 代號無法閱讀。"""
    if not network:
        return rec
    for g in rec["grading"]["graded_segments"]:
        seg = network.get(g["segment_id"])
        if seg is not None:
            g["name"] = seg.name
    return rec


def build_recommendation(state: dict, network: dict | None = None) -> dict:
    """把事件處理結果重組為建議書五項內容。

    僅重組既有結果，不重新判定；欄位為空即代表該事件確實未觸發相關規則。
    """
    return _with_segment_names({
        "incident_id": state.get("incident_id"),
        "generated_from": {
            "workflow_status": state.get("workflow_status"),
            "as_of": state.get("as_of"),
            "decision_trace_steps": len(state.get("decision_trace") or []),
        },
        # 覆寫假設值（如漫遊率）須隨建議書一併揭露，避免與實際資料混淆
        "assumptions": state.get("assumptions") or [],
        "identification": _identification(state),
        "grading": _grading(state),
        "routing": _routing(state),
        "signal_plan": _signal_plan(state),
        "interagency": _interagency(state),
        "note": (
            "本建議書由決策引擎輸出重組產生，未經 LLM 改寫；"
            "各項數值可於「紀錄與驗證」頁比對決策鏈與資料佐證。"
        ),
    }, network)
