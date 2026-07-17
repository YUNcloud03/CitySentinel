"""Resource Registry：可調度資源庫存與配置。

支撐「AI Command Center」的資源調度：Coordinator 依 SOP 與事件嚴重度
產生需求，向 registry 配置資源並扣減可用量；資源不足時回報缺口，
不得標示任務已完成（見 dispatch_engine）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 資源類型
POLICE = "Police"
SHUTTLE = "Shuttle"
SIGNAL_MAINT = "SignalMaintenance"
SIGNAL_CONTROL = "SignalControl"
MRT_LIAISON = "MRTLiaison"

TYPE_LABELS = {
    POLICE: "交通警力",
    SHUTTLE: "接駁車",
    SIGNAL_MAINT: "號誌維修人員",
    SIGNAL_CONTROL: "號誌控制",
    MRT_LIAISON: "北捷聯絡窗口",
}


@dataclass
class Resource:
    resource_id: str
    resource_type: str
    label: str
    total_count: int
    available_count: int
    current_location: str
    eta_minutes: int
    status: str = "Available"  # Available / Fully_Assigned

    def as_dict(self) -> dict:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "label": self.label,
            "total_count": self.total_count,
            "available_count": self.available_count,
            "current_location": self.current_location,
            "eta_minutes": self.eta_minutes,
            "status": self.status,
        }


def default_resources() -> list[Resource]:
    # 警力總量刻意有限（12）：三起事件併發即出現資源競爭，
    # 用以展示優先權抽調與缺口回報（庫存太寬裕會 Demo 不出調度彈性）。
    return [
        Resource("POL-01", POLICE, "交通警力 A 組", 8, 8, "信義分局", 6),
        Resource("POL-02", POLICE, "交通警力 B 組", 4, 4, "大安分局", 9),
        Resource("SHU-01", SHUTTLE, "公車處接駁車隊", 6, 6, "市府轉運站", 8),
        Resource("SIG-01", SIGNAL_MAINT, "號誌搶修組", 4, 4, "交工處松山站", 12),
        Resource("SIGC-01", SIGNAL_CONTROL, "號誌時制控制台", 3, 3, "交控中心", 1),
        Resource("MRT-01", MRT_LIAISON, "北捷行控聯絡窗口", 2, 2, "北捷行控中心", 2),
    ]


class ResourceRegistry:
    def __init__(self, resources: list[Resource] | None = None):
        self._seed = resources or default_resources()
        self._resources: dict[str, Resource] = {}
        self.reset()

    def reset(self) -> None:
        """回到初始庫存（Demo 重跑用）。"""
        self._resources = {
            r.resource_id: Resource(**r.as_dict()) for r in self._seed
        }

    def list(self) -> list[Resource]:
        return list(self._resources.values())

    def get(self, resource_id: str) -> Resource:
        return self._resources[resource_id]

    def _available_of_type(self, rtype: str) -> list[Resource]:
        return [
            r for r in self._resources.values()
            if r.resource_type == rtype and r.available_count > 0
        ]

    def allocate(self, rtype: str, count: int) -> tuple[list[dict], int]:
        """配置某類型 count 個資源；跨多個資源單位配置（依 ETA 由近至遠）。

        回傳 (assignments, gap)：
          assignments = [{resource_id, label, count, eta_minutes}, ...]
          gap = 未能滿足的數量（> 0 代表資源不足）
        同一資源不可重複派遣：available_count 會被扣減。
        """
        assignments: list[dict] = []
        remaining = count
        for r in sorted(self._available_of_type(rtype), key=lambda x: x.eta_minutes):
            if remaining <= 0:
                break
            take = min(r.available_count, remaining)
            r.available_count -= take
            remaining -= take
            if r.available_count == 0:
                r.status = "Fully_Assigned"
            assignments.append({
                "resource_id": r.resource_id,
                "label": r.label,
                "count": take,
                "eta_minutes": r.eta_minutes,
            })
        return assignments, remaining

    def release(self, assignments: list[dict]) -> None:
        """歸還配置（拒絕/調整/重新注入同一事件時使用）。"""
        for a in assignments:
            r = self._resources.get(a["resource_id"])
            if r is None:
                continue
            r.available_count = min(r.total_count, r.available_count + a["count"])
            if r.available_count > 0:
                r.status = "Available"
