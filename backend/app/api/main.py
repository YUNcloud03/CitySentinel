"""FastAPI 入口（技術文件第 16 節 API 規格）。

啟動：uvicorn app.api.main:app --reload --port 8000（於 backend/ 目錄）
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..coordinator.coordinator import Coordinator, DataBundle
from ..coordinator.whatif import run_what_if
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


# ---- 16.6–16.7 決策鏈與通報 ----

@app.get("/api/incidents/{incident_id}/decision-trace")
def decision_trace(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return {
        "incident_id": incident_id,
        "triggered_rules": state["triggered_rules"],
        "trigger_details": state.get("trigger_details", []),
        "routing_result": state["routing_result"],
        "ete_result": state["ete_result"],
        "sop_evidence": state["sop_evidence"],
        "decision_trace": state["decision_trace"],
    }


@app.get("/api/incidents/{incident_id}/notifications")
def incident_notifications(incident_id: str):
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return state["notifications"]
