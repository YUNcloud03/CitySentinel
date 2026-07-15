"""時序資料播放器：沿資料時間軸推進，每個 tick 自動跑規則監測。

播放節奏由前端輪詢 /tick 控制（1～3 秒一次代表資料中的 15～30 分鐘），
畫面同時顯示「模擬時間」與「真實系統時間」。
"""
from __future__ import annotations

from ..data_loader import all_timestamps, format_ts
from ..engines import rule_engine
from ..coordinator.coordinator import DataBundle


class SimulationPlayer:
    def __init__(self, bundle: DataBundle):
        self.bundle = bundle
        self.timestamps = all_timestamps(bundle.traffic, bundle.crowd)
        self.index = -1  # 尚未開始
        self.playing = False
        self.speed = 1
        self.alert_log: list[dict] = []

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

        traffic_snap = self.bundle.traffic_at(at)
        crowd_snap = self.bundle.crowd_at(at)
        traffic_eval = rule_engine.evaluate_traffic(traffic_snap)
        crowd_triggers = rule_engine.evaluate_crowd(crowd_snap, self.bundle.crowd, at)

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
        }
