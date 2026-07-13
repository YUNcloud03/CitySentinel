"""技術文件 19.3 ETE 測試案例。"""
import pytest

from app.engines.ete_calculator import calculate_ete


def test_critical_at_baseline_saturation_is_60():
    result = calculate_ete("Critical", [0.5])
    assert result["ete_minutes"] == 60
    assert result["congestion_penalty_minutes"] == 0


def test_high_with_08_saturation_is_58():
    result = calculate_ete("High", [0.8])
    assert result["ete_minutes"] == pytest.approx(58.0)


def test_medium_penalty_never_negative():
    result = calculate_ete("Medium", [0.3])
    assert result["congestion_penalty_minutes"] == 0
    assert result["ete_minutes"] == 20


def test_doc_example_critical_086():
    result = calculate_ete("Critical", [0.86])
    assert result["ete_minutes"] == pytest.approx(81.6)


def test_average_over_multiple_segments():
    result = calculate_ete("Critical", [1.0, 0.72])
    assert result["average_saturation"] == pytest.approx(0.86)


def test_unknown_severity_raises():
    with pytest.raises(ValueError):
        calculate_ete("Low", [0.5])


def test_backend_keeps_raw_value_ui_rounds():
    result = calculate_ete("Critical", [0.86])
    assert result["ete_minutes"] == pytest.approx(81.6)  # 後端保留原值
    assert result["ete_minutes_display"] == 82           # UI 四捨五入
