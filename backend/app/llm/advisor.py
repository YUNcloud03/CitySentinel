"""Advisory Agent：LLM 只解釋已驗證的決策，不做任何判定。

LLM 可以：把決策鏈整理成交控摘要、解析 What-if 自然語言。
LLM 不可以：修改 SOP 門檻/ETE/Routing 結果、引用不存在的條款、
新增不存在的道路或場站、直接呼叫發布 API。

Guardrails：
    1. Structured Output（Pydantic schema）
    2. cited_rule_ids 必須是本事件已觸發/引用條款的子集，否則整包棄用走 fallback
    3. requires_human_approval 一律強制為 True
    4. LLM 逾時/失敗 → 確定性模板 fallback，主流程不中斷
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from . import client as llm_client

RULE_NAMES = {
    1: "交通擁塞級別判定", 2: "車禍與路障應變", 3: "捷運與接駁分流",
    4: "大巨蛋散場啟動", 5: "號誌故障應變", 6: "數位通報與多語化", 7: "ETE 計算",
}


class DecisionSummary(BaseModel):
    summary: str = Field(description="給交控中心指揮官的事件摘要，150 字內，繁體中文")
    cited_rule_ids: list[int] = Field(description="引用的 SOP 條款編號（純整數，如 2），只能來自提供的清單")
    recommended_actions: list[str] = Field(description="建議的處置行動，須對應已觸發規則")
    assumptions: list[str] = Field(default_factory=list, description="摘要依據的假設")
    requires_human_approval: bool = True

    @field_validator("cited_rule_ids", mode="before")
    @classmethod
    def _coerce_rule_ids(cls, v):
        """寬容解析：LLM 偶爾回 "SOP 2" 這類字串，抽出數字；抽不出的保留原值讓驗證失敗。"""
        if not isinstance(v, list):
            return v
        out = []
        for item in v:
            if isinstance(item, str):
                m = re.search(r"\d+", item)
                out.append(int(m.group()) if m else item)
            else:
                out.append(item)
        return out


_SUMMARY_SYSTEM = """你是交控中心的 AI 參謀。根據「已由確定性引擎計算完成」的決策資料，
為指揮官撰寫簡潔摘要。嚴格遵守：
1. 只能引用提供資料中出現的 SOP 條款編號，禁止自行新增條款。
2. 不可改寫任何數值（飽和度、ETE、人數、容量）。
3. 不可提出資料中不存在的道路、場站或資源。
4. 所有對外發布都需人工核准，requires_human_approval 必須為 true。
以繁體中文回答。"""


def _allowed_rules(state: dict) -> set[int]:
    attr = state.get("rule_attribution") or {}
    return set(state.get("triggered_rules", [])) | set(attr.get("calculation_rules", []))


def _build_context(state: dict) -> str:
    """把 incident state 壓縮成 LLM 輸入（只給已驗證的結果，不給原始權限）。"""
    lines = [
        f"事件：{state['incident_id']}｜{state['event'].get('type')}｜{state['event'].get('location')}",
        f"嚴重度：{state['event'].get('severity')}｜狀態：{state['event'].get('status')}",
        f"描述：{state['event'].get('description')}",
    ]
    attr = state.get("rule_attribution") or {}
    lines.append(f"事件觸發條款：{attr.get('caused_by_incident', state.get('triggered_rules', []))}")
    if attr.get("context_rules"):
        lines.append(f"情境參考條款（非本事件造成）：{attr['context_rules']}")
    if attr.get("calculation_rules"):
        lines.append(f"計算條款：{attr['calculation_rules']}")
    routing = state.get("routing_result")
    if routing and routing.get("primary_route"):
        p = routing["primary_route"]
        lines.append(f"主疏散：{p['name']}（容量 {p['capacity_vph']}，飽和 {p.get('saturation_score')}）")
        for s in routing.get("secondary_routes", []):
            lines.append(f"次要疏散：{s['name']}（{s.get('role_reason')}）")
        for e in routing.get("excluded_routes", []):
            lines.append(f"排除：{e.get('name', e['segment_id'])}：{e.get('detail')}")
    ete = state.get("ete_result")
    if ete:
        lines.append(f"ETE：{ete['formula']}")
    dispatch = state.get("dispatch")
    if dispatch:
        for a in dispatch.get("actions", []):
            lines.append(f"調度：{a['action']}（狀態 {a['status']}，缺口 {a.get('gap', 0)}）")
        if dispatch.get("has_shortfall"):
            lines.append("警告：存在資源缺口，需人工升級調度")
    return "\n".join(lines)


def _fallback_summary(state: dict) -> dict:
    """確定性模板摘要（LLM 不可用或 guardrail 擋下時）。"""
    attr = state.get("rule_attribution") or {}
    caused = attr.get("caused_by_incident", state.get("triggered_rules", []))
    ete = state.get("ete_result")
    routing = state.get("routing_result")
    parts = [
        f"{state['event'].get('location', state['incident_id'])}發生{state['event'].get('type', '事件')}"
        f"（{state['event'].get('severity')}），觸發 SOP {'、'.join(map(str, caused))}。"
    ]
    if routing and routing.get("primary_route"):
        parts.append(f"主疏散路徑為{routing['primary_route']['name']}。")
    if ete:
        parts.append(f"預計恢復時間 {ete['ete_minutes_display']} 分鐘。")
    dispatch = state.get("dispatch")
    if dispatch and dispatch.get("has_shortfall"):
        parts.append("注意：資源存在缺口，需人工升級調度。")
    actions = []
    for t in state.get("trigger_details", []):
        if t["rule_id"] in set(caused):
            actions.extend(t["actions"])
    return {
        "summary": "".join(parts),
        "cited_rule_ids": sorted(set(caused)),
        "recommended_actions": actions[:6],
        "assumptions": [],
        "requires_human_approval": True,
        "llm_generated": False,
        "provider": None,
    }


def generate_decision_summary(state: dict) -> dict:
    """交控摘要：LLM 生成 + guardrail 驗證；失敗走確定性模板。"""
    allowed = _allowed_rules(state)
    result = llm_client.structured_completion(
        _SUMMARY_SYSTEM,
        f"可引用的 SOP 條款編號：{sorted(allowed)}\n\n決策資料：\n{_build_context(state)}",
        DecisionSummary,
    )
    if result is None:
        return _fallback_summary(state)

    # Guardrail：引用條款必須是允許集合的子集，否則整包不可信
    if not set(result.cited_rule_ids) <= allowed:
        fallback = _fallback_summary(state)
        fallback["guardrail_rejected"] = (
            f"LLM 引用了未觸發的條款 {sorted(set(result.cited_rule_ids) - allowed)}，已改用模板"
        )
        return fallback

    provider, _ = llm_client.get_provider()
    return {
        **result.model_dump(),
        "requires_human_approval": True,  # 強制，不信任 LLM 輸出的值
        "llm_generated": True,
        "provider": provider,
    }


# ---- What-if 自然語言解析（LLM 版，regex 解析失敗時的第二層） ----

class WhatIfScenarioSchema(BaseModel):
    at: str = Field(description="時間切面，格式 YYYY-MM-DD HH:MM，日期固定 2026-05-20")
    crowd_overrides: dict[str, dict] | None = Field(
        default=None, description="基地台覆寫，key 為 BS_ 開頭 ID，值可含 user_count/growth_rate/roaming_user_pct"
    )
    traffic_overrides: dict[str, dict] | None = Field(
        default=None, description="路段覆寫，key 為 RD_ 開頭 ID，值可含 saturation_score"
    )
    simulated_incident: dict | None = Field(
        default=None, description="模擬事故（封路等），含 affected_segment/status/severity"
    )


_WHATIF_SYSTEM = """把使用者的 what-if 假設問題轉為結構化參數。嚴格遵守：
1. station/segment ID 只能使用提供清單中存在的 ID，禁止編造。
2. 沒有提到的欄位不要輸出。
3. 時間未指定時使用 2026-05-20 22:00。
4. 覆寫數值必須忠於問題原文，不可自行增減。"""


def parse_what_if_with_llm(question: str, station_ids: list[str], segment_ids: list[str]) -> dict | None:
    """LLM 解析 What-if；驗證 ID 存在性後回傳 scenario dict，失敗回 None。"""
    result = llm_client.structured_completion(
        _WHATIF_SYSTEM,
        f"可用基地台：{station_ids}\n可用路段：{segment_ids}\n\n問題：{question}",
        WhatIfScenarioSchema,
    )
    if result is None:
        return None
    scenario = result.model_dump(exclude_none=True)

    # Guardrail：ID 必須真實存在
    for bs_id in (scenario.get("crowd_overrides") or {}):
        if bs_id not in station_ids:
            return None
    for seg_id in (scenario.get("traffic_overrides") or {}):
        if seg_id not in segment_ids:
            return None
    sim = scenario.get("simulated_incident")
    if sim and sim.get("affected_segment") not in segment_ids:
        return None
    if not any(k in scenario for k in ("crowd_overrides", "traffic_overrides", "simulated_incident")):
        return None
    return scenario
