"""FastAPI 入口（技術文件第 16 節 API 規格）。

啟動：uvicorn app.api.main:app --reload --port 8000（於 backend/ 目錄）
"""
from __future__ import annotations

import re
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from ..coordinator.coordinator import Coordinator, DataBundle
from ..coordinator.whatif import run_what_if
from ..coordinator.whatif_nl import parse_question
from ..llm import advisor, generator
from ..llm.agent import AdvisorAgent
from ..llm.client import CALL_LOG, get_provider
from ..simulation.player import SimulationPlayer

app = FastAPI(title="城市應變分析 AI Command Center", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Demo 用；正式部署請鎖來源
    allow_methods=["*"],
    allow_headers=["*"],
)

bundle = DataBundle()
coordinator = Coordinator(bundle)
player = SimulationPlayer(bundle)
advisor_agent = AdvisorAgent(bundle, coordinator, player)


class SimulationStartRequest(BaseModel):
    speed: int = 1
    start_timestamp: str | None = None


class SimulationSeekRequest(BaseModel):
    timestamp: str


class IncidentInjectRequest(BaseModel):
    event_id: str
    at: str | None = None  # 預設用事件自身 timestamp


class WhatIfRequest(BaseModel):
    at: str
    crowd_overrides: dict[str, dict] | None = None
    traffic_overrides: dict[str, dict] | None = None
    simulated_incident: dict | None = None


# ---- 基礎資料 ----

@app.get("/api/health")
def health():
    return {"status": "ok", "segments": len(bundle.network), "incidents": list(bundle.incidents)}


@app.get("/api/resources")
def resources():
    return [r.as_dict() for r in bundle.registry.list()]


@app.post("/api/resources/reset")
def reset_resources():
    bundle.registry.reset()
    coordinator._incident_allocations.clear()
    return {"status": "reset", "resources": [r.as_dict() for r in bundle.registry.list()]}


@app.get("/api/road-network")
def road_network():
    return [seg.__dict__ | {"intersections": list(seg.intersections),
                            "alternatives": list(seg.alternatives),
                            "nearby_stations": list(seg.nearby_stations)}
            for seg in bundle.network.values()]


@app.get("/api/sop")
def sop_rules():
    return list(bundle.sop.rules.values())


# ---- 16.1–16.2 時序播放 ----

@app.post("/api/simulation/start")
def simulation_start(req: SimulationStartRequest):
    return player.start(speed=req.speed, start_timestamp=req.start_timestamp)


@app.post("/api/simulation/pause")
def simulation_pause():
    return player.pause()


@app.post("/api/simulation/seek")
def simulation_seek(req: SimulationSeekRequest):
    return player.seek(req.timestamp)


@app.post("/api/simulation/tick")
def simulation_tick():
    return player.tick()


@app.get("/api/simulation/state")
def simulation_state():
    return player.current_view()


@app.get("/api/simulation/alerts")
def simulation_alerts():
    return player.alert_log


@app.get("/api/simulation/timeline")
def simulation_timeline():
    """時間軸：所有資料時間點 + 重要事件 marker（供時間條拖曳回放）。"""
    from ..data_loader import format_ts, traffic_snapshot
    from ..engines.rule_engine import classify_congestion

    stamps = player.timestamps
    incident_ts = {i["timestamp"]: i["event_id"] for i in bundle.incidents.values()}
    markers = []
    for i, ts in enumerate(stamps):
        label = format_ts(ts)
        kind = None
        if label in incident_ts:
            kind = "incident"
        else:
            snap = traffic_snapshot(bundle.traffic, ts)
            if any(classify_congestion(r.saturation_score) == "A" for r in snap.values()):
                kind = "critical"
        markers.append({"index": i, "time": label, "kind": kind})
    return {"timestamps": [format_ts(t) for t in stamps], "markers": markers}


# ---- 16.3–16.4 事件注入 ----

@app.post("/api/incidents/inject")
def inject_incident(req: IncidentInjectRequest):
    from ..data_loader import parse_ts

    try:
        at = parse_ts(req.at) if req.at else None
        return coordinator.inject_incident(req.event_id, at=at)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/incidents")
def list_incidents():
    return {
        "available": list(bundle.incidents.values()),
        "processed": list(coordinator.incident_states),
    }


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return state


# ---- 16.5 What-if ----

@app.post("/api/what-if")
def what_if(req: WhatIfRequest):
    return run_what_if(bundle, req.model_dump(exclude_none=True))


class WhatIfNLRequest(BaseModel):
    question: str


@app.post("/api/what-if/nl")
def what_if_nl(req: WhatIfNLRequest):
    """自然語言 What-if：regex 確定性解析優先；解析不了才用 LLM（含 guardrail），
    兩者輸出同一 scenario 格式、走同一套 Sandbox 引擎。"""
    parsed_by = "regex"
    try:
        scenario = parse_question(req.question)
    except ValueError as exc:
        scenario = advisor.parse_what_if_with_llm(
            req.question,
            station_ids=sorted({r.bs_id for r in bundle.crowd}),
            segment_ids=list(bundle.network),
        )
        if scenario is None:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        parsed_by = f"llm:{get_provider()[0]}"
    result = run_what_if(bundle, scenario)
    result["parsed_from"] = req.question
    result["parsed_by"] = parsed_by
    return result


# ---- 通報生命週期（生成 ≠ 送達；發布須人工核准） ----

@app.get("/api/notifications")
def list_notifications():
    return bundle.notification_center.list()


@app.post("/api/notifications/{notification_id}/{op}")
def notification_op(notification_id: str, op: Literal["approve", "dispatch", "retry"]):
    center = bundle.notification_center
    try:
        if op == "approve":
            return center.approve(notification_id)
        if op == "dispatch":
            return center.dispatch(notification_id)
        return center.retry(notification_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---- 自訂事件模擬器（schema 驗證後才注入） ----

class CustomIncidentRequest(BaseModel):
    type: str = Field(min_length=2, max_length=64)
    affected_segment: str
    status: Literal["Closed", "Blocked", "Restricted", "Caution"]
    severity: Literal["Critical", "High", "Medium", "Low"]
    location: str = ""
    description: str = ""
    timestamp: str = Field(pattern=r"^2026-05-20 ([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("affected_segment")
    @classmethod
    def _segment_prefix(cls, v: str) -> str:
        if not re.match(r"^(RD|BS)_[A-Z0-9_]+$", v):
            raise ValueError("affected_segment 須為 RD_ 或 BS_ 開頭的合法 ID")
        return v


simulation_runs: list[dict] = []


@app.post("/api/incidents/custom")
def inject_custom_incident(req: CustomIncidentRequest):
    """自訂事件注入：schema 驗證 → 實體存在性檢查 → 走同一套 Coordinator。"""
    known_stations = {r.bs_id for r in bundle.crowd}
    if req.affected_segment.startswith("RD_") and req.affected_segment not in bundle.network:
        raise HTTPException(status_code=422, detail=f"路段 {req.affected_segment} 不存在於路網")
    if req.affected_segment.startswith("BS_") and req.affected_segment not in known_stations:
        raise HTTPException(status_code=422, detail=f"基地台 {req.affected_segment} 不存在")

    run_id = f"SIMRUN-{len(simulation_runs) + 1:03d}"
    incident = {"event_id": f"CUSTOM_{run_id}", **req.model_dump()}
    state = coordinator.process_incident(incident)
    simulation_runs.append({
        "simulation_run_id": run_id,
        "event_payload": incident,
        "incident_id": state["incident_id"],
        "triggered_rules": state["triggered_rules"],
        "workflow_status": state["workflow_status"],
        "created_at": state["started_at"],
    })
    state["simulation_run_id"] = run_id
    return state


@app.get("/api/simulation-runs")
def list_simulation_runs():
    return simulation_runs


# ---- AI 摘要（LLM 解釋已驗證的決策；失敗走模板） ----

@app.post("/api/incidents/{incident_id}/ai-summary")
def ai_summary(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    summary = advisor.generate_decision_summary(state)
    state["ai_summary"] = summary
    return summary


@app.get("/api/llm/status")
def llm_status():
    provider, _ = get_provider()
    return {"provider": provider, "available": provider is not None}


# ---- 預警摘要（官方：彈窗摘要由 LLM 生成；快取避免重複呼叫） ----

class AlertSummaryRequest(BaseModel):
    rule_id: int
    entity_id: str
    sim_time: str | None = None
    evidence: dict = {}
    actions: list[str] = []


_alert_summary_cache: dict[str, dict] = {}


@app.post("/api/alerts/summary")
def alert_summary(req: AlertSummaryRequest):
    key = f"{req.rule_id}|{req.entity_id}|{req.sim_time}"
    if key not in _alert_summary_cache:
        _alert_summary_cache[key] = generator.generate_alert_summary(req.model_dump())
    return _alert_summary_cache[key]


# ---- 顧問對話（三層路由：What-if → SOP 查詢 → LLM 問答） ----

class AdvisorChatRequest(BaseModel):
    question: str
    history: list[dict] = []


def _latest_incident_context() -> str:
    states = list(coordinator.incident_states.values())
    if not states:
        return ""
    st = states[-1]
    lines = [
        f"事件 {st['incident_id']}｜{st['event'].get('type')}｜{st['event'].get('location')}",
        f"觸發 SOP：{st['triggered_rules']}",
    ]
    if st.get("routing_result") and st["routing_result"].get("primary_route"):
        lines.append(f"主疏散：{st['routing_result']['primary_route']['name']}")
    if st.get("ete_result"):
        lines.append(f"ETE：{st['ete_result']['formula']}")
    if st.get("confidence"):
        lines.append(f"事件可信度：{st['confidence']['confidence_score']}（{st['confidence']['level']}）")
    return "\n".join(lines)


@app.post("/api/advisor/chat")
def advisor_chat(req: AdvisorChatRequest):
    q = req.question.strip()

    # 主路徑：tool-calling agent——LLM 自主決定呼叫哪些唯讀工具後回答。
    # LLM 不可用或 agent 失敗時，退回下方確定性路由（Demo 永不死）。
    try:
        agent_result = advisor_agent.run(q, req.history)
        if agent_result.get("available"):
            return {"kind": "agent", **{k: v for k, v in agent_result.items() if k != "available"}}
    except Exception:  # noqa: BLE001 - agent 任何失敗都走確定性 fallback
        pass

    # ---- 以下為確定性 fallback 路由 ----
    # 第一層：What-if 假設分析（regex → LLM 解析，同一套 sandbox）
    scenario = None
    parsed_by = None
    try:
        scenario = parse_question(q)
        parsed_by = "regex"
    except ValueError:
        if re.search(r"如果|假設|會怎樣|what.?if", q, re.IGNORECASE):
            scenario = advisor.parse_what_if_with_llm(
                q,
                station_ids=sorted({r.bs_id for r in bundle.crowd}),
                segment_ids=list(bundle.network),
            )
            if scenario:
                parsed_by = f"llm:{get_provider()[0]}"
    if scenario:
        result = run_what_if(bundle, scenario)
        new_rules = result["diff"]["newly_triggered_rules"]
        answer = (
            f"已在 Sandbox 執行假設分析（{result['as_of']} 時間切面，正式狀態未修改）。"
            + (f"假設成立後將新觸發 SOP {'、'.join(map(str, new_rules))}。"
               if new_rules else "假設成立後不會新觸發任何 SOP 條款。")
        )
        return {"kind": "whatif", "answer": answer, "parsed_by": parsed_by,
                "whatif_result": result, "cited_rule_ids": result["sandbox"]["triggered_rules"]}

    # 第二層：SOP 條款直接查詢（確定性）
    m = re.search(r"(?:SOP|規則|第)\s*([1-7])\s*(?:條|$|[^0-9])", q, re.IGNORECASE)
    if m and re.search(r"SOP|規則|條款|第.*條|內容|是什麼|規定", q, re.IGNORECASE):
        rule = bundle.sop.get(int(m.group(1)))
        return {"kind": "sop", "answer": f"第 {rule['rule_id']} 條「{rule['title']}」：\n{rule['text']}",
                "cited_rule_ids": [rule["rule_id"]]}

    # 第三層：LLM 問答（guardrail：只引用 SOP 1-7；失敗走能力說明）
    llm_answer = advisor.answer_question(q, bundle.sop.rules, _latest_incident_context())
    if llm_answer:
        return {"kind": "chat", **llm_answer}
    return {
        "kind": "help",
        "answer": "我可以協助：(1) What-if 假設分析，例如「如果 BL17 人數增加到 40000 人會怎樣？」"
                  "(2) SOP 條款查詢，例如「SOP 2 的內容是什麼」"
                  "(3) 當前事件諮詢（需 LLM 可用）。",
        "cited_rule_ids": [],
    }


# ---- 信心分數與資料佐證（可驗證性） ----

@app.get("/api/confidence")
def confidence_list():
    return [
        {"incident_id": st["incident_id"], "as_of": st["as_of"],
         "event_type": st["event"].get("type"), **st["confidence"]}
        for st in coordinator.incident_states.values()
        if st.get("confidence")
    ]


@app.get("/api/provenance")
def provenance():
    """資料佐證：來源檔 SHA256、筆數、引擎門檻——讓評審可重算每個數字。"""
    import hashlib

    from ..config import ROAD_NETWORK_JSON
    from ..engines import confidence as ce
    from ..engines import ete_calculator as ete
    from ..engines import routing_engine as re_

    road_hash = hashlib.sha256(ROAD_NETWORK_JSON.read_bytes()).hexdigest()
    return {
        "data_sources": [
            {"file": "road_network_geometry.json", "records": len(bundle.network),
             "sha256": road_hash, "note": "authoritative（官方命題資料夾版）"},
            {"file": "city_traffic_flow.csv", "records": len(bundle.traffic)},
            {"file": "signaling_crowd_density.csv", "records": len(bundle.crowd)},
            {"file": "emergency_traffic_sop.txt", "records": len(bundle.sop.rules)},
            {"file": "live_incidents.json", "records": len(bundle.incidents)},
        ],
        "engine_constants": {
            "壅塞分級": {"B級": 0.85, "A級": 0.95},
            "Routing": {"最低容量_vph": re_.MIN_CAPACITY_VPH, "壅塞維持門檻": re_.CONGESTED_THRESHOLD},
            "ETE": {"base_clearance": ete.BASE_CLEARANCE, "懲罰基準": ete.PENALTY_BASELINE,
                    "懲罰係數": ete.PENALTY_FACTOR},
            "信心分數": {"車速崩跌_kmh": ce.SPEED_COLLAPSE_KMH,
                        "人流異常成長率": ce.CROWD_ANOMALY_GROWTH},
        },
        "note": "所有判定與計算皆由確定性引擎執行，可依上述門檻與原始資料重算驗證。",
    }


# ---- 系統紀錄（統一 log）與歷史趨勢 ----

def _norm_ts(value: str) -> str:
    """把 ISO（含 T）與一般格式統一為 'YYYY-MM-DD HH:MM:SS' 以利排序。"""
    return value.replace("T", " ")[:19]


@app.get("/api/logs")
def system_logs():
    """統一系統紀錄：監測預警、事件處理、人工覆寫、通報歷程、模擬紀錄。

    以「真實系統時間」排序（新到舊）；監測預警另附模擬時間。
    """
    entries: list[dict] = []

    for a in player.alert_log:
        entries.append({
            "at": a.get("logged_at", a["sim_time"]),
            "sim_time": a["sim_time"],
            "category": "監測預警",
            "title": f"SOP {a['rule_id']}｜{a['entity_id']}",
            "detail": "；".join(a["actions"]),
        })

    for st in coordinator.incident_states.values():
        entries.append({
            "at": _norm_ts(st["started_at"]),
            "sim_time": st.get("as_of"),
            "category": "事件處理",
            "title": f"{st['incident_id']}｜{st['workflow_status']}",
            "detail": f"觸發 SOP {st['triggered_rules']}"
                      + (f"｜ETE {st['ete_result']['ete_minutes_display']} 分" if st.get("ete_result") else ""),
        })
        for t in st["decision_trace"]:
            if t["step"] == "HUMAN_OVERRIDE":
                d = t["detail"]
                entries.append({
                    "at": _norm_ts(t["at"]),
                    "sim_time": None,
                    "category": "人工覆寫",
                    "title": f"{st['incident_id']}｜{d.get('action_id')}｜{d.get('op')}",
                    "detail": f"{d.get('override_by')}：{d.get('override_reason') or '（未填理由）'}",
                })
            elif t["step"] == "DISPATCH_PREEMPTED":
                d = t["detail"]
                entries.append({
                    "at": _norm_ts(t["at"]),
                    "sim_time": None,
                    "category": "人工覆寫",
                    "title": f"{st['incident_id']}｜{d.get('action_id')}｜遭抽調",
                    "detail": f"被 {d.get('pulled_by')} 抽調 {d.get('count')} 單位（{d.get('operator')} 核准）",
                })
            elif t["step"] == "RESOURCE_REBALANCED":
                d = t["detail"]
                entries.append({
                    "at": _norm_ts(t["at"]),
                    "sim_time": None,
                    "category": "事件處理",
                    "title": f"{st['incident_id']}｜{d.get('action_id')}｜資源回填",
                    "detail": f"回填 {d.get('refilled')} 單位，剩餘缺口 {d.get('remaining_gap')}",
                })

    for n in bundle.notification_center.list():
        for h in n["history"]:
            entries.append({
                "at": h["at"],
                "sim_time": None,
                "category": "通報",
                "title": f"{n['notification_id']} → {h['status']}",
                "detail": h["note"],
            })

    for r in simulation_runs:
        entries.append({
            "at": _norm_ts(r["created_at"]),
            "sim_time": None,
            "category": "模擬",
            "title": f"{r['simulation_run_id']}｜{r['event_payload']['type']}",
            "detail": f"{r['event_payload']['affected_segment']}｜觸發 SOP {r['triggered_rules']}",
        })

    # LLM 呼叫留痕（稽核：哪次生成用了 LLM、延遲、成敗）
    for c in CALL_LOG:
        entries.append({
            "at": c["at"],
            "sim_time": None,
            "category": "LLM",
            "title": f"{c['purpose']}｜{c['provider']}/{c['model']}｜{'成功' if c['ok'] else '失敗'}",
            "detail": f"延遲 {c['latency_ms']} ms" + (f"｜{c['note']}" if c.get("note") else ""),
        })

    entries.sort(key=lambda e: e["at"], reverse=True)
    return entries


@app.get("/api/history")
def history(until: str | None = None):
    """趨勢資料：各路段飽和度、各場站人數/漫遊率時序（供監測頁圖表）。"""
    from ..data_loader import format_ts, parse_ts

    limit = parse_ts(until) if until else None
    traffic: dict[str, dict] = {}
    for rec in bundle.traffic:
        if limit and rec.timestamp > limit:
            continue
        traffic.setdefault(rec.segment_id, {"name": rec.road_name, "points": []})
        traffic[rec.segment_id]["points"].append(
            {"t": format_ts(rec.timestamp), "sat": rec.saturation_score, "speed": rec.avg_speed}
        )
    crowd: dict[str, dict] = {}
    for rec in bundle.crowd:
        if limit and rec.timestamp > limit:
            continue
        crowd.setdefault(rec.bs_id, {"name": rec.location_name, "points": []})
        crowd[rec.bs_id]["points"].append(
            {"t": format_ts(rec.timestamp), "users": rec.user_count, "roaming": rec.roaming_user_pct}
        )
    return {"traffic": traffic, "crowd": crowd}


# ---- 16.6–16.7 決策鏈與通報 ----

@app.get("/api/incidents/{incident_id}/decision-trace")
def decision_trace(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return {
        "incident_id": incident_id,
        "triggered_rules": state["triggered_rules"],
        "rule_attribution": state.get("rule_attribution", {}),
        "trigger_details": state.get("trigger_details", []),
        "routing_result": state["routing_result"],
        "ete_result": state["ete_result"],
        "dispatch": state.get("dispatch"),
        "sop_evidence": state["sop_evidence"],
        "decision_trace": state["decision_trace"],
    }


@app.get("/api/incidents/{incident_id}/notifications")
def incident_notifications(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return state["notifications"]


class DispatchActionRequest(BaseModel):
    op: str  # accept / reject / adjust / preempt
    count: int | None = None
    reason: str = ""
    operator: str = "commander"
    source_incident_id: str | None = None  # preempt 用：抽調來源
    source_action_id: str | None = None


@app.get("/api/incidents/{incident_id}/dispatch")
def incident_dispatch(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return state.get("dispatch") or {"actions": [], "gaps": [], "has_shortfall": False}


@app.post("/api/incidents/{incident_id}/dispatch/{action_id}")
def dispatch_action(incident_id: str, action_id: str, req: DispatchActionRequest):
    """管理者 Challenge 操作：接受 / 拒絕 / 調整 / 優先權抽調。"""
    try:
        if req.op == "preempt":
            if not (req.source_incident_id and req.source_action_id and req.count):
                raise ValueError("preempt 需提供 source_incident_id、source_action_id、count")
            state = coordinator.preempt(
                incident_id, action_id,
                req.source_incident_id, req.source_action_id, req.count,
                reason=req.reason, operator=req.operator,
            )
        else:
            state = coordinator.dispatch_action(
                incident_id, action_id, req.op,
                count=req.count, reason=req.reason, operator=req.operator,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return state["dispatch"]
