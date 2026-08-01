"""Filter Taipei official signal locations to official-aligned challenge corridors."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


ROAD_ALIASES = {
    "RD_TPE_001": ("忠孝東四段", "忠孝東路四段"),
    "RD_TPE_002": ("光復南路",),
    "RD_TPE_003": ("基隆路一段",),
    "RD_TPE_004": ("市民四段", "市民大道四段"),
    "RD_TPE_005": ("仁愛路四段", "仁愛四段"),
    "RD_TPE_006": ("敦化南一段", "敦化南路一段"),
    "RD_TPE_007": ("松高路",),
    "RD_TPE_008": ("延吉街",),
    "RD_TPE_009": ("基隆路地下道",),
    "RD_TPE_010": ("市府路",),
    "RD_TPE_011": ("松壽路",),
    "RD_TPE_012": ("敦化南二段", "敦化南路二段"),
    "RD_TPE_013": ("信義路五段", "信義五段"),
    "RD_TPE_014": ("松智路",),
    "RD_TPE_015": ("復興南一段", "復興南路一段"),
}


def distance_to_segment_m(point, start, end) -> float:
    lat = math.radians(point[1])
    scale_x, scale_y = 111320 * math.cos(lat), 110540
    px, py = point[0] * scale_x, point[1] * scale_y
    ax, ay = start[0] * scale_x, start[1] * scale_y
    bx, by = end[0] * scale_x, end[1] * scale_y
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / denominator)) if denominator else 0
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def nearest_segment(point, candidates, segments) -> tuple[float, str]:
    return min(
        (distance_to_segment_m(point, coords[i], coords[i + 1]), segment_id)
        for segment_id, coords in segments.items() if segment_id in candidates
        for i in range(len(coords) - 1)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--roads", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corridor-metres", type=float, default=75)
    args = parser.parse_args()

    with args.csv.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    road_data = json.loads(args.roads.read_text(encoding="utf-8"))
    segments = {
        feature["properties"]["segment_id"]: feature["geometry"]["coordinates"]
        for feature in road_data["features"]
    }

    features = []
    seen_devices = set()
    for row in rows:
        try:
            point = (float(row["經度"]), float(row["緯度"]))
        except (KeyError, TypeError, ValueError):
            continue
        intersection_name = row.get("路口名稱", "").strip()
        candidates = {
            segment_id for segment_id, aliases in ROAD_ALIASES.items()
            if any(alias in intersection_name for alias in aliases)
        }
        if not candidates:
            continue
        distance, segment_id = nearest_segment(point, candidates, segments)
        device_id = row.get("設備編號", "").strip()
        if distance > args.corridor_metres or not device_id or device_id in seen_devices:
            continue
        seen_devices.add(device_id)
        features.append({
            "type": "Feature",
            "id": device_id,
            "properties": {
                "icid": row.get("icid", "").strip(),
                "device_id": device_id,
                "name": intersection_name,
                "group": row.get("群組", "").strip(),
                "report_url": row.get("三合一報表連結（網址）", "").strip(),
                "segment_id": segment_id,
                "corridor_distance_m": round(distance, 1),
                "location_source": "臺北市政府交通局",
                "phase_source": "simulation",
            },
            "geometry": {"type": "Point", "coordinates": [point[0], point[1]]},
        })

    output = {
        "type": "FeatureCollection",
        "metadata": {
            "source": args.csv.name,
            "source_updated": "2025-06-09",
            "filter": f"official road-name match and within {args.corridor_metres:g}m of official-aligned challenge road geometry",
            "total_official_records": len(rows),
            "crs": "EPSG:4326",
        },
        "features": features,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"signals.geojson: {len(features)} of {len(rows)} official records")


if __name__ == "__main__":
    main()
