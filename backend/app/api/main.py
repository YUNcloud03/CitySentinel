"""FastAPI 入口（技術文件第 16 節 API 規格）。

啟動：uvicorn app.api.main:app --reload --port 8000（於 backend/ 目錄）
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from ..coordinator.coordinator import Coordinator, DataBundle
from ..coordinator.green_corridor import corridor_state_at, simulate_green_corridor
from ..coordinator.whatif import run_what_if
from ..coordinator.decision_sandbox import run_decision_sandbox
from ..coordinator.recommendation import build_recommendation
from ..coordinator.whatif_nl import parse_question
from ..llm import advisor, generator
from ..llm.agent import AdvisorAgent
from ..llm.client import CALL_LOG, get_provider
from ..simulation.player import SimulationPlayer
from ..simulation.plan_comparison import build_plan_comparison, replay_plan_comparison
from ..engines.signal_timing import calculate_signal_plan
from ..audit import (
    confidence_contract,
    coordinator_contract,
    data_quality_report,
    dataset_usage_report,
    simulation_contract,
)

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
plan_comparison_runs: dict[str, dict] = {}


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


class DecisionSandboxRequest(BaseModel):
    name: str = "方案 A"
    at: str
    focus_segment_id: str
    actions: list[dict] = Field(default_factory=list)
    disruption: str = "none"
    disruption_segment_id: str | None = None
    disruption_load: float | None = None


class GreenCorridorRequest(BaseModel):
    at: str
    origin_segment_id: str
    destination_segment_id: str
    vehicle_type: Literal["Ambulance", "FireEngine"] = "Ambulance"
    blocked_segment_ids: list[str] = Field(default_factory=list)


class GreenCorridorApprovalRequest(BaseModel):
    approved_by: str = Field(default="指揮官", min_length=2, max_length=64)


class SignalTimingRequest(BaseModel):
    at: str
    segment_ids: list[str] = Field(min_length=2, max_length=4)


class ManualPlanControls(BaseModel):
    green_extension_pct: int = Field(default=0, ge=0, le=25)
    diversion_share: float = Field(default=0, ge=0, le=0.75)
    police_units: int = Field(default=0, ge=0, le=12)


class PlanComparisonRequest(BaseModel):
    incident_id: str = Field(min_length=1, max_length=128)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    manual_controls: ManualPlanControls | None = None


class PlanApprovalRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=32)
    approved_by: str = Field(default="指揮官", min_length=2, max_length=64)


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


@app.get("/api/crowd-stations")
def crowd_stations():
    """Return organizer station IDs and labels available to custom crowd events."""
    stations = {}
    for record in bundle.crowd:
        stations.setdefault(record.bs_id, record.location_name)
    return [
        {"station_id": station_id, "name": name}
        for station_id, name in sorted(stations.items())
    ]


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


@app.post("/api/simulation/reset")
def simulation_reset():
    """Start a new deterministic run from the organizer-data baseline.

    Resetting is intentionally broader than seeking: no incident, allocation,
    notification, corridor or prior simulation-run state may leak into the new run.
    """
    cleared = {
        "incidents": len(coordinator.incident_states),
        "notifications": len(bundle.notification_center.list()),
        "green_corridors": len(green_corridor_runs),
        "custom_runs": len(simulation_runs),
        "plan_comparison_runs": len(plan_comparison_runs),
        "llm_audit_entries": len(CALL_LOG),
    }
    coordinator.reset()
    green_corridor_runs.clear()
    simulation_runs.clear()
    plan_comparison_runs.clear()
    _alert_summary_cache.clear()
    CALL_LOG.clear()
    view = player.reset("2026-05-20 21:00")
    return {
        "status": "reset",
        "baseline_timestamp": view["sim_time"],
        "cleared": cleared,
        "view": view,
    }


@app.get("/api/simulation/comparison")
def simulation_comparison():
    """後端統一產生的基準／事件／處置比較證據，不允許前端自行推導。"""
    comparison = player.current_view().get("scenario_comparison")
    if comparison is None:
        raise HTTPException(status_code=409, detail="目前沒有可比較的進行中道路事件")
    return comparison


@app.post("/api/simulation/plan-comparison")
def create_plan_comparison(req: PlanComparisonRequest):
    """Build and persist deterministic constrained optimization evidence."""
    state = coordinator.incident_states.get(req.incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {req.incident_id} 尚未處理")
    try:
        config = {"random_seed": req.random_seed}
        if req.manual_controls is not None:
            config["manual_controls"] = req.manual_controls.model_dump()
        result = build_plan_comparison(bundle, state, config)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    plan_comparison_runs[result["simulation_run_id"]] = result
    return result


@app.get("/api/simulation/plan-comparison/{run_id}")
def get_plan_comparison(run_id: str):
    result = plan_comparison_runs.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"模擬 Run {run_id} 不存在")
    return result


@app.post("/api/simulation/plan-comparison/{run_id}/replay")
def replay_saved_plan_comparison(run_id: str):
    stored = plan_comparison_runs.get(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"模擬 Run {run_id} 不存在")
    state = coordinator.incident_states.get(stored["scenario_id"])
    if state is None:
        raise HTTPException(status_code=409, detail="原始事件狀態已重設，無法重播")
    return replay_plan_comparison(bundle, stored, state)


@app.post("/api/simulation/plan-comparison/{run_id}/approve")
def approve_plan_comparison(run_id: str, req: PlanApprovalRequest):
    """Approve one feasible package and make it the active simulation controller."""
    from ..data_loader import format_ts, parse_ts
    stored = plan_comparison_runs.get(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"模擬 Run {run_id} 不存在")
    plan = next((row for row in stored["plans"] if row["plan_id"] == req.plan_id), None)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"方案 {req.plan_id} 不存在")
    if not plan.get("eligible") or not plan.get("controls"):
        raise HTTPException(status_code=409, detail="此方案未通過硬性限制，禁止核准")
    state = coordinator.incident_states.get(stored["scenario_id"])
    if state is None:
        raise HTTPException(status_code=409, detail="原始事件狀態已重設，無法核准")
    current_sim_time = player.current_view()["sim_time"]
    effective_sim_time = max(parse_ts(current_sim_time), datetime.fromisoformat(stored["started_at"]))
    approval = {
        "run_id": run_id,
        "plan_id": plan["plan_id"],
        "plan_name": plan["name"],
        "approved_by": req.approved_by,
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "approved_sim_time": format_ts(effective_sim_time),
        "controls": plan["controls"],
        "commands": plan["executable_commands"],
        "forecast_series": plan["forecast_series"],
        "score": plan["score"],
        "status": "ACTIVE_IN_SIMULATION",
    }
    state["approved_optimization"] = approval
    state.setdefault("decision_trace", []).append({
        "step": "OPTIMIZED_PLAN_APPROVED",
        "at": approval["approved_at"],
        "detail": approval,
    })
    stored["approval_status"] = "APPROVED_FOR_SIMULATION"
    stored["approved_plan"] = approval
    return {
        "simulation_run_id": run_id,
        "scenario_id": stored["scenario_id"],
        "approval_status": stored["approval_status"],
        "approved_plan": approval,
    }


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


@app.get("/api/audit/simulation")
def simulation_audit():
    """Dataset time contract, initialization policy, and deterministic replay hash."""
    return simulation_contract(bundle)


@app.get("/api/audit/dataset-usage")
def dataset_usage_audit():
    """Trace every organizer-provided file to the runtime features that consume it."""
    return {"datasets": dataset_usage_report()}


@app.get("/api/audit/data-quality")
def data_quality_audit():
    """Machine-readable before/after counts and quality checks; no silent cleaning."""
    return data_quality_report(bundle)


@app.get("/api/audit/confidence")
def confidence_audit():
    return confidence_contract()


@app.get("/api/audit/coordinator")
def coordinator_audit():
    return coordinator_contract()


# ---- 16.3–16.4 事件注入 ----

@app.post("/api/incidents/inject")
def inject_incident(req: IncidentInjectRequest):
    from ..data_loader import parse_ts

    try:
        at = parse_ts(req.at) if req.at else None
        state = coordinator.inject_incident(req.event_id, at=at)
        player.activate_incident(state)
        return state
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
    try:
        return run_what_if(bundle, req.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/decision-sandbox")
def decision_sandbox(req: DecisionSandboxRequest):
    """Operator-controlled simulation. No LLM is used and production state is immutable."""
    try:
        return run_decision_sandbox(bundle, req.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/signal-timing/calculate")
def signal_timing(req: SignalTimingRequest):
    """Compute the next cycle from traceable road-level demand inputs."""
    from ..data_loader import parse_ts
    try:
        return calculate_signal_plan(bundle, parse_ts(req.at), req.segment_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/green-corridor/simulate")
def green_corridor(req: GreenCorridorRequest):
    """Build a deterministic emergency signal-preemption proposal.

    The result is simulation-only and always requires human approval before any
    real signal, dispatch, or public-notification operation.
    """
    try:
        scenario = req.model_dump()
        if player.active_incident_state:
            scenario["_incident_state"] = player.active_incident_state
        result = simulate_green_corridor(bundle, scenario)
        green_corridor_runs[result["scenario_id"]] = result
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


green_corridor_runs: dict[str, dict] = {}


@app.get("/api/green-corridor/runs")
def green_corridor_history():
    return list(green_corridor_runs.values())


@app.post("/api/green-corridor/{scenario_id}/approve")
def approve_green_corridor(scenario_id: str, req: GreenCorridorApprovalRequest):
    result = green_corridor_runs.get(scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"救援走廊 {scenario_id} 不存在")
    if result["approval_status"] == "APPROVED_FOR_SIMULATION":
        return result
    approved_at = datetime.now().isoformat(timespec="seconds")
    result["approval_status"] = "APPROVED_FOR_SIMULATION"
    result["approved_by"] = req.approved_by
    result["approved_at"] = approved_at
    result["runtime_state"] = corridor_state_at(result, 0, approved=True)
    result["decision_trace"].append({
        "step": "SIMULATION_ACTIVATED",
        "detail": {"approved_by": req.approved_by, "approved_at": approved_at},
    })
    return result


@app.get("/api/green-corridor/{scenario_id}/state")
def green_corridor_state(scenario_id: str, elapsed_seconds: int = 0):
    result = green_corridor_runs.get(scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"救援走廊 {scenario_id} 不存在")
    if elapsed_seconds < 0:
        raise HTTPException(status_code=422, detail="elapsed_seconds 不可小於 0")
    state = corridor_state_at(result, elapsed_seconds)
    result["runtime_state"] = state
    return state


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
    status: Literal["Closed", "Blocked", "Restricted", "Caution", "Crowded", "Surging", "Dispersing"]
    severity: Literal["Critical", "High", "Medium", "Low"]
    location: str = ""
    description: str = ""
    source_type: Literal["official", "operator", "iot", "camera", "citizen", "unknown"] = "operator"
    source_id: str = "dashboard-operator"
    human_confirmed: bool = True
    affected_direction: Literal["both", "northbound", "southbound", "eastbound", "westbound"] = "both"
    lanes_total: int = Field(default=2, ge=1, le=8)
    lanes_closed: int = Field(default=1, ge=0, le=8)
    review_interval_minutes: int = Field(default=15, ge=5, le=120)
    timestamp: str = Field(pattern=r"^2026-05-20 ([01]\d|2[0-3]):[0-5]\d$")
    # Demo 用漫遊率假設值；None＝沿用該時間切面的實際資料
    roaming_override_pct: float | None = Field(default=None, ge=0, le=100)
    crowd_user_count_override: int | None = Field(default=None, ge=0, le=200_000)
    crowd_growth_rate_override: float | None = Field(default=None, ge=-1, le=5)
    crowd_roaming_user_pct_override: float | None = Field(default=None, ge=0, le=100)
    crowd_stay_time_avg_override: float | None = Field(default=None, ge=0, le=600)

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
    if req.lanes_closed > req.lanes_total:
        raise HTTPException(status_code=422, detail="封閉車道數不可大於總車道數")
    is_crowd = req.type == "Crowd_Surge_Injury"
    if is_crowd and not req.affected_segment.startswith("BS_"):
        raise HTTPException(status_code=422, detail="人潮事件必須選擇 BS_ 站點")
    if not is_crowd and not req.affected_segment.startswith("RD_"):
        raise HTTPException(status_code=422, detail="道路事件必須選擇 RD_ 路段")

    run_id = f"SIMRUN-{len(simulation_runs) + 1:03d}"
    # 覆寫值是判定參數而非事件屬性，不併入 incident（否則會混進稽核用的事件內容）
    incident_payload = req.model_dump()
    roaming_override = incident_payload.pop("roaming_override_pct", None)
    crowd_overrides = {
        "user_count": incident_payload.pop("crowd_user_count_override", None),
        "growth_rate": incident_payload.pop("crowd_growth_rate_override", None),
        "roaming_user_pct": incident_payload.pop("crowd_roaming_user_pct_override", None),
        "stay_time_avg": incident_payload.pop("crowd_stay_time_avg_override", None),
    }
    if req.status == "Closed":
        incident_payload["lanes_closed"] = req.lanes_total
    incident = {"event_id": f"CUSTOM_{run_id}", **incident_payload}
    state = coordinator.process_incident(
        incident,
        roaming_override_pct=roaming_override,
        crowd_overrides=crowd_overrides if is_crowd else None,
    )
    player.activate_incident(state)
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


class IncidentResolveRequest(BaseModel):
    operator: str = Field(default="traffic_commander_01", min_length=2, max_length=64)
    reason: str = Field(min_length=4, max_length=500)


@app.post("/api/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str, req: IncidentResolveRequest):
    """Human-confirmed operational closure; time alone never resolves an incident."""
    simulation_time = player.current_view().get("sim_time")
    if not simulation_time:
        raise HTTPException(status_code=409, detail="模擬尚未開始，無法結案")
    try:
        return coordinator.resolve_incident(
            incident_id,
            operator=req.operator,
            reason=req.reason,
            simulation_time=simulation_time,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    from ..coordinator import green_corridor as gc
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
            "綠色救援走廊": {
                "一般號誌平均延誤秒": gc.BASE_SIGNAL_DELAY_SECONDS,
                "走廊號誌平均延誤秒": gc.CORRIDOR_SIGNAL_DELAY_SECONDS,
                "走廊最低速度_kmh": gc.MIN_CORRIDOR_SPEED_KMH,
                "走廊最高速度_kmh": gc.MAX_CORRIDOR_SPEED_KMH,
                "行人清空秒數": gc.PEDESTRIAN_CLEARANCE_SECONDS,
            },
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


@app.get("/api/incidents/{incident_id}/recommendation")
def incident_recommendation(incident_id: str):
    """交控中心建議書：重組既有處理結果為官方要求的五項內容（不重新判定）。"""
    state = coordinator.incident_states.get(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"事件 {incident_id} 尚未處理")
    return build_recommendation(state, bundle.network)


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
            simulation_time = player.current_view().get("sim_time")
            state = coordinator.dispatch_action(
                incident_id, action_id, req.op,
                count=req.count, reason=req.reason, operator=req.operator,
                simulation_time=simulation_time,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return state["dispatch"]
