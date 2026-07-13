"""Workflow Coordinator：事件驅動的應變工作流。

狀態機：NEW → VALIDATED → RULE_EVALUATED → ROUTE_PLANNED → ETE_CALCULATED
        → SOP_RETRIEVED → CONTENT_GENERATED → PUBLISHED → COMPLETED
每一步都寫入 decision trace，供 Dashboard 決策鏈展示。

Coordinator 不自己猜路徑、不自己算 ETE、不自己決定 SOP 門檻——
一律呼叫確定性引擎。
"""
from __future__ import annotations

from datetime import datetime

from .. import notifications
from ..data_loader import (
    crowd_snapshot,
    format_ts,
    load_crowd,
    load_incidents,
    load_road_network,
    load_traffic,
    parse_ts,
    traffic_snapshot,
)
from ..engines import ete_calculator, routing_engine, rule_engine
from ..retrievers.sop_retriever import SOPRetriever


class DataBundle:
    """一次載入全部主辦資料，供各引擎共用。"""

    def __init__(self):
        self.network = load_road_network()
        self.traffic = load_traffic()
        self.crowd = load_crowd()
        self.incidents = {i["event_id"]: i for i in load_incidents()}
        self.sop = SOPRetriever()

    def traffic_at(self, at: datetime):
        return traffic_snapshot(self.traffic, at)

    def crowd_at(self, at: datetime):
        return crowd_snapshot(self.crowd, at)


class Coordinator:
    def __init__(self, bundle: DataBundle | None = None):
        self.bundle = bundle or DataBundle()
        self.incident_states: dict[str, dict] = {}

    # ---- 對外入口 ----

    def inject_incident(self, event_id: str, at: datetime | None = None) -> dict:
        incident = self.bundle.incidents.get(event_id)
        if incident is None:
            raise KeyError(f"未知的事件 ID: {event_id}")
        return self.process_incident(incident, at=at)

    def process_incident(self, incident: dict, at: datetime | None = None) -> dict:
        at = at or parse_ts(incident["timestamp"])
        trace: list[dict] = []
        state = {
            "incident_id": incident.get("event_id", "ADHOC"),
            "workflow_status": "processing",
            "current_step": "NEW",
            "event": incident,
            "as_of": format_ts(at),
            "triggered_rules": [],
            "routing_result": None,
            "ete_result": None,
            "sop_evidence": [],
            "notifications": {},
            "decision_trace": trace,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "completed_at": None,
            "errors": [],
        }

        def step(name: str, detail):
            state["current_step"] = name
            trace.append({"step": name, "at": datetime.now().isoformat(timespec="milliseconds"), "detail": detail})

        try:
            # VALIDATED
            missing = [k for k in ("event_id", "type", "status", "severity", "timestamp") if not incident.get(k)]
            if missing:
                raise ValueError(f"事件缺少必要欄位: {missing}")
            step("VALIDATED", {"checked_fields": "ok"})

            traffic_snap = self.bundle.traffic_at(at)
            crowd_snap = self.bundle.crowd_at(at)

            # RULE_EVALUATED：事件規則 + 當下人流規則（同一時間切面）
            incident_triggers = rule_engine.evaluate_incident(incident)
            crowd_triggers = rule_engine.evaluate_crowd(crowd_snap, self.bundle.crowd, at)
            triggers = incident_triggers + crowd_triggers
            state["triggered_rules"] = sorted({t["rule_id"] for t in triggers})
            state["trigger_details"] = triggers
            step("RULE_EVALUATED", {"triggered_rules": state["triggered_rules"]})

            # ROUTE_PLANNED（SOP 2 觸發才需要）
            rule2 = next((t for t in incident_triggers if t["rule_id"] == 2), None)
            if rule2 is not None:
                routing = routing_engine.plan_evacuation(
                    incident["affected_segment"],
                    self.bundle.network,
                    traffic_snap,
                    incident.get("location"),
                )
                state["routing_result"] = routing
                step("ROUTE_PLANNED", {
                    "primary": routing["primary_route"]["segment_id"] if routing["primary_route"] else None,
                    "excluded": [(e["segment_id"], e["reason_code"]) for e in routing["excluded_routes"]],
                })
            else:
                step("ROUTE_PLANNED", {"skipped": "未觸發 SOP 第 2 條，無需路徑重規劃"})

            # ETE_CALCULATED：受影響「路段」才有 ETE（BS_ 事件用 affected_road）
            road_id = None
            seg = incident.get("affected_segment", "")
            if seg.startswith("RD_"):
                road_id = seg
            elif incident.get("affected_road", "").startswith("RD_"):
                road_id = incident["affected_road"]
            if road_id and incident["severity"] in ete_calculator.BASE_CLEARANCE:
                rec = traffic_snap.get(road_id)
                if rec is not None:
                    ete = ete_calculator.calculate_ete(incident["severity"], [rec.saturation_score])
                    ete["affected_segments"] = [road_id]
                    state["ete_result"] = ete
                    step("ETE_CALCULATED", {"ete_minutes": ete["ete_minutes"], "formula": ete["formula"]})
                else:
                    step("ETE_CALCULATED", {"skipped": f"{road_id} 在 {format_ts(at)} 尚無車流資料"})
            else:
                step("ETE_CALCULATED", {"skipped": "非路段事件或 severity 不在 ETE 對照表"})

            # SOP_RETRIEVED
            state["sop_evidence"] = self.bundle.sop.retrieve(state["triggered_rules"] + [7] if state["ete_result"] else state["triggered_rules"])
            step("SOP_RETRIEVED", {"rule_ids": [r["rule_id"] for r in state["sop_evidence"]]})

            # CONTENT_GENERATED
            state["notifications"] = self._generate_notifications(state, incident, at, crowd_triggers)
            step("CONTENT_GENERATED", {"channels": list(state["notifications"].keys())})

            # PUBLISHED（Demo 內為推送 Dashboard；實際發布須人工確認）
            step("PUBLISHED", {"note": "結果已可供 Dashboard 讀取；對外發布需人工確認"})

            state["workflow_status"] = "completed"
            state["current_step"] = "COMPLETED"
            state["completed_at"] = datetime.now().isoformat(timespec="seconds")
        except Exception as exc:  # noqa: BLE001 - 記錄後保留部分結果（fallback 原則）
            state["errors"].append(str(exc))
            state["workflow_status"] = "failed"
            step("FAILED_FINAL", {"error": str(exc)})

        self.incident_states[state["incident_id"]] = state
        return state

    # ---- 內部 ----

    def _generate_notifications(self, state, incident, at, crowd_triggers) -> dict:
        result: dict = {}
        affected_id = incident.get("affected_segment", "")
        if not affected_id.startswith("RD_"):
            affected_id = incident.get("affected_road", "")
        affected_seg = self.bundle.network.get(affected_id)
        affected_name = affected_seg.name if affected_seg else incident.get("location", "受影響區域")
        ete_display = state["ete_result"]["ete_minutes_display"] if state["ete_result"] else 0

        primary = (state.get("routing_result") or {}).get("primary_route")
        primary_name = primary["name"] if primary else None

        # CMS
        cms_lines = []
        if 2 in state["triggered_rules"]:
            cms_lines.append(notifications.cms_reroute_message(affected_name, primary_name, ete_display))
        if 5 in state["triggered_rules"]:
            cms_lines.append(notifications.cms_signal_failure_note(affected_name))
        if cms_lines:
            result["cms"] = " / ".join(cms_lines)

        # 多語（SOP 6：任一基地台漫遊率 >= 30% 時必做多語；否則仍附 zh/en）
        roaming_triggers = [t for t in crowd_triggers if t["rule_id"] == 6]
        msgs = notifications.multilingual_reroute(
            affected_name,
            notifications.ROAD_NAME_EN.get(affected_id, affected_name),
            primary_name,
            notifications.ROAD_NAME_EN.get(primary["segment_id"], primary_name) if primary else None,
            ete_display,
            at,
        )
        result["multilingual_required"] = bool(roaming_triggers)
        result["roaming_evidence"] = [t["evidence"] for t in roaming_triggers]
        result["messages"] = msgs if roaming_triggers else {k: msgs[k] for k in ("zh", "en")}
        return result
