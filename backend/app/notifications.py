"""通報內容生成（確定性模板版）。

依技術文件 20.3：即使 LLM 失敗，仍須以模板產出 CMS 與多語訊息，
因此模板為第一層實作；LLM 潤飾屬 Phase 2 加分。
時間格式統一 YYYY-MM-DD HH:MM（SOP 第 6 條）。
"""
from __future__ import annotations

from datetime import datetime

from .data_loader import format_ts


def cms_reroute_message(
    affected_name: str, primary_name: str | None, ete_minutes_display: int
) -> str:
    """SOP 第 2 條 CMS 格式。"""
    if primary_name is None:
        return f"{affected_name}封閉，請依現場指揮改道，預計延誤 {ete_minutes_display} 分鐘"
    return f"{affected_name}封閉，請改道 {primary_name}，預計延誤 {ete_minutes_display} 分鐘"


def cms_signal_failure_note(road_name: str) -> str:
    """SOP 第 5 條 CMS 加註。"""
    return f"{road_name} 號誌故障，請依現場指揮通行"


def multilingual_reroute(
    affected_name: str,
    affected_name_en: str,
    primary_name: str | None,
    primary_name_en: str | None,
    ete_minutes_display: int,
    at: datetime,
) -> dict[str, str]:
    """SOP 第 6 條：中英必做、日韓加分，同一回應內產出。"""
    ts = format_ts(at)
    if primary_name:
        return {
            "zh": f"[{ts}] {affected_name}封閉，請改道 {primary_name}，預計延誤 {ete_minutes_display} 分鐘。",
            "en": f"[{ts}] {affected_name_en} is closed. Please detour via {primary_name_en}. Expected delay: {ete_minutes_display} minutes.",
            "ja": f"[{ts}] {affected_name}は通行止めです。{primary_name}へ迂回してください。予想遅延：約{ete_minutes_display}分。",
            "ko": f"[{ts}] {affected_name}이(가) 통제 중입니다. {primary_name}(으)로 우회하시기 바랍니다. 예상 지연: 약 {ete_minutes_display}분.",
        }
    return {
        "zh": f"[{ts}] {affected_name}交通管制中，請依現場指揮通行。",
        "en": f"[{ts}] Traffic control in effect at {affected_name_en}. Please follow on-site instructions.",
        "ja": f"[{ts}] {affected_name}は交通規制中です。現場の指示に従ってください。",
        "ko": f"[{ts}] {affected_name} 교통 통제 중입니다. 현장 안내에 따라 주시기 바랍니다.",
    }


# 路段英文名（主辦資料無英文名，Demo 用固定對照表）
ROAD_NAME_EN = {
    "RD_TPE_001": "Zhongxiao E. Rd. Sec. 4",
    "RD_TPE_002": "Guangfu S. Rd.",
    "RD_TPE_003": "Keelung Rd. Sec. 1",
    "RD_TPE_004": "Civic Blvd. Sec. 4",
    "RD_TPE_005": "Ren'ai Rd. Sec. 4",
    "RD_TPE_006": "Dunhua S. Rd. Sec. 1",
    "RD_TPE_007": "Songgao Rd.",
    "RD_TPE_008": "Yanji St.",
    "RD_TPE_009": "Keelung Rd. Underpass",
    "RD_TPE_010": "Shifu Rd.",
    "RD_TPE_011": "Songshou Rd.",
    "RD_TPE_012": "Dunhua S. Rd. Sec. 2",
    "RD_TPE_013": "Xinyi Rd. Sec. 5",
    "RD_TPE_014": "Songzhi Rd.",
    "RD_TPE_015": "Fuxing S. Rd. Sec. 1",
}
