"""技術文件 19.1 Rule Engine 測試案例。"""
from datetime import datetime

from app.data_loader import CrowdRecord
from app.engines import rule_engine

AT = datetime(2026, 5, 20, 22, 0)


def _crowd(bs_id="BS_MRT_BL17", user_count=1000, growth_rate=0.0, roaming=5.0):
    return CrowdRecord(
        timestamp=AT, bs_id=bs_id, location_name="test", user_count=user_count,
        stay_time_avg=30, growth_rate=growth_rate, roaming_user_pct=roaming,
    )


# 壅塞分級邊界

def test_saturation_084_is_normal():
    assert rule_engine.classify_congestion(0.84) == "Normal"


def test_saturation_085_is_level_b():
    assert rule_engine.classify_congestion(0.85) == "B"


def test_saturation_095_is_level_a():
    assert rule_engine.classify_congestion(0.95) == "A"


# SOP 3：BL17 門檻

def test_bl17_user_count_25001_triggers_rule_3():
    rec = _crowd(user_count=25_001)
    triggers = rule_engine.evaluate_crowd({rec.bs_id: rec}, [rec], AT)
    assert 3 in {t["rule_id"] for t in triggers}


def test_bl17_user_count_25000_not_trigger():
    rec = _crowd(user_count=25_000)
    triggers = rule_engine.evaluate_crowd({rec.bs_id: rec}, [rec], AT)
    assert 3 not in {t["rule_id"] for t in triggers}


def test_bl17_growth_031_triggers_rule_3():
    rec = _crowd(growth_rate=0.31)
    triggers = rule_engine.evaluate_crowd({rec.bs_id: rec}, [rec], AT)
    assert 3 in {t["rule_id"] for t in triggers}


def test_generic_station_growth_050_triggers_crowd_policy():
    rec = _crowd(bs_id="BS_XY_ATT", user_count=18_000, growth_rate=0.50)
    triggers = rule_engine.evaluate_crowd({rec.bs_id: rec}, [rec], AT)
    trigger = next(t for t in triggers if t["rule_id"] == 3)
    assert trigger["entity_id"] == "BS_XY_ATT"
    assert trigger["evidence"]["policy_code"] == "CROWD_GROWTH_5M_50"


def test_generic_station_growth_below_050_stays_monitoring():
    rec = _crowd(bs_id="BS_XY_ATT", user_count=18_000, growth_rate=0.49)
    triggers = rule_engine.evaluate_crowd({rec.bs_id: rec}, [rec], AT)
    assert 3 not in {t["rule_id"] for t in triggers}


# SOP 4：大巨蛋散場（峰值 + 負成長需同時成立）

def test_dome_dispersal_requires_both_conditions():
    peak = _crowd(bs_id="BS_TPE_DOME", user_count=35_000, growth_rate=1.0)
    now = _crowd(bs_id="BS_TPE_DOME", user_count=22_000, growth_rate=-0.31)
    triggers = rule_engine.evaluate_crowd({now.bs_id: now}, [peak, now], AT)
    assert 4 in {t["rule_id"] for t in triggers}

    # 峰值不足 30,000 時不觸發
    low_peak = _crowd(bs_id="BS_TPE_DOME", user_count=29_999, growth_rate=1.0)
    triggers = rule_engine.evaluate_crowd({now.bs_id: now}, [low_peak, now], AT)
    assert 4 not in {t["rule_id"] for t in triggers}


# SOP 6：漫遊率門檻（>= 30% 含邊界）

def test_roaming_30_pct_triggers_rule_6():
    rec = _crowd(bs_id="BS_TPE_101", roaming=30.0)
    triggers = rule_engine.evaluate_crowd({rec.bs_id: rec}, [rec], AT)
    assert 6 in {t["rule_id"] for t in triggers}


def test_roaming_29_pct_not_trigger():
    rec = _crowd(bs_id="BS_TPE_101", roaming=29.9)
    triggers = rule_engine.evaluate_crowd({rec.bs_id: rec}, [rec], AT)
    assert 6 not in {t["rule_id"] for t in triggers}


# SOP 2 / SOP 5：事件判定

def test_rule_2_requires_all_three_conditions():
    base = {"status": "Closed", "severity": "Critical", "affected_segment": "RD_TPE_002",
            "type": "Road_Collapse_Accident", "description": ""}
    assert 2 in {t["rule_id"] for t in rule_engine.evaluate_incident(base)}
    # BS_ 開頭改由第 3 條處理，不觸發第 2 條
    bs_event = base | {"affected_segment": "BS_MRT_BL17"}
    assert 2 not in {t["rule_id"] for t in rule_engine.evaluate_incident(bs_event)}
    # severity Medium 不觸發
    medium = base | {"severity": "Medium"}
    assert 2 not in {t["rule_id"] for t in rule_engine.evaluate_incident(medium)}


def test_rule_5_power_failure_or_keyword():
    by_type = {"type": "Power_Failure", "status": "Caution", "severity": "Medium",
               "affected_segment": "RD_TPE_007", "description": ""}
    assert 5 in {t["rule_id"] for t in rule_engine.evaluate_incident(by_type)}
    by_keyword = {"type": "Other", "status": "Caution", "severity": "Medium",
                  "affected_segment": "RD_TPE_007", "description": "部分路段號誌失效"}
    assert 5 in {t["rule_id"] for t in rule_engine.evaluate_incident(by_keyword)}
