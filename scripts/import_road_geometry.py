"""Build the challenge's 15 road segments from official Taipei road GIS blocks."""
from __future__ import annotations

import argparse
import csv
import json
import zipfile
from pathlib import Path

from import_map_assets import read_dbf, twd97_to_wgs84


# Bounds deliberately describe the real named road section, not the old demo sketch.
# A segment can combine adjacent official section names where the challenge topology
# crosses a real-world section boundary (notably Keelung Road).
SEGMENTS = {
    "RD_TPE_001": {"names": ("忠孝東路四段",), "axis": 0, "bounds": (121.5436, 25.0408, 121.5646, 25.0420), "controls": ("SJHM710", "SJERC10")},
    "RD_TPE_002": {"names": ("光復南路",), "axis": 1, "bounds": (121.5570, 25.0375, 121.5581, 25.0452), "controls": ("SIKPW10", "SKAPX10")},
    "RD_TPE_003": {"names": ("基隆路一段", "基隆路二段"), "axis": 1, "bounds": (121.5588, 25.0323, 121.5646, 25.0412), "controls": ("SHKQD10", "SJERC10")},
    "RD_TPE_004": {"names": ("市民大道四段",), "axis": 0, "bounds": (121.5436, 25.0442, 121.5579, 25.0452), "controls": ("SK8M710", "SKAPX10")},
    "RD_TPE_005": {"names": ("仁愛路四段",), "axis": 0, "bounds": (121.5486, 25.0370, 121.5638, 25.0381), "controls": ("SIMN810", "SIKR710")},
    # The challenge identifies these as whole named road sections.  Keep the
    # complete official GIS chain instead of clipping it to the original demo
    # viewport; clipping created a false gap between sections 1 and 2 and left
    # only three blocks of Dunhua South Road Section 2 on the map.
    "RD_TPE_006": {"names": ("敦化南路一段",), "axis": 1, "bounds": (121.5484, 25.0331, 121.5492, 25.0450), "controls": ("SIMN810", "SJGPQ10", "SHLN710")},
    "RD_TPE_007": {"names": ("松高路",), "axis": 0, "bounds": (121.5623, 25.0388, 121.5657, 25.0396), "controls": ("SIWR710", "SIWRJ10")},
    "RD_TPE_008": {"names": ("延吉街",), "axis": 1, "bounds": (121.5542, 25.0375, 121.5558, 25.0416), "controls": ("SILPI10", "SJGPC10")},
    "RD_TPE_009": {"names": ("基隆路一段",), "axis": 1, "bounds": (121.5642, 25.0410, 121.5700, 25.0500), "controls": ("SJERC10",)},
    "RD_TPE_010": {"names": ("市府路",), "axis": 1, "bounds": (121.5632, 25.0357, 121.5639, 25.0393), "controls": ("SI9R710", "SIKR710", "SIWR710")},
    "RD_TPE_011": {"names": ("松壽路",), "axis": 0, "bounds": (121.5611, 25.0356, 121.5657, 25.0362), "controls": ("SI9QP10", "SI9R710", "SI9RI10")},
    "RD_TPE_012": {"names": ("敦化南路二段",), "axis": 1, "bounds": (121.5484, 25.0218, 121.5492, 25.0334), "controls": ("SHLN710",)},
    "RD_TPE_013": {"names": ("信義路五段",), "axis": 0, "bounds": (121.5603, 25.0325, 121.5694, 25.0333), "controls": ("SHJRJ10", "SHJS610")},
    "RD_TPE_014": {"names": ("松智路",), "axis": 1, "bounds": (121.5651, 25.0327, 121.5658, 25.0393), "controls": ("SHJRJ10", "SI9RI10", "SIWRJ10")},
    "RD_TPE_015": {"names": ("復興南路一段",), "axis": 1, "bounds": (121.5434, 25.0413, 121.5441, 25.0450), "controls": ("SJHM710", "SK8M710")},
}


def in_bounds(point: tuple[float, float], bounds: tuple[float, float, float, float]) -> bool:
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def read_signal_controls(path: Path) -> dict[str, tuple[float, float]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {
            row["設備編號"].strip(): (float(row["經度"]), float(row["緯度"]))
            for row in csv.DictReader(source)
            if row.get("設備編號") and row.get("經度") and row.get("緯度")
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--road-zip", type=Path, required=True)
    parser.add_argument("--signals-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    controls = read_signal_controls(args.signals_csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Only the DBF is needed. Reading that member explicitly avoids inheriting
    # directory permissions stored in the ZIP and works in restricted builds.
    with zipfile.ZipFile(args.road_zip) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith("road.dbf"))
        rows = read_dbf(archive.read(member))

    features = []
    for segment_id, spec in SEGMENTS.items():
        points = []
        road_ids = []
        for row in rows:
            if row.get("roadname") not in spec["names"]:
                continue
            point = twd97_to_wgs84(float(row["point_x"]), float(row["point_y"]))
            if in_bounds(point, spec["bounds"]):
                points.append(point)
                road_ids.append(row.get("road_id", ""))
        for device_id in spec["controls"]:
            if device_id not in controls:
                raise ValueError(f"Missing official signal control point: {device_id}")
            point = controls[device_id]
            if in_bounds(point, spec["bounds"]):
                points.append(point)
        points = sorted(set(points), key=lambda point: (point[spec["axis"]], point[1 - spec["axis"]]))
        if len(points) < 2:
            raise ValueError(f"{segment_id}: insufficient official geometry points")
        features.append({
            "type": "Feature",
            "id": segment_id,
            "properties": {
                "segment_id": segment_id,
                "source_road_names": list(spec["names"]),
                "source_road_ids": sorted(set(road_ids)),
                "geometry_source": "臺北市政府工務局新建工程處",
            },
            "geometry": {"type": "LineString", "coordinates": [list(point) for point in points]},
        })

    result = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "臺北市寬度超過8公尺道路GIS圖資",
            "source_updated": "2025-09-17",
            "source_url": "https://data.taipei/dataset/detail?id=ee2e4015-8844-48fb-aa57-31209909b0fc",
            "method": "official road-block label points plus official signal intersection control points",
            "crs": "EPSG:4326",
        },
        "features": features,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"roads.json: {len(features)} official-aligned segments")


if __name__ == "__main__":
    main()
