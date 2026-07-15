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
from ..llm import advisor
from ..llm.client import get_provider
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
    op: str  # accept / reject / adjust
    count: int | None = None
    reason: str = ""
    operator: str = "commander"


@app.get("/api/incidents/{incident_id}/dispatch")
def incident_dispatch(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return state.get("dispatch") or {"actions": [], "gaps": [], "has_shortfall": False}


@app.post("/api/incidents/{incident_id}/dispatch/{action_id}")
def dispatch_action(incident_id: str, action_id: str, req: DispatchActionRequest):
    """管理者 Challenge 操作：接受 / 拒絕 / 調整調度動作。"""
    try:
        state = coordinator.dispatch_action(
            incident_id, action_id, req.op,
            count=req.count, reason=req.reason, operator=req.operator,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return state["dispatch"]
