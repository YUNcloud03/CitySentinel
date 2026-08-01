import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main


@pytest.fixture()
def client():
    return TestClient(api_main.app)


def test_simulation_audit_reports_real_source_timeline(client):
    body = client.get("/api/audit/simulation").json()
    assert body["time_range"]["start"] == "2026-05-20 17:00"
    assert body["time_range"]["end"] == "2026-05-20 23:30"
    assert body["time_range"]["timeline_points"] == 19
    assert body["time_range"]["interpolation"] is False
    assert body["initialization"]["front_end_constants_used"] is False
    assert body["name_alignment"]["all_traffic_names_match"] is True
    assert body["reproducibility"]["deterministic"] is True
    assert len(body["reproducibility"]["snapshot_sha256"]) == 64


def test_every_organizer_dataset_has_an_explicit_usage_mapping(client):
    rows = client.get("/api/audit/dataset-usage").json()["datasets"]
    assert {row["file"] for row in rows} == {
        "city_traffic_flow.csv", "signaling_crowd_density.csv", "live_incidents.json",
        "road_network_geometry.json", "emergency_traffic_sop.txt",
    }
    assert all(row["status"] == "used" and row["functions"] and row["fields"] for row in rows)


def test_data_quality_report_reconciles_raw_and_loaded_counts(client):
    body = client.get("/api/audit/data-quality").json()
    assert body["summary"]["silent_drops"] == 0
    traffic = body["datasets"]["city_traffic_flow.csv"]
    crowd = body["datasets"]["signaling_crowd_density.csv"]
    assert traffic["raw_rows"] == traffic["loaded_rows"] == 112
    assert crowd["raw_rows"] == crowd["loaded_rows"] == 36
    assert traffic["road_name_mismatches"] == 0
    assert traffic["duplicate_timestamp_entity_rows"] == 0
    assert crowd["duplicate_timestamp_entity_rows"] == 0
