import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _distance_to_segment_m(point, start, end):
    lat = math.radians(point[1])
    scale_x, scale_y = 111320 * math.cos(lat), 110540
    px, py = point[0] * scale_x, point[1] * scale_y
    ax, ay = start[0] * scale_x, start[1] * scale_y
    bx, by = end[0] * scale_x, end[1] * scale_y
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / denominator)) if denominator else 0
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def test_official_road_geometry_has_all_challenge_segments():
    data = json.loads((ROOT / "frontend/src/data/roads.json").read_text(encoding="utf-8"))
    features = data["features"]
    assert len(features) == 15
    assert {feature["properties"]["segment_id"] for feature in features} == {
        f"RD_TPE_{number:03d}" for number in range(1, 16)
    }
    assert data["metadata"]["source"] == "臺北市寬度超過8公尺道路GIS圖資"
    assert all(len(feature["geometry"]["coordinates"]) >= 2 for feature in features)


def test_keelung_junction_uses_official_signal_coordinate():
    data = json.loads((ROOT / "frontend/src/data/roads.json").read_text(encoding="utf-8"))
    roads = {
        feature["properties"]["segment_id"]: feature["geometry"]["coordinates"]
        for feature in data["features"]
    }
    official_junction = [121.564465, 25.041144]
    assert official_junction in roads["RD_TPE_001"]
    assert official_junction in roads["RD_TPE_003"]
    assert official_junction in roads["RD_TPE_009"]
    assert [121.567, 25.0416] not in roads["RD_TPE_001"]


def test_dunhua_sections_use_the_complete_official_named_sections():
    data = json.loads((ROOT / "frontend/src/data/roads.json").read_text(encoding="utf-8"))
    roads = {
        feature["properties"]["segment_id"]: feature["geometry"]["coordinates"]
        for feature in data["features"]
    }

    # Section 1 reaches south of Renai Road and section 2 continues past
    # Heping East Road.  These bounds prevent the old viewport clipping from
    # silently turning either organizer road ID into a short demo fragment.
    assert min(point[1] for point in roads["RD_TPE_006"]) < 25.034
    assert min(point[1] for point in roads["RD_TPE_012"]) < 25.023
    assert len(roads["RD_TPE_006"]) >= 10
    assert len(roads["RD_TPE_012"]) >= 8
    assert [121.548802, 25.033249] in roads["RD_TPE_006"]
    assert [121.548802, 25.033249] in roads["RD_TPE_012"]


def test_each_selected_signal_is_within_declared_corridor():
    roads_data = json.loads((ROOT / "frontend/src/data/roads.json").read_text(encoding="utf-8"))
    signals_data = json.loads((ROOT / "frontend/public/data/signals.geojson").read_text(encoding="utf-8"))
    roads = {
        feature["properties"]["segment_id"]: feature["geometry"]["coordinates"]
        for feature in roads_data["features"]
    }
    for signal in signals_data["features"]:
        point = signal["geometry"]["coordinates"]
        coords = roads[signal["properties"]["segment_id"]]
        distance = min(
            _distance_to_segment_m(point, coords[index], coords[index + 1])
            for index in range(len(coords) - 1)
        )
        assert distance <= 75.1, (signal["properties"]["device_id"], distance)
