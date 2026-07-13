"""What-if 自然語言解析測試。"""
import pytest

from app.coordinator.whatif_nl import parse_question


def test_bl17_user_count_40000():
    s = parse_question("如果 BL17 人數增加到 40000 人會怎樣？")
    assert s["crowd_overrides"]["BS_MRT_BL17"]["user_count"] == 40_000
    assert s["at"] == "2026-05-20 22:00"  # 預設時間切面


def test_wan_multiplier_and_alias():
    s = parse_question("假設國父紀念館站人數 4萬")
    assert s["crowd_overrides"]["BS_MRT_BL17"]["user_count"] == 40_000


def test_roaming_pct():
    s = parse_question("假設台北101漫遊率 50%")
    assert s["crowd_overrides"]["BS_TPE_101"]["roaming_user_pct"] == 50.0


def test_time_in_question():
    s = parse_question("如果 21:15 光復南路飽和度 0.99")
    assert s["at"] == "2026-05-20 21:15"
    assert s["traffic_overrides"]["RD_TPE_002"]["saturation_score"] == 0.99


def test_road_closure_becomes_simulated_incident():
    s = parse_question("如果封閉忠孝東路會怎樣？")
    sim = s["simulated_incident"]
    assert sim["affected_segment"] == "RD_TPE_001"
    assert sim["status"] == "Closed" and sim["severity"] == "Critical"


def test_growth_rate_negative():
    s = parse_question("如果大巨蛋成長率變成 -0.5？")
    assert s["crowd_overrides"]["BS_TPE_DOME"]["growth_rate"] == -0.5


def test_longer_alias_wins():
    s = parse_question("如果敦化南路二段飽和度 0.9")
    assert "RD_TPE_012" in s["traffic_overrides"]


def test_unparseable_raises():
    with pytest.raises(ValueError):
        parse_question("今天天氣如何？")
