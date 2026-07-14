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
from ..notifications_center import NotificationCenter
from ..resources import dispatch_engine
from ..resources.registry import ResourceRegistry
from ..retrievers.sop_retriever import SOPRetriever


class DataBundle:
    """一次載入全部主辦資料，供各引擎共用。"""

    def __init__(self):
        self.network = load_road_network()
        self.traffic = load_traffic()
        self.crowd = load_crowd()
        self.incidents = {i["event_id"]: i for i in load_incidents()}
        self.sop = SOPRetriever()
        self.registry = ResourceRegistry()
        self.notification_center = NotificationCenter()

    def traffic_at(self, at: datetime):
        return traffic_snapshot(self.traffic, at)

    def crowd_at(self, at: datetime):
        return crowd_snapshot(self.crowd, at)


class Coordinator:
    def __init__(self, bundle: DataBundle | None = None):
        self.bundle = bundle or DataBundle()
        self.incident_states: dict[str, dict] = {}
        # 記錄每個事件目前佔用的資源配置，供 re-inject / 拒絕時歸還
        self._incident_allocations: dict[str, list[dict]] = {}

    # ---- 對外入口 ----

    def inject_incident(self, event_id: str, at: datetime | None = None) -> dict:
        incident = self.bundle.incidents.get(event_id)
        if incident is None:
            raise KeyError(f"未知的事件 ID: {event_id}")
        return self.process_incident(incident, at=at)

    def process_incident(self, incident: dict, at: datetime | None = None) -> dict:
        at = at or parse_ts(incident["timestamp"])
        incident_id = incident.get("event_id", "ADHOC")
        # 重新注入同一事件：先歸還前次佔用的資源，避免庫存被重複扣減
        prior = self._incident_allocations.pop(incident_id, None)
        if prior:
            self.bundle.registry.release(prior)
        trace: list[dict] = []
        state = {
            "incident_id": incident_id,
            "workflow_status": "processing",
            "current_step": "NEW",
            "event": incident,
            "as_of": format_ts(at),
            "triggered_rules": [],
            "routing_result": None,
            "ete_result": None,
            "dispatch": None,
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

            # 規則歸因（修正 triggered/context 混淆）：
            #   caused_by_incident = 事件本身造成的規則（SOP2/5，及當事件就是該基地台時的 SOP3）
            #   context = 同一時間切面的環境監測規則，僅供情境參考，不驅動本事件的調度
            affected = incident.get("affected_segment", "")
            incident_rule_ids = {t["rule_id"] for t in incident_triggers}
            crowd_rules_for_incident = {
                t["rule_id"] for t in crowd_triggers if t["entity_id"] == affected
            }
            caused_by_incident = sorted(incident_rule_ids | crowd_rules_for_incident)
            context_rules = sorted(
                {t["rule_id"] for t in crowd_triggers} - crowd_rules_for_incident
            )
            state["rule_attribution"] = {
                "caused_by_incident": caused_by_incident,
                "context_rules": context_rules,
                "calculation_rules": [],  # ETE 觸發後補上 7
            }
            step("RULE_EVALUATED", {
                "caused_by_incident": caused_by_incident,
                "context_rules": context_rules,
            })

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
                    ete["saturation_source_segments"] = [road_id]  # 讓評審可重算
                    state["ete_result"] = ete
                    state["rule_attribution"]["calculation_rules"] = [7]
                    step("ETE_CALCULATED", {"ete_minutes": ete["ete_minutes"], "formula": ete["formula"]})
                else:
                    step("ETE_CALCULATED", {"skipped": f"{road_id} 在 {format_ts(at)} 尚無車流資料"})
            else:
                step("ETE_CALCULATED", {"skipped": "非路段事件或 severity 不在 ETE 對照表"})

            # DISPATCH_PLANNED：依「事件造成的規則」調度資源
            snapshot_id = f"SNAP-{at:%Y%m%d-%H%M}"
            requirements = dispatch_engine.build_requirements(
                incident,
                incident_rule_ids,
                crowd_rules_for_incident,
                state["routing_result"],
                self.bundle.network,
            )
            if requirements:
                dispatch = dispatch_engine.plan_dispatch(
                    self.bundle.registry, requirements, snapshot_id
                )
                state["dispatch"] = dispatch
                self._incident_allocations[incident_id] = [
                    a for act in dispatch["actions"] for a in act["assignments"]
                ]
                step("DISPATCH_PLANNED", {
                    "actions": len(dispatch["actions"]),
                    "has_shortfall": dispatch["has_shortfall"],
                    "gaps": dispatch["gaps"],
                })
            else:
                step("DISPATCH_PLANNED", {"skipped": "此事件無需資源調度"})

            # SOP_RETRIEVED
            state["sop_evidence"] = self.bundle.sop.retrieve(state["triggered_rules"] + [7] if state["ete_result"] else state["triggered_rules"])
            step("SOP_RETRIEVED", {"rule_ids": [r["rule_id"] for r in state["sop_evidence"]]})

            # CONTENT_GENERATED
            state["notifications"] = self._generate_notifications(state, incident, at, crowd_triggers)
            notification = self.bundle.notification_center.create_from_incident(state)
            state["notification_id"] = notification["notification_id"]
            step("CONTENT_GENERATED", {
                "channels": list(state["notifications"].keys()),
                "notification_id": notification["notification_id"],
            })

            # PUBLISHED：僅代表結果可供 Dashboard 讀取；
            # 對外推播進入 READY_FOR_APPROVAL，需人工核准後才 dispatch
            step("PUBLISHED", {
                "note": "Dashboard 已更新；對外通報待人工核准",
                "notification_status": notification["status"],
            })

            state["workflow_status"] = "completed"
            state["current_step"] = "COMPLETED"
            state["completed_at"] = datetime.now().isoformat(timespec="seconds")
        except Exception as exc:  # noqa: BLE001 - 記錄後保留部分結果（fallback 原則）
            state["errors"].append(str(exc))
            state["workflow_status"] = "failed"
            step("FAILED_FINAL", {"error": str(exc)})

        self.incident_states[state["incident_id"]] = state
        return state

    # ---- 人工指揮：接受 / 拒絕 / 調整調度動作 ----

    def dispatch_action(
        self,
        incident_id: str,
        action_id: str,
        op: str,
        count: int | None = None,
        reason: str = "",
        operator: str = "commander",
    ) -> dict:
        """管理者對單一調度動作的操作。保留原始 Agent 建議，覆寫寫入稽核。

        op：accept（接受）、reject（拒絕並歸還資源）、adjust（調整數量）
        """
        state = self.incident_states.get(incident_id)
        if state is None or not state.get("dispatch"):
            raise KeyError(f"事件 {incident_id} 無調度資料")
        action = next(
            (a for a in state["dispatch"]["actions"] if a["action_id"] == action_id), None
        )
        if action is None:
            raise KeyError(f"找不到調度動作 {action_id}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        override = {"override_by": operator, "override_reason": reason, "override_at": now, "op": op}

        if op == "accept":
            action["status"] = "accepted"
        elif op == "reject":
            self._release_action(incident_id, action)
            action["assignments"] = []
            action["fulfilled_count"] = 0
            action["status"] = "rejected"
        elif op == "adjust":
            if count is None:
                raise ValueError("adjust 需提供 count")
            # 保留原始建議數量（agent_recommended_count），僅調整實際派遣
            action.setdefault("agent_recommended_count", action["requested_count"])
            self._release_action(incident_id, action)
            assignments, gap = self.bundle.registry.allocate(action["resource_type"], count)
            action["assignments"] = assignments
            action["requested_count"] = count
            action["fulfilled_count"] = count - gap
            action["gap"] = gap
            action["status"] = "adjusted" if gap == 0 else "shortfall"
            self._incident_allocations.setdefault(incident_id, [])
            self._incident_allocations[incident_id].extend(assignments)
            override["adjusted_to"] = count
        else:
            raise ValueError(f"未知操作: {op}（須為 accept/reject/adjust）")

        action["override"] = override
        state["decision_trace"].append({
            "step": "HUMAN_OVERRIDE",
            "at": datetime.now().isoformat(timespec="milliseconds"),
            "detail": {"action_id": action_id, **override},
        })
        # 覆寫後重算缺口摘要
        state["dispatch"]["gaps"] = [
            {"action_id": a["action_id"], "resource_type": a["resource_type"],
             "gap": a["gap"], "purpose": a.get("action", "")}
            for a in state["dispatch"]["actions"] if a.get("gap", 0) > 0
            and a["status"] != "rejected"
        ]
        state["dispatch"]["has_shortfall"] = bool(state["dispatch"]["gaps"])
        return state

    def _release_action(self, incident_id: str, action: dict) -> None:
        """歸還單一動作佔用的資源，並從事件配置清單中移除。"""
        if not action.get("assignments"):
            return
        self.bundle.registry.release(action["assignments"])
        current = self._incident_allocations.get(incident_id, [])
        for a in action["assignments"]:
            if a in current:
                current.remove(a)

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
