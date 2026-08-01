"""時序資料播放器：沿資料時間軸推進，每個 tick 自動跑規則監測。

播放節奏由前端輪詢 /tick 控制（1～3 秒一次代表資料中的 15～30 分鐘），
畫面同時顯示「模擬時間」與「真實系統時間」。
"""
from __future__ import annotations

import hashlib
import json

from ..data_loader import all_timestamps, format_ts
from ..engines import ete_calculator, rule_engine
from ..coordinator.coordinator import DataBundle
from .incident_effects import project_incident


def _scenario_metrics(record) -> dict:
    saturation = record.saturation_score if hasattr(record, "saturation_score") else record["saturation_score"]
    return {
        "avg_speed": record.avg_speed if hasattr(record, "avg_speed") else record["avg_speed"],
        "vehicle_count": record.vehicle_count if hasattr(record, "vehicle_count") else record["vehicle_count"],
        "saturation_score": saturation,
        "congestion_level": "A" if saturation >= .95 else "B" if saturation >= .85 else "Normal",
    }


def build_scenario_comparison(at, baseline, current, context, incident_state) -> dict | None:
    """Build one backend-owned evidence contract for baseline/event/treatment."""
    if not context.get("active") or not incident_state:
        return None
    segment_id = context.get("affected_segment_id")
    event_metrics = context.get("unmitigated_metrics", {}).get(segment_id)
    if not segment_id or segment_id not in baseline or segment_id not in current or not event_metrics:
        return None

    event = incident_state.get("event") or {}
    severity = event.get("severity")

    def ete_for(saturation: float) -> dict | None:
        if severity not in ete_calculator.BASE_CLEARANCE:
            return None
        return ete_calculator.calculate_ete(severity, [saturation])

    baseline_metrics = _scenario_metrics(baseline[segment_id])
    incident_metrics = _scenario_metrics(event_metrics)
    treatment_metrics = _scenario_metrics(current[segment_id])
    accepted = bool(context.get("accepted_action_ids"))
    on_scene = bool(context.get("on_scene_action_ids"))
    treatment_state = (
        "CLEARANCE_ACTIVE" if on_scene and context.get("response_phase") == "CLEARANCE_ACTIVE"
        else "CLEARED_AWAITING_FIELD_CONFIRMATION" if context.get("response_phase") == "CLEARED"
        else "DISPATCHING_NO_IMPROVEMENT_YET" if accepted
        else "LOCKED_PENDING_APPROVAL"
    )
    canonical_input = json.dumps({
        "as_of": format_ts(at),
        "segment_id": segment_id,
        "event": event,
        "baseline": baseline_metrics,
        "accepted_action_ids": context.get("accepted_action_ids", []),
        "on_scene_action_ids": context.get("on_scene_action_ids", []),
        "model": context.get("model"),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    input_hash = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()
    return {
        "simulation_run_id": f"COMPARE-{input_hash[:12]}",
        "input_sha256": input_hash,
        "as_of": format_ts(at),
        "affected_segment_id": segment_id,
        "affected_road_name": baseline[segment_id].road_name,
        "model": context.get("model"),
        "randomness_used": False,
        "scenarios": {
            "baseline": {
                "available": True,
                "state": "NO_INCIDENT",
                "metrics": baseline_metrics,
                "ete": None,
                "source": "city_traffic_flow.csv",
            },
            "incident": {
                "available": True,
                "state": "OBSTACLE_ACTIVE_UNMITIGATED",
                "metrics": incident_metrics,
                "ete": ete_for(incident_metrics["saturation_score"]),
                "source": context.get("model"),
            },
            "treatment": {
                "available": accepted,
                "state": treatment_state,
                "locked_reason": None if accepted else "指揮官尚未核准任何處置決策",
                "effect_started": on_scene,
                "metrics": treatment_metrics if accepted else None,
                "ete": ete_for(treatment_metrics["saturation_score"]) if accepted else None,
                "source": context.get("model") if accepted else None,
            },
        },
        "ete_definition": "依 SOP 第 7 條，以各情境當下飽和度重新估算；不是剩餘時間線性插值",
    }


class SimulationPlayer:
    def __init__(self, bundle: DataBundle):
        self.bundle = bundle
        self.timestamps = all_timestamps(bundle.traffic, bundle.crowd)
        self.index = -1  # 尚未開始
        self.playing = False
        self.speed = 1
        self.alert_log: list[dict] = []
        self.active_incident_state: dict | None = None

    def activate_incident(self, state: dict | None) -> None:
        """Attach one incident scenario to subsequent timeline views."""
        self.active_incident_state = state

    def reset(self, timestamp: str = "2026-05-20 21:00") -> dict:
        """Return the player to a clean, paused organizer-data baseline."""
        self.playing = False
        self.speed = 1
        self.alert_log.clear()
        self.active_incident_state = None
        return self.seek(timestamp)

    # ---- 控制 ----

    def start(self, speed: int = 1, start_timestamp: str | None = None):
        self.playing = True
        self.speed = speed
        if start_timestamp is not None:
            self.seek(start_timestamp)
        elif self.index < 0:
            self.index = 0
        return self.current_view()

    def pause(self):
        self.playing = False
        return {"playing": False, "sim_time": self._sim_time()}

    def seek(self, timestamp: str):
        from ..data_loader import parse_ts

        target = parse_ts(timestamp)
        candidates = [i for i, t in enumerate(self.timestamps) if t <= target]
        self.index = candidates[-1] if candidates else 0
        return self.current_view()

    def tick(self):
        """推進一個資料時間點並回傳當下監測結果。"""
        if not self.playing:
            return self.current_view()
        if self.index < len(self.timestamps) - 1:
            self.index += 1
        else:
            self.playing = False  # 播畢自動停
        return self.current_view()

    # ---- 查詢 ----

    def _sim_time(self):
        if self.index < 0:
            return None
        return self.timestamps[self.index]

    def current_view(self) -> dict:
        at = self._sim_time()
        if at is None:
            return {"playing": self.playing, "sim_time": None, "message": "尚未開始播放"}

        baseline_traffic = self.bundle.traffic_at(at)
        traffic_snap, simulation_context = project_incident(
            at=at,
            baseline=baseline_traffic,
            incident_state=self.active_incident_state,
            network=self.bundle.network,
        )
        crowd_snap = self.bundle.crowd_at(at)
        traffic_eval = rule_engine.evaluate_traffic(traffic_snap)
        crowd_triggers = rule_engine.evaluate_crowd(crowd_snap, self.bundle.crowd, at)
        scenario_comparison = build_scenario_comparison(
            at, baseline_traffic, traffic_snap, simulation_context, self.active_incident_state
        )

        alerts = traffic_eval["triggers"] + crowd_triggers
        for alert in alerts:
            key = (format_ts(at), alert["rule_id"], alert["entity_id"])
            if key not in {(a["sim_time"], a["rule_id"], a["entity_id"]) for a in self.alert_log}:
                from datetime import datetime as _dt

                self.alert_log.append(
                    {"sim_time": format_ts(at), "rule_id": alert["rule_id"],
                     "entity_id": alert["entity_id"], "evidence": alert["evidence"],
                     "actions": alert["actions"],
                     "logged_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S")}
                )

        return {
            "playing": self.playing,
            "speed": self.speed,
            "sim_time": format_ts(at),
            "progress": {"index": self.index, "total": len(self.timestamps)},
            "traffic": {
                seg_id: {
                    "road_name": rec.road_name,
                    "avg_speed": rec.avg_speed,
                    "vehicle_count": rec.vehicle_count,
                    "saturation_score": rec.saturation_score,
                    "lane_status": rec.lane_status,
                    "congestion_level": traffic_eval["levels"][seg_id],
                    "data_time": format_ts(rec.timestamp),
                    "simulation_source": (
                        "incident_projection"
                        if seg_id in simulation_context.get("changed_segment_ids", [])
                        else "organizer_dataset"
                    ),
                    "baseline_avg_speed": baseline_traffic[seg_id].avg_speed,
                    "baseline_vehicle_count": baseline_traffic[seg_id].vehicle_count,
                    "baseline_saturation_score": baseline_traffic[seg_id].saturation_score,
                    **(
                        {
                            "event_avg_speed": simulation_context["unmitigated_metrics"][seg_id]["avg_speed"],
                            "event_vehicle_count": simulation_context["unmitigated_metrics"][seg_id]["vehicle_count"],
                            "event_saturation_score": simulation_context["unmitigated_metrics"][seg_id]["saturation_score"],
                        }
                        if seg_id in simulation_context.get("unmitigated_metrics", {}) else {}
                    ),
                }
                for seg_id, rec in sorted(traffic_snap.items())
            },
            "crowd": {
                bs_id: {
                    "location_name": rec.location_name,
                    "user_count": rec.user_count,
                    "growth_rate": rec.growth_rate,
                    "roaming_user_pct": rec.roaming_user_pct,
                    "data_time": format_ts(rec.timestamp),
                }
                for bs_id, rec in sorted(crowd_snap.items())
            },
            "active_alerts": alerts,
            "alert_log_size": len(self.alert_log),
            "simulation_context": simulation_context,
            "scenario_comparison": scenario_comparison,
        }
