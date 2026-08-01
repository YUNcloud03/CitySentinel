"""What-if Sandbox：在複製的狀態上套用假設條件，不動正式狀態。

輸入為結構化假設（Phase 1）；自然語言 → 結構化參數的 LLM 解析屬 Phase 2，
解析完成後同樣走這裡的 run_what_if()，共用同一套 Rule/Route/ETE 引擎。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime

from ..data_loader import parse_ts
from ..engines import rule_engine, routing_engine, ete_calculator
from .coordinator import DataBundle


def _trigger_summary(triggers: list[dict]) -> list[dict]:
    return [
        {"rule_id": t["rule_id"], "entity_id": t["entity_id"], "evidence": t["evidence"], "actions": t["actions"]}
        for t in triggers
    ]


def run_what_if(bundle: DataBundle, scenario: dict) -> dict:
    """scenario 格式：
    {
      "at": "2026-05-20 22:00",                       # 必填，假設套用的時間切面
      "crowd_overrides":   {"BS_MRT_BL17": {"user_count": 40000, ...}},
      "traffic_overrides": {"RD_TPE_004": {"saturation_score": 0.9, ...}},
      "simulated_incident": {...live_incidents 同格式...}   # 選填
    }
    回傳 baseline 與 sandbox 的觸發規則比較。
    """
    at: datetime = parse_ts(scenario["at"])

    # 基準狀態
    base_traffic = bundle.traffic_at(at)
    base_crowd = bundle.crowd_at(at)
    unknown_traffic = set(scenario.get("traffic_overrides") or {}) - set(bundle.network)
    known_stations = {record.bs_id for record in bundle.crowd}
    unknown_crowd = set(scenario.get("crowd_overrides") or {}) - known_stations
    if unknown_traffic or unknown_crowd:
        raise KeyError(
            f"What-if 含未知 ID：{', '.join(sorted(unknown_traffic | unknown_crowd))}"
        )
    baseline_triggers = (
        rule_engine.evaluate_crowd(base_crowd, bundle.crowd, at)
        + rule_engine.evaluate_traffic(base_traffic)["triggers"]
    )

    # Sandbox：複製快照並套用覆寫（正式狀態不變）
    sandbox_traffic = dict(base_traffic)
    for seg_id, fields in (scenario.get("traffic_overrides") or {}).items():
        if seg_id in sandbox_traffic:
            sandbox_traffic[seg_id] = replace(sandbox_traffic[seg_id], **fields)
    sandbox_crowd = dict(base_crowd)
    for bs_id, fields in (scenario.get("crowd_overrides") or {}).items():
        if bs_id in sandbox_crowd:
            sandbox_crowd[bs_id] = replace(sandbox_crowd[bs_id], **fields)

    # 覆寫後的人流歷史（峰值判定用）：以 sandbox 快照值視為「當前」，歷史沿用正式資料
    sandbox_triggers = (
        rule_engine.evaluate_crowd(sandbox_crowd, bundle.crowd, at)
        + rule_engine.evaluate_traffic(sandbox_traffic)["triggers"]
    )

    result = {
        "as_of": scenario["at"],
        "scenario": scenario,
        "baseline": {
            "triggered_rules": sorted({t["rule_id"] for t in baseline_triggers}),
            "triggers": _trigger_summary(baseline_triggers),
        },
        "sandbox": {
            "triggered_rules": sorted({t["rule_id"] for t in sandbox_triggers}),
            "triggers": _trigger_summary(sandbox_triggers),
        },
        "production_state_modified": False,
    }

    # 假設事件：跑事件規則 + 路徑 + ETE（僅在 sandbox 內）
    sim = scenario.get("simulated_incident")
    if sim:
        incident_triggers = rule_engine.evaluate_incident(sim)
        result["sandbox"]["incident_triggers"] = _trigger_summary(incident_triggers)
        if any(t["rule_id"] == 2 for t in incident_triggers):
            result["sandbox"]["routing_result"] = routing_engine.plan_evacuation(
                sim["affected_segment"], bundle.network, sandbox_traffic, sim.get("location")
            )
            rec = sandbox_traffic.get(sim["affected_segment"])
            if rec and sim.get("severity") in ete_calculator.BASE_CLEARANCE:
                result["sandbox"]["ete_result"] = ete_calculator.calculate_ete(
                    sim["severity"], [rec.saturation_score]
                )

    new_rules = set(result["sandbox"]["triggered_rules"]) - set(result["baseline"]["triggered_rules"])
    result["diff"] = {"newly_triggered_rules": sorted(new_rules)}
    scenario_json = json.dumps(scenario, ensure_ascii=False, sort_keys=True, default=str)
    baseline_json = json.dumps({
        "traffic": {key: vars(value) for key, value in sorted(base_traffic.items())},
        "crowd": {key: vars(value) for key, value in sorted(base_crowd.items())},
    }, ensure_ascii=False, sort_keys=True, default=str)
    scenario_hash = hashlib.sha256(scenario_json.encode()).hexdigest()
    baseline_hash = hashlib.sha256(baseline_json.encode()).hexdigest()
    result["simulation_run_id"] = f"WHATIF-{scenario_hash[:12]}"
    result["model"] = "deterministic-whatif-v1"
    result["evidence_contract"] = {
        "version": "v1", "baseline_snapshot_sha256": baseline_hash,
        "scenario_sha256": scenario_hash, "model": result["model"], "randomness_used": False,
        "metrics": result["diff"],
        "limitations": "覆寫指定欄位後重新執行規則；不是交通微觀模擬",
    }
    return result
