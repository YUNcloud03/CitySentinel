"""Advisory Agent：真正的 tool-calling agent（諮詢層）。

LLM 在迴圈中**自主決定**呼叫哪些工具、以什麼參數、何時停止——這是系統中
唯一由 LLM 掌握控制流的地方，刻意只放在諮詢層：

    決策層（Rule/Routing/ETE/Dispatch）＝確定性引擎，LLM 不可觸碰
    諮詢層（本模組）＝LLM agent，但工具全部唯讀或 sandbox

安全邊界（物理性，非規範性）：
    1. 工具允許清單只有唯讀查詢與 What-if sandbox——發布通報、調度資源、
       核准動作的工具**不存在**，agent 想呼叫也沒有。
    2. 迴圈上限 MAX_ITERS，超過即終止。
    3. 引用條款由「工具呼叫軌跡」推導（agent 真的查過什麼就引用什麼），
       再與回答文字交叉驗證，不信任 LLM 自報。
    4. 每一步 LLM 呼叫與工具執行都留痕（CALL_LOG + tool_trace 回傳前端）。
"""
from __future__ import annotations

import json
import hashlib
import re
import time
from datetime import datetime

from ..coordinator.whatif import run_what_if
from ..data_loader import format_ts, parse_ts
from . import client as llm_client

MAX_ITERS = 5
MAX_RESULT_CHARS = 3000  # 單一工具結果餵回 LLM 的長度上限

AGENT_SYSTEM = """你是交控中心的 AI 顧問 agent，透過工具查證後回答指揮官的問題。

行為準則：
1. 回答前先用工具查證——不要憑記憶回答 SOP 內容、事件狀態或數據。
2. 假設性問題（如果/假設…會怎樣）一律呼叫 run_what_if 在 sandbox 驗證。
3. 引用 SOP 時使用「SOP N」格式標明條款編號。
   What-if 結果若顯示條款在「基準」就已觸發，代表該條款目前已在適用中——
   回答時說明假設成立後該條款持續適用及其處置動作，不要只說「無新觸發」。
4. 所有數值必須與工具回傳完全一致，不可改寫、換算或推測。
5. 你沒有任何執行權限：不能發布通報、不能調度資源、不能核准任何動作，
   這些都需要指揮官在指揮中心操作。若被要求執行，說明需人工操作。
6. 查證完成即回答，以繁體中文、150 字內為原則。"""


# ---- 工具定義（allowlist：唯讀 + sandbox，無任何執行類工具） ----

TOOL_SPECS: list[dict] = [
    {
        "name": "get_sop",
        "description": "查詢交通應變 SOP。給 rule_id（1-7）取該條全文；不給則列出全部條款標題。",
        "parameters": {
            "type": "object",
            "properties": {"rule_id": {"type": "integer", "minimum": 1, "maximum": 7}},
            "required": [],
        },
    },
    {
        "name": "get_incident",
        "description": "查詢已處理事件的決策結果（觸發條款、疏散路徑、ETE、調度、可信度）。不給 incident_id 則回傳最新一筆與全部事件清單。",
        "parameters": {
            "type": "object",
            "properties": {"incident_id": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "run_what_if",
        "description": "在 Sandbox 執行假設分析（不影響正式狀態）。覆寫人流/車流數值或模擬事故，回傳基準與假設後的 SOP 觸發差異。ID 必須使用系統中存在的（見 system prompt 清單）。",
        "parameters": {
            "type": "object",
            "properties": {
                "at": {"type": "string", "description": "時間切面 YYYY-MM-DD HH:MM，日期固定 2026-05-20"},
                "crowd_overrides": {
                    "type": "object",
                    "description": "基地台覆寫，如 {\"BS_MRT_BL17\": {\"user_count\": 40000}}；欄位可用 user_count/growth_rate/roaming_user_pct",
                },
                "traffic_overrides": {
                    "type": "object",
                    "description": "路段覆寫，如 {\"RD_TPE_002\": {\"saturation_score\": 0.96}}",
                },
                "simulated_incident": {
                    "type": "object",
                    "description": "模擬事故：{affected_segment, status(Closed/Blocked/Restricted), severity(Critical/High/Medium), location?}",
                },
            },
            "required": ["at"],
        },
    },
    {
        "name": "get_traffic",
        "description": "查詢指定時間（預設當前模擬時間）的路段車流快照：飽和度、車速、壅塞分級。",
        "parameters": {
            "type": "object",
            "properties": {"at": {"type": "string", "description": "YYYY-MM-DD HH:MM"}},
            "required": [],
        },
    },
    {
        "name": "get_crowd",
        "description": "查詢指定時間（預設當前模擬時間）的基地台人流快照：人數、成長率、漫遊率。",
        "parameters": {
            "type": "object",
            "properties": {"at": {"type": "string", "description": "YYYY-MM-DD HH:MM"}},
            "required": [],
        },
    },
    {
        "name": "get_resources",
        "description": "查詢調度資源庫存：各資源可用量/總量、ETA、目前狀態。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_confidence",
        "description": "查詢事件可信度評估（多源交叉驗證分數與證據）。",
        "parameters": {
            "type": "object",
            "properties": {"incident_id": {"type": "string"}},
            "required": [],
        },
    },
]


class AdvisorAgent:
    def __init__(self, bundle, coordinator, player):
        self.bundle = bundle
        self.coordinator = coordinator
        self.player = player

    # ---- 工具執行（全部唯讀 / sandbox） ----

    def _default_at(self) -> str:
        t = self.player._sim_time() if self.player else None
        return format_ts(t) if t else "2026-05-20 22:00"

    def _execute_tool(self, name: str, args: dict) -> dict:
        try:
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                return {"error": f"未知工具 {name}（允許清單外）"}
            return handler(**args)
        except Exception as exc:  # noqa: BLE001 - 工具錯誤回饋給 agent 自行調整
            return {"error": f"{type(exc).__name__}: {exc}"}

    def _tool_get_sop(self, rule_id: int | None = None) -> dict:
        if rule_id is None:
            return {"rules": [{"rule_id": r["rule_id"], "title": r["title"]}
                              for r in self.bundle.sop.rules.values()]}
        rule = self.bundle.sop.get(int(rule_id))
        return {"rule_id": rule["rule_id"], "title": rule["title"], "text": rule["text"]}

    def _tool_get_incident(self, incident_id: str | None = None) -> dict:
        states = self.coordinator.incident_states
        if not states:
            return {"info": "目前沒有已處理的事件"}
        st = states.get(incident_id) if incident_id else list(states.values())[-1]
        if st is None:
            return {"error": f"找不到事件 {incident_id}", "available": list(states)}
        routing = st.get("routing_result") or {}
        primary = routing.get("primary_route")
        return {
            "incident_id": st["incident_id"],
            "event": {k: st["event"].get(k) for k in ("type", "location", "status", "severity")},
            "rule_attribution": st.get("rule_attribution"),
            "primary_route": primary["name"] if primary else None,
            "excluded_routes": [
                {"name": e.get("name", e["segment_id"]), "reason": e["reason_code"]}
                for e in routing.get("excluded_routes", [])
            ],
            "ete": (st.get("ete_result") or {}).get("formula"),
            "confidence": st.get("confidence"),
            "dispatch_actions": [
                {"action": a["action"], "status": a["status"], "gap": a.get("gap", 0)}
                for a in (st.get("dispatch") or {}).get("actions", [])
            ],
            "all_incidents": list(states),
        }

    def _tool_run_what_if(self, at: str, crowd_overrides: dict | None = None,
                          traffic_overrides: dict | None = None,
                          simulated_incident: dict | None = None) -> dict:
        parse_ts(at)  # 格式驗證
        scenario: dict = {"at": at}
        if crowd_overrides:
            scenario["crowd_overrides"] = crowd_overrides
        if traffic_overrides:
            scenario["traffic_overrides"] = traffic_overrides
        if simulated_incident:
            sim = dict(simulated_incident)
            sim.setdefault("event_id", "AGENT_WHATIF")
            sim.setdefault("type", "Simulated_Incident")
            sim.setdefault("timestamp", at)
            sim.setdefault("description", "agent what-if 模擬")
            scenario["simulated_incident"] = sim
        if len(scenario) == 1:
            return {"error": "至少需要一項覆寫或模擬事故"}
        result = run_what_if(self.bundle, scenario)
        compact = {
            "at": at,
            "baseline_rules": result["baseline"]["triggered_rules"],
            "sandbox_rules": result["sandbox"]["triggered_rules"],
            "newly_triggered": result["diff"]["newly_triggered_rules"],
            "sandbox_triggers": [
                {"rule_id": t["rule_id"], "entity_id": t["entity_id"],
                 "already_triggered_at_baseline": t["rule_id"] not in result["diff"]["newly_triggered_rules"],
                 "actions": t["actions"]}
                for t in result["sandbox"]["triggers"]
            ],
            "production_state_modified": False,
        }
        sandbox = result.get("sandbox", {})
        if sandbox.get("routing_result"):
            p = sandbox["routing_result"].get("primary_route")
            compact["simulated_primary_route"] = p["name"] if p else None
            compact["incident_rules"] = sorted(
                {t["rule_id"] for t in sandbox.get("incident_triggers", [])})
        if sandbox.get("ete_result"):
            compact["simulated_ete_minutes"] = sandbox["ete_result"]["ete_minutes_display"]
        return compact

    def _tool_get_traffic(self, at: str | None = None) -> dict:
        ts = parse_ts(at) if at else parse_ts(self._default_at())
        from ..data_loader import traffic_snapshot
        from ..engines.rule_engine import classify_congestion

        snap = traffic_snapshot(self.bundle.traffic, ts)
        return {"at": format_ts(ts), "segments": [
            {"id": s, "name": r.road_name, "saturation": r.saturation_score,
             "speed": r.avg_speed, "level": classify_congestion(r.saturation_score)}
            for s, r in sorted(snap.items(), key=lambda x: -x[1].saturation_score)
        ]}

    def _tool_get_crowd(self, at: str | None = None) -> dict:
        ts = parse_ts(at) if at else parse_ts(self._default_at())
        from ..data_loader import crowd_snapshot

        snap = crowd_snapshot(self.bundle.crowd, ts)
        return {"at": format_ts(ts), "stations": [
            {"id": b, "name": r.location_name, "users": r.user_count,
             "growth": r.growth_rate, "roaming_pct": r.roaming_user_pct}
            for b, r in sorted(snap.items(), key=lambda x: -x[1].user_count)
        ]}

    def _tool_get_resources(self) -> dict:
        return {"resources": [r.as_dict() for r in self.bundle.registry.list()]}

    def _tool_get_confidence(self, incident_id: str | None = None) -> dict:
        out = [
            {"incident_id": st["incident_id"], **st["confidence"]}
            for st in self.coordinator.incident_states.values()
            if st.get("confidence") and (not incident_id or st["incident_id"] == incident_id)
        ]
        return {"assessments": out or "尚無事件可信度資料"}

    # ---- 工具結果摘要（前端軌跡顯示用） ----

    @staticmethod
    def _summarize(name: str, result: dict) -> str:
        if "error" in result:
            return f"錯誤：{result['error']}"
        if name == "get_sop":
            return f"第 {result['rule_id']} 條「{result['title']}」" if "rule_id" in result \
                else f"{len(result['rules'])} 條 SOP 標題"
        if name == "run_what_if":
            return f"基準 {result['baseline_rules']} → 假設後 {result['sandbox_rules']}（sandbox，正式狀態未動）"
        if name == "get_incident":
            return f"{result.get('incident_id', '')}｜主疏散 {result.get('primary_route')}" \
                if "incident_id" in result else str(result.get("info", ""))
        if name == "get_traffic":
            top = result["segments"][0] if result["segments"] else None
            return f"{result['at']}｜最高飽和 {top['name']} {top['saturation']}" if top else "無資料"
        if name == "get_crowd":
            top = result["stations"][0] if result["stations"] else None
            return f"{result['at']}｜最多人 {top['name']} {top['users']:,}" if top else "無資料"
        if name == "get_resources":
            return f"{len(result['resources'])} 類資源庫存"
        if name == "get_confidence":
            a = result["assessments"]
            return f"{len(a)} 筆可信度評估" if isinstance(a, list) else str(a)
        return "完成"

    # ---- LLM 單步（provider 分流；測試時可 monkeypatch） ----

    def _llm_step(self, messages: list) -> tuple[str, object]:
        """回傳 ("tools", [(id, name, args), ...]) 或 ("final", answer_text)。"""
        provider, client = llm_client.get_provider()
        prov = llm_client.active_provider()
        started = time.monotonic()
        try:
            if prov.protocol == "anthropic":
                out = self._step_anthropic(client, prov.model, messages)
            else:
                out = self._step_openai(client, prov.model, messages)
            ok = True
            return out
        except Exception as exc:  # noqa: BLE001
            ok = False
            raise
        finally:
            llm_client.CALL_LOG.append({
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "purpose": "advisor_agent_step",
                "provider": provider,
                "model": prov.model,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "ok": ok,
                "note": "",
            })

    def _step_openai(self, client, model, messages) -> tuple[str, object]:
        tools = [{"type": "function",
                  "function": {"name": t["name"], "description": t["description"],
                               "parameters": t["parameters"]}}
                 for t in TOOL_SPECS]
        resp = client.chat.completions.create(
            model=model, max_tokens=900, temperature=0,
            messages=messages, tools=tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(msg)  # SDK 接受 message 物件
            calls = [(tc.id, tc.function.name, json.loads(tc.function.arguments or "{}"))
                     for tc in msg.tool_calls]
            return ("tools", calls)
        return ("final", msg.content or "")

    def _append_tool_result_openai(self, messages, call_id, result) -> None:
        messages.append({"role": "tool", "tool_call_id": call_id,
                         "content": json.dumps(result, ensure_ascii=False)[:MAX_RESULT_CHARS]})

    def _step_anthropic(self, client, model, messages) -> tuple[str, object]:
        tools = [{"name": t["name"], "description": t["description"],
                  "input_schema": t["parameters"]}
                 for t in TOOL_SPECS]
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        convo = [m for m in messages if m["role"] != "system"]
        resp = client.messages.create(
            model=model, max_tokens=900,
            system=system, messages=convo, tools=tools,
        )
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            calls = [(b.id, b.name, dict(b.input))
                     for b in resp.content if b.type == "tool_use"]
            return ("tools", calls)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return ("final", text)

    def _append_tool_result_anthropic(self, messages, call_id, result) -> None:
        # anthropic：所有 tool_result 需在同一則 user message；呼叫端已依 call 逐一附加，
        # 這裡合併到最後一則 user tool_result 訊息
        block = {"type": "tool_result", "tool_use_id": call_id,
                 "content": json.dumps(result, ensure_ascii=False)[:MAX_RESULT_CHARS]}
        if messages and messages[-1].get("role") == "user" and isinstance(messages[-1]["content"], list):
            messages[-1]["content"].append(block)
        else:
            messages.append({"role": "user", "content": [block]})

    # ---- 主迴圈 ----

    def run(self, question: str, history: list[dict] | None = None) -> dict:
        provider, _ = llm_client.get_provider()
        if provider is None:
            return {"available": False}
        protocol = llm_client.active_provider().protocol

        segment_ids = list(self.bundle.network)
        station_ids = sorted({r.bs_id for r in self.bundle.crowd})
        system = (
            AGENT_SYSTEM
            + f"\n\n當前模擬時間：{self._default_at()}"
            + f"\n可用路段 ID：{segment_ids}"
            + f"\n可用基地台 ID：{station_ids}"
        )
        messages: list = [{"role": "system", "content": system}]
        for h in (history or [])[-6:]:
            role = "assistant" if h.get("role") in ("advisor", "assistant") else "user"
            messages.append({"role": role, "content": str(h.get("text", ""))[:800]})
        messages.append({"role": "user", "content": question})

        trace: list[dict] = []
        answer = ""
        for _ in range(MAX_ITERS):
            kind, payload = self._llm_step(messages)
            if kind == "final":
                if not trace:
                    answer = "目前尚未取得可驗證工具證據，不能提供數字、路線、資源或 SOP 結論。"
                else:
                    answer = payload
                break
            for call_id, name, args in payload:
                result = self._execute_tool(name, args)
                canonical_args = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
                canonical_result = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
                trace.append({"call_id": call_id, "tool": name, "args": args,
                              "args_sha256": hashlib.sha256(canonical_args.encode()).hexdigest(),
                              "result_sha256": hashlib.sha256(canonical_result.encode()).hexdigest(),
                              "summary": self._summarize(name, result)})
                if protocol == "anthropic":
                    self._append_tool_result_anthropic(messages, call_id, result)
                else:
                    self._append_tool_result_openai(messages, call_id, result)
        else:
            answer = "已達工具呼叫上限，以下為目前查證到的資訊摘要：" + \
                     "；".join(t["summary"] for t in trace[-3:])

        validation = "VERIFIED_TOOL_GROUNDED" if trace else "REJECTED_NO_EVIDENCE"
        return {
            "available": True,
            "answer": answer,
            "cited_rule_ids": self._derive_citations(answer, trace),
            "tool_trace": trace,
            "iterations": len(trace),
            "provider": provider,
            "evidence_contract": {
                "version": "v1",
                "validation_status": validation,
                "tool_result_hashes": [row["result_sha256"] for row in trace],
                "claim_status": "advisory_only",
                "external_execution_allowed": False,
            },
        }

    # ---- 引用推導（不信任 LLM 自報：以工具軌跡為準，再與文字交叉） ----

    @staticmethod
    def _derive_citations(answer: str, trace: list[dict]) -> list[int]:
        cited: set[int] = set()
        for t in trace:
            if t["tool"] == "get_sop" and isinstance(t["args"].get("rule_id"), int):
                cited.add(t["args"]["rule_id"])
            if t["tool"] == "run_what_if":
                m = re.findall(r"\[([0-9, ]+)\]", t["summary"])
                for group in m:
                    cited.update(int(x) for x in re.findall(r"[1-7]", group))
        return sorted(c for c in cited if 1 <= c <= 7)
