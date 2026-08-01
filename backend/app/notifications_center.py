"""推播生命週期狀態機。

訊息「生成」不等於「已送達民眾」。狀態機：

    DRAFTED → READY_FOR_APPROVAL → APPROVED → DISPATCHING
        → DELIVERY_CONFIRMED（全通道成功）
        → DELIVERY_FAILED（任一通道失敗）→ RETRYING → CONFIRMED / FAILED

Demo 使用模擬 Adapter 回傳送達狀態，不真的發送簡訊或控制 CMS。
發布（dispatch）必須先經人工核准（approve）——LLM 與 Coordinator 都不得直接發布。
"""
from __future__ import annotations

from datetime import datetime

CHANNELS = ("CMS", "Mobile_App", "SMS")

# 合法狀態轉移表
_TRANSITIONS = {
    "READY_FOR_APPROVAL": {"approve": "APPROVED"},
    "APPROVED": {"dispatch": "DISPATCHING"},
    "DELIVERY_FAILED": {"retry": "RETRYING"},
}


class MockDeliveryAdapter:
    """模擬通道發送：首次發送時 fail_once 內的通道會失敗，重試即成功。

    這讓 Demo 能穩定展示「送達失敗 → 重試 → 確認」的完整閉環。
    """

    def __init__(self, fail_once: set[str] | None = None):
        self.fail_once = set(fail_once) if fail_once is not None else {"SMS"}
        self._failed_already: set[tuple[str, str]] = set()

    def send(self, notification_id: str, channel: str) -> dict:
        key = (notification_id, channel)
        if channel in self.fail_once and key not in self._failed_already:
            self._failed_already.add(key)
            return {"channel": channel, "status": "DELIVERY_FAILED",
                    "detail": "模擬通道逾時（Demo：重試即成功）"}
        return {"channel": channel, "status": "DELIVERY_CONFIRMED",
                "detail": "模擬送達確認"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class NotificationCenter:
    def __init__(self, adapter: MockDeliveryAdapter | None = None):
        self.adapter = adapter or MockDeliveryAdapter()
        self._store: dict[str, dict] = {}
        self._seq = 0

    # ---- 建立（Coordinator 於 CONTENT_GENERATED 時呼叫） ----

    def create_from_incident(self, incident_state: dict) -> dict:
        self._seq += 1
        noti = incident_state.get("notifications", {})
        policy = ((incident_state.get("confidence") or {}).get("execution_policy") or {}).get(
            "code", "ACTION_PROPOSED"
        )
        if policy == "ACTION_PROPOSED":
            status, channels, history_note = (
                "READY_FOR_APPROVAL", list(CHANNELS), "等待管理者核准"
            )
        elif policy == "HUMAN_CONFIRMATION_REQUIRED":
            status, channels, history_note = (
                "PENDING_CONFIRMATION", ["Dashboard"], "可信度不足，需先人工確認；禁止對外發布"
            )
        else:
            status, channels, history_note = (
                "MONITOR_ONLY", ["Dashboard"], "低可信事件僅供內部監測；禁止對外發布"
            )
        notification = {
            "notification_id": f"NOTI-{datetime.now():%Y%m%d}-{self._seq:03d}",
            "incident_id": incident_state["incident_id"],
            "channels": channels,
            "target_area": "信義計畫區",
            "languages": list((noti.get("messages") or {}).keys()) or ["zh", "en"],
            "cms": noti.get("cms"),
            "messages": noti.get("messages", {}),
            "multilingual_required": noti.get("multilingual_required", False),
            "generated_by": {
                "cms": (noti.get("cms_meta") or {}).get("source"),
                "messages": (noti.get("messages_meta") or {}).get("source"),
            },
            "status": status,
            "deliveries": None,
            "created_at": _now(),
            "history": [
                {"status": "DRAFTED", "at": _now(), "note": "內容由系統生成"},
                {"status": status, "at": _now(), "note": history_note},
            ],
            "execution_policy": policy,
        }
        self._store[notification["notification_id"]] = notification
        return notification

    # ---- 查詢 ----

    def list(self) -> list[dict]:
        return list(self._store.values())

    def get(self, notification_id: str) -> dict:
        if notification_id not in self._store:
            raise KeyError(f"找不到通報 {notification_id}")
        return self._store[notification_id]

    # ---- 生命週期操作 ----

    def _check_transition(self, noti: dict, op: str) -> None:
        allowed = _TRANSITIONS.get(noti["status"], {})
        if op not in allowed:
            raise ValueError(
                f"狀態 {noti['status']} 不允許操作 {op}"
                f"（合法操作：{list(allowed) or '無'}）"
            )

    def approve(self, notification_id: str, operator: str = "commander") -> dict:
        noti = self.get(notification_id)
        self._check_transition(noti, "approve")
        noti["status"] = "APPROVED"
        noti["history"].append(
            {"status": "APPROVED", "at": _now(), "note": f"由 {operator} 核准"}
        )
        return noti

    def dispatch(self, notification_id: str) -> dict:
        noti = self.get(notification_id)
        self._check_transition(noti, "dispatch")
        noti["status"] = "DISPATCHING"
        noti["history"].append({"status": "DISPATCHING", "at": _now(), "note": "開始發送"})
        return self._deliver(noti, noti["channels"])

    def retry(self, notification_id: str) -> dict:
        noti = self.get(notification_id)
        self._check_transition(noti, "retry")
        failed = [d["channel"] for d in (noti["deliveries"] or []) if d["status"] == "DELIVERY_FAILED"]
        noti["status"] = "RETRYING"
        noti["history"].append(
            {"status": "RETRYING", "at": _now(), "note": f"重試失敗通道：{failed}"}
        )
        return self._deliver(noti, failed)

    def _deliver(self, noti: dict, channels: list[str]) -> dict:
        results = {d["channel"]: d for d in (noti["deliveries"] or [])}
        for ch in channels:
            results[ch] = self.adapter.send(noti["notification_id"], ch)
        noti["deliveries"] = [results[ch] for ch in noti["channels"] if ch in results]
        if all(d["status"] == "DELIVERY_CONFIRMED" for d in noti["deliveries"]):
            noti["status"] = "DELIVERY_CONFIRMED"
            note = "全通道送達確認"
        else:
            noti["status"] = "DELIVERY_FAILED"
            failed = [d["channel"] for d in noti["deliveries"] if d["status"] == "DELIVERY_FAILED"]
            note = f"通道失敗：{failed}，可重試"
        noti["history"].append({"status": noti["status"], "at": _now(), "note": note})
        return noti
