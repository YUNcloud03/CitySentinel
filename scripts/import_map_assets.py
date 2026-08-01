"""Convert Taipei crosswalk Shapefiles and CMS XML into compact GeoJSON assets.

Uses only the Python standard library so the import is reproducible without GDAL.
Crosswalk input must use TWD97 / TM2 zone 121 (EPSG:3826).
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def twd97_to_wgs84(x: float, y: float) -> tuple[float, float]:
    a, b = 6378137.0, 6356752.314140356
    lon0, k0, dx = math.radians(121.0), 0.9999, 250000.0
    e = math.sqrt(1 - (b * b) / (a * a))
    e2 = e * e / (1 - e * e)
    m = y / k0
    mu = m / (a * (1 - e**2 / 4 - 3 * e**4 / 64 - 5 * e**6 / 256))
    e1 = (1 - math.sqrt(1 - e**2)) / (1 + math.sqrt(1 - e**2))
    fp = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + 151 * e1**3 / 96 * math.sin(6 * mu)
        + 1097 * e1**4 / 512 * math.sin(8 * mu)
    )
    c1, t1 = e2 * math.cos(fp) ** 2, math.tan(fp) ** 2
    n1 = a / math.sqrt(1 - e**2 * math.sin(fp) ** 2)
    r1 = a * (1 - e**2) / (1 - e**2 * math.sin(fp) ** 2) ** 1.5
    d = (x - dx) / (n1 * k0)
    lat = fp - (n1 * math.tan(fp) / r1) * (
        d**2 / 2
        - (5 + 3*t1 + 10*c1 - 4*c1**2 - 9*e2) * d**4 / 24
        + (61 + 90*t1 + 298*c1 + 45*t1**2 - 252*e2 - 3*c1**2) * d**6 / 720
    )
    lon = lon0 + (
        d - (1 + 2*t1 + c1) * d**3 / 6
        + (5 - 2*c1 + 28*t1 - 3*c1**2 + 8*e2 + 24*t1**2) * d**5 / 120
    ) / math.cos(fp)
    return round(math.degrees(lon), 7), round(math.degrees(lat), 7)


def read_dbf(source: Path | bytes) -> list[dict[str, str]]:
    raw = source if isinstance(source, bytes) else source.read_bytes()
    row_count = struct.unpack_from("<I", raw, 4)[0]
    header_len, row_len = struct.unpack_from("<HH", raw, 8)
    fields, pos = [], 32
    while pos < header_len and raw[pos] != 0x0D:
        fields.append((
            raw[pos:pos+11].split(b"\0", 1)[0].decode("ascii", "replace").lower(),
            raw[pos+16],
        ))
        pos += 32
    rows = []
    for i in range(row_count):
        row = raw[header_len + i*row_len: header_len + (i+1)*row_len]
        cursor, values = 1, {}
        for name, length in fields:
            values[name] = row[cursor:cursor+length].decode("utf-8", "replace").strip()
            cursor += length
        rows.append(values)
    return rows


def read_polygon_shp(path: Path) -> list[list[list[list[float]]]]:
    raw, offset, shapes = path.read_bytes(), 100, []
    while offset + 8 <= len(raw):
        _, words = struct.unpack_from(">2i", raw, offset)
        content = raw[offset + 8: offset + 8 + words * 2]
        shape_type = struct.unpack_from("<i", content, 0)[0]
        if shape_type != 5:
            raise ValueError(f"{path.name}: expected Polygon (5), got {shape_type}")
        num_parts, num_points = struct.unpack_from("<2i", content, 36)
        part_starts = list(struct.unpack_from(f"<{num_parts}i", content, 44))
        point_offset = 44 + num_parts * 4
        points = [
            twd97_to_wgs84(*struct.unpack_from("<2d", content, point_offset + i * 16))
            for i in range(num_points)
        ]
        rings = []
        for index, start in enumerate(part_starts):
            end = part_starts[index + 1] if index + 1 < len(part_starts) else num_points
            ring = [list(point) for point in points[start:end]]
            if ring and ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append(ring)
        shapes.append(rings)
        offset += 8 + words * 2
    return shapes


def build_crosswalks(root: Path) -> dict:
    features = []
    for shp_path in sorted(root.rglob("*.shp")):
        dbf_path = shp_path.with_suffix(".dbf")
        if not dbf_path.exists():
            raise FileNotFoundError(f"Missing companion DBF: {dbf_path}")
        shapes, rows = read_polygon_shp(shp_path), read_dbf(dbf_path)
        if len(shapes) != len(rows):
            raise ValueError(f"Geometry/attribute mismatch: {shp_path}")
        for index, (rings, row) in enumerate(zip(shapes, rows)):
            features.append({
                "type": "Feature",
                "id": f"{shp_path.stem}-{row.get('keyid') or index}",
                "properties": {
                    "keyid": row.get("keyid", ""),
                    "licode": row.get("licode", shp_path.stem.rsplit("_", 1)[-1]),
                    "kind": "斑馬紋" if row.get("licode", "").endswith("9") else "枕木紋",
                    "length": row.get("rdlblg", ""),
                    "width": row.get("rdlbwt", ""),
                    "updated": row.get("edittime", ""),
                    "source_layer": shp_path.stem,
                },
                "geometry": {"type": "Polygon", "coordinates": rings},
            })
    return {
        "type": "FeatureCollection",
        "metadata": {"source": "臺北市交通管制工程處行人穿越線圖資", "crs": "EPSG:4326"},
        "features": features,
    }


def build_cms(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        root = ET.fromstring(response.read())
    namespace = {"t": "http://traffic.transportdata.tw/standard/traffic/schema/"}
    updated = root.findtext("t:UpdateTime", "", namespace)
    features = []
    for cms in root.findall(".//t:CMS", namespace):
        def value(name: str) -> str:
            return cms.findtext(f"t:{name}", "", namespace)
        features.append({
            "type": "Feature",
            "id": value("CMSID"),
            "properties": {
                "cms_id": value("CMSID"), "link_id": value("LinkID"),
                "road_id": value("RoadID"), "road_name": value("RoadName"),
                "direction": value("RoadDirection"), "location_type": value("LocationType"),
            },
            "geometry": {"type": "Point", "coordinates": [float(value("PositionLon")), float(value("PositionLat"))]},
        })
    return {
        "type": "FeatureCollection",
        "metadata": {"source": url, "updated": updated, "crs": "EPSG:4326"},
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crosswalk-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cms-url", default="https://tcgbusfs.blob.core.windows.net/blobtisv/CMS.xml")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    assets = {
        "crosswalks.geojson": build_crosswalks(args.crosswalk_root),
        "cms.geojson": build_cms(args.cms_url),
    }
    for filename, data in assets.items():
        (args.output_dir / filename).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print(f"{filename}: {len(data['features'])} features")


if __name__ == "__main__":
    main()
