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
from ..engines import confidence as confidence_engine
from ..engines import ete_calculator, routing_engine, rule_engine
from ..notifications_center import NotificationCenter
from ..resources import dispatch_engine
from ..resources.registry import ResourceRegistry
from ..retrievers.sop_retriever import SOPRetriever


def build_coordinator_summary(state: dict) -> dict:
    """從已計算完成的事件狀態，組出「總司令一句話決策」。

    確定性：全部欄位取自引擎已算好的結果，不新增判斷、不改數值。
    四段：判定（可信度）、行動（疏散+調度）、升級條件、依據（SOP+ETE+佐證）。
    """
    conf = state.get("confidence") or {}
    attr = state.get("rule_attribution") or {}
    caused = attr.get("caused_by_incident", state.get("triggered_rules", []))
    routing = state.get("routing_result") or {}
    primary = routing.get("primary_route")
    ete = state.get("ete_result") or {}
    dispatch = state.get("dispatch") or {}
    event = state.get("event", {})

    verdict = (
        f"{event.get('type', '事件')}於{event.get('location', '受影響區域')}，"
        f"可信度{conf.get('level', '—')}"
        + (f"（{round(conf['confidence_score'] * 100)}%）" if conf.get("confidence_score") else "")
    )

    actions: list[str] = []
    if primary:
        note = "（已壅塞，併行大眾運輸）" if primary.get("congested") else ""
        actions.append(f"主疏散改道{primary['name']}{note}")
    police = next((a for a in dispatch.get("actions", []) if a["resource_type"] == "Police"), None)
    if police:
        actions.append(f"派遣 {police['fulfilled_count']} 名交通警力")
    if 3 in caused:
        actions.append("啟動捷運過站不停與接駁分流")
    if 5 in caused:
        actions.append("每路口配置警力人工指揮")
    if not actions:
        actions.append("維持局部監測")

    if dispatch.get("has_shortfall"):
        escalation = "資源存在缺口，需人工升級調度或跨區支援（不得標示為已達成）"
    elif 6 in state.get("triggered_rules", []):
        escalation = "區域漫遊率達門檻，已啟動全區多語推播"
    else:
        escalation = "若 5 分鐘內受影響路段飽和度未降至門檻以下，升級全區多語推播"

    basis_parts = [f"SOP {'、'.join(map(str, caused))}"] if caused else []
    if ete.get("ete_minutes_display"):
        basis_parts.append(f"ETE {ete['ete_minutes_display']} 分")
    if conf.get("evidence"):
        basis_parts.append(f"{len(conf['evidence'])} 項多源佐證")
    basis = "；".join(basis_parts) or "SOP Rule Engine 判定"

    return {"verdict": verdict, "actions": actions, "escalation": escalation, "basis": basis}


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

            # CONFIDENCE_ASSESSED：多源可信度（僅供參考，不參與判定）
            state["confidence"] = confidence_engine.assess_confidence(
                incident, traffic_snap, crowd_snap, self.bundle.network
            )
            step("CONFIDENCE_ASSESSED", {
                "score": state["confidence"]["confidence_score"],
                "level": state["confidence"]["level"],
                "signals": len(state["confidence"]["evidence"]),
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
                    self.bundle.registry, requirements, snapshot_id,
                    severity=incident.get("severity", "Medium"),
                )
                state["dispatch"] = dispatch
                self._incident_allocations[incident_id] = [
                    a for act in dispatch["actions"] for a in act["assignments"]
                ]
                # 缺口時掃描較低優先事件，提出可抽調來源（僅建議，須人工核准）
                self._attach_preemption_candidates(state)
                step("DISPATCH_PLANNED", {
                    "actions": len(dispatch["actions"]),
                    "severity": dispatch["severity"],
                    "has_shortfall": dispatch["has_shortfall"],
                    "gaps": dispatch["gaps"],
                    "preemption_proposals": sum(
                        len(a.get("preemption_candidates", [])) for a in dispatch["actions"]
                    ),
                })
            else:
                step("DISPATCH_PLANNED", {"skipped": "此事件無需資源調度"})

            # 重新注入釋出的資源可能可回填其他事件的缺口
            self._rebalance()

            # SOP_RETRIEVED
            state["sop_evidence"] = self.bundle.sop.retrieve(state["triggered_rules"] + [7] if state["ete_result"] else state["triggered_rules"])
            step("SOP_RETRIEVED", {"rule_ids": [r["rule_id"] for r in state["sop_evidence"]]})

            # CONTENT_GENERATED
            state["notifications"] = self._generate_notifications(state, incident, at, crowd_triggers)
            notification = self.bundle.notification_center.create_from_incident(state)
            state["notification_id"] = notification["notification_id"]
            step("CONTENT_GENERATED", {
                "notification_id": notification["notification_id"],
                "cms_source": (state["notifications"].get("cms_meta") or {}).get("source"),
                "messages_source": (state["notifications"].get("messages_meta") or {}).get("source"),
                "guardrail": [
                    m["guardrail_rejected"]
                    for m in (state["notifications"].get("cms_meta"),
                              state["notifications"].get("messages_meta"))
                    if m and m.get("guardrail_rejected")
                ] or None,
            })

            # PUBLISHED：僅代表結果可供 Dashboard 讀取；
            # 對外推播進入 READY_FOR_APPROVAL，需人工核准後才 dispatch
            step("PUBLISHED", {
                "note": "Dashboard 已更新；對外通報待人工核准",
                "notification_status": notification["status"],
            })

            # Coordinator 一句話決策摘要（判定/行動/升級條件/依據）——稽核產物
            state["coordinator_summary"] = build_coordinator_summary(state)

            state["workflow_status"] = "completed"
            state["current_step"] = "COMPLETED"
            state["completed_at"] = datetime.now().isoformat(timespec="seconds")
        except Exception as exc:  # noqa: BLE001 - 記錄後保留部分結果（fallback 原則）
            state["errors"].append(str(exc))
            state["workflow_status"] = "failed"
            step("FAILED_FINAL", {"error": str(exc)})

        self.incident_states[state["incident_id"]] = state
        return state

    # ---- 調度彈性：優先權抽調建議 / 釋出回填 ----

    def _iter_dispatch_actions(self):
        """走訪全部事件的調度動作：yield (state, action)。"""
        for st in self.incident_states.values():
            for act in (st.get("dispatch") or {}).get("actions", []):
                yield st, act

    def _attach_preemption_candidates(self, state: dict) -> None:
        """為缺口動作找出「較低優先事件」占用中的同類資源，列為可抽調來源。

        僅建議、不執行——指揮官核准（op=preempt）後才會真的移轉。
        """
        my_priority = state["dispatch"]["priority"]
        for action in state["dispatch"]["actions"]:
            if action.get("gap", 0) <= 0:
                continue
            candidates = []
            for src_state, src_act in self._iter_dispatch_actions():
                if src_state["incident_id"] == state["incident_id"]:
                    continue
                src_priority = (src_state.get("dispatch") or {}).get("priority", 0)
                if src_priority >= my_priority:
                    continue  # 只允許高優先抽調低優先
                if src_act["resource_type"] != action["resource_type"]:
                    continue
                if src_act["status"] == "rejected" or src_act["fulfilled_count"] <= 0:
                    continue
                candidates.append({
                    "source_incident_id": src_state["incident_id"],
                    "source_action_id": src_act["action_id"],
                    "source_severity": (src_state.get("dispatch") or {}).get("severity"),
                    "available_to_pull": src_act["fulfilled_count"],
                    "suggested_count": min(action["gap"], src_act["fulfilled_count"]),
                })
            candidates.sort(key=lambda c: dispatch_engine.SEVERITY_RANK.get(c["source_severity"], 0))
            action["preemption_candidates"] = candidates
            if candidates:
                best = candidates[0]
                action["escalation"] = (
                    action.get("escalation", "")
                    + f"｜可抽調建議：自 {best['source_incident_id']}"
                    f"（{best['source_severity']}）抽調 {best['suggested_count']} 單位，需指揮官核准"
                )

    def _pull_from_action(self, incident_id: str, action: dict, count: int) -> list[dict]:
        """自某動作釋出 count 單位（由 ETA 最遠的配置先抽），回傳釋出清單。"""
        released: list[dict] = []
        remaining = count
        for a in sorted(action["assignments"], key=lambda x: -x["eta_minutes"]):
            if remaining <= 0:
                break
            take = min(a["count"], remaining)
            a["count"] -= take
            remaining -= take
            released.append({"resource_id": a["resource_id"], "label": a["label"],
                             "count": take, "eta_minutes": a["eta_minutes"]})
        action["assignments"] = [a for a in action["assignments"] if a["count"] > 0]
        action["fulfilled_count"] -= count
        action["gap"] = action["requested_count"] - action["fulfilled_count"]
        self.bundle.registry.release(released)
        current = self._incident_allocations.get(incident_id, [])
        for r in released:
            for a in list(current):
                if a["resource_id"] == r["resource_id"] and a["count"] >= r["count"]:
                    a["count"] -= r["count"]
                    if a["count"] == 0:
                        current.remove(a)
                    break
        return released

    def _refresh_gaps(self, state: dict) -> None:
        d = state.get("dispatch")
        if not d:
            return
        d["gaps"] = [
            {"action_id": a["action_id"], "resource_type": a["resource_type"],
             "gap": a["gap"], "purpose": a.get("action", "")}
            for a in d["actions"] if a.get("gap", 0) > 0 and a["status"] != "rejected"
        ]
        d["has_shortfall"] = bool(d["gaps"])

    def _rebalance(self) -> None:
        """資源釋出後的再規劃：依優先權（高→低）回填仍有缺口的動作。

        只回填「尚未被拒絕」的動作；回填結果仍是待核准建議，
        並在該事件決策鏈寫入 RESOURCE_REBALANCED。
        """
        shortfalls = [
            (st, act) for st, act in self._iter_dispatch_actions()
            if act.get("gap", 0) > 0 and act["status"] != "rejected"
        ]
        shortfalls.sort(
            key=lambda x: -(x[0].get("dispatch") or {}).get("priority", 0))
        for st, act in shortfalls:
            assignments, remaining = self.bundle.registry.allocate(
                act["resource_type"], act["gap"])
            if not assignments:
                continue
            filled = act["gap"] - remaining
            act["assignments"].extend(assignments)
            act["fulfilled_count"] += filled
            act["gap"] = remaining
            if act["gap"] == 0 and act["status"] == "shortfall":
                act["status"] = "proposed"
                act.pop("escalation", None)
            self._incident_allocations.setdefault(st["incident_id"], []).extend(assignments)
            st["decision_trace"].append({
                "step": "RESOURCE_REBALANCED",
                "at": datetime.now().isoformat(timespec="milliseconds"),
                "detail": {"action_id": act["action_id"], "refilled": filled,
                           "remaining_gap": act["gap"],
                           "note": "其他事件釋出資源後自動回填（仍待指揮官核准）"},
            })
            self._refresh_gaps(st)

    def preempt(
        self, incident_id: str, action_id: str,
        source_incident_id: str, source_action_id: str, count: int,
        reason: str = "", operator: str = "commander",
    ) -> dict:
        """指揮官核准的優先權抽調：自低優先事件移轉資源到高優先事件。

        雙邊稽核：來源事件記 DISPATCH_PREEMPTED，目標事件記 HUMAN_OVERRIDE(op=preempt)。
        """
        state = self.incident_states.get(incident_id)
        src_state = self.incident_states.get(source_incident_id)
        if state is None or src_state is None:
            raise KeyError("事件不存在")
        action = next((a for a in state["dispatch"]["actions"] if a["action_id"] == action_id), None)
        src_act = next((a for a in src_state["dispatch"]["actions"]
                        if a["action_id"] == source_action_id), None)
        if action is None or src_act is None:
            raise KeyError("調度動作不存在")
        if src_act["resource_type"] != action["resource_type"]:
            raise ValueError("資源類型不符，無法抽調")
        if state["dispatch"]["priority"] <= src_state["dispatch"]["priority"]:
            raise ValueError(
                f"僅允許高優先抽調低優先（{state['dispatch']['severity']} ≤ "
                f"{src_state['dispatch']['severity']}）")
        count = min(count, src_act["fulfilled_count"], action["gap"])
        if count <= 0:
            raise ValueError("無可抽調數量（來源已無配置或目標已無缺口）")

        now = datetime.now()
        self._pull_from_action(source_incident_id, src_act, count)
        src_act["status"] = "preempted" if src_act["fulfilled_count"] == 0 else src_act["status"]
        src_act["escalation"] = (
            f"遭高優先事件 {incident_id} 抽調 {count} 單位（{operator} 核准），"
            f"目前配置 {src_act['fulfilled_count']}/{src_act['requested_count']}，缺口需人工補充")
        src_state["decision_trace"].append({
            "step": "DISPATCH_PREEMPTED",
            "at": now.isoformat(timespec="milliseconds"),
            "detail": {"action_id": source_action_id, "pulled_by": incident_id,
                       "count": count, "operator": operator, "reason": reason},
        })

        assignments, gap_left = self.bundle.registry.allocate(action["resource_type"], count)
        action["assignments"].extend(assignments)
        action["fulfilled_count"] += count - gap_left
        action["gap"] = action["requested_count"] - action["fulfilled_count"]
        if action["gap"] == 0:
            action["status"] = "proposed"
            action.pop("escalation", None)
        action["preemption_candidates"] = []
        self._incident_allocations.setdefault(incident_id, []).extend(assignments)
        state["decision_trace"].append({
            "step": "HUMAN_OVERRIDE",
            "at": now.isoformat(timespec="milliseconds"),
            "detail": {"action_id": action_id, "op": "preempt", "override_by": operator,
                       "override_reason": reason or f"自 {source_incident_id} 抽調 {count} 單位",
                       "override_at": now.strftime("%Y-%m-%d %H:%M"),
                       "source_incident_id": source_incident_id,
                       "source_action_id": source_action_id, "count": count},
        })
        self._refresh_gaps(state)
        self._refresh_gaps(src_state)
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
        self._refresh_gaps(state)
        # 拒絕/調降釋出的資源，自動回填其他事件的缺口（優先權排序）
        if op in ("reject", "adjust"):
            self._rebalance()
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
        """通報內容：LLM 生成（官方要求），必含 token 驗證把關，模板保底。"""
        from ..llm import generator

        affected_id = incident.get("affected_segment", "")
        if not affected_id.startswith("RD_"):
            affected_id = incident.get("affected_road", "")
        affected_seg = self.bundle.network.get(affected_id)
        affected_name = affected_seg.name if affected_seg else incident.get("location", "受影響區域")

        content = generator.build_notification_content(
            state, incident, at, affected_id, affected_name
        )
        msgs = content.pop("_full_messages")
        result = content

        # SOP 6：任一基地台漫遊率 >= 30% 才須多語；未觸發僅產出中文
        roaming_triggers = [t for t in crowd_triggers if t["rule_id"] == 6]
        result["multilingual_required"] = bool(roaming_triggers)
        result["roaming_evidence"] = [t["evidence"] for t in roaming_triggers]
        result["multilingual_decision"] = self._multilingual_decision(at, roaming_triggers)
        result["messages"] = msgs if roaming_triggers else {"zh": msgs["zh"]}
        return result

    def _multilingual_decision(self, at: datetime, roaming_triggers: list[dict]) -> dict:
        """SOP 6 觸發判定說明（供 UI 與評審檢視「本次是否觸發、為什麼」）。

        未觸發時 crowd_triggers 不含任何項目，最高漫遊率須自行由該時間切面取得，
        才能說明「最高 12% < 30%」而不是只回一個 false。
        """
        threshold = rule_engine.ROAMING_THRESHOLD_PCT
        if roaming_triggers:
            top = max(roaming_triggers, key=lambda t: t["evidence"]["roaming_user_pct"])
            ev = top["evidence"]
            pct = ev["roaming_user_pct"]
            return {
                "triggered": True,
                "threshold_pct": threshold,
                "max_roaming_pct": pct,
                "bs_id": top["entity_id"],
                "location_name": ev.get("location_name"),
                "triggered_count": len(roaming_triggers),
                "reason": (
                    f"{ev.get('location_name') or top['entity_id']} 漫遊率 {pct:g}% "
                    f"≥ {threshold:g}%，觸發 SOP 第 6 條，須產出多國語言"
                ),
            }

        snap = self.bundle.crowd_at(at)
        top_rec = max(snap.values(), key=lambda r: r.roaming_user_pct, default=None)
        if top_rec is None:
            return {
                "triggered": False,
                "threshold_pct": threshold,
                "max_roaming_pct": None,
                "bs_id": None,
                "location_name": None,
                "triggered_count": 0,
                "reason": "無基地台資料可判定，未觸發 SOP 第 6 條，僅產出中文",
            }
        return {
            "triggered": False,
            "threshold_pct": threshold,
            "max_roaming_pct": top_rec.roaming_user_pct,
            "bs_id": top_rec.bs_id,
            "location_name": top_rec.location_name,
            "triggered_count": 0,
            "reason": (
                f"最高漫遊率 {top_rec.roaming_user_pct:g}%（{top_rec.location_name}）"
                f"< {threshold:g}%，未觸發 SOP 第 6 條，僅產出中文"
            ),
        }
