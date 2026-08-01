import { along } from "@turf/along";
import { circle } from "@turf/circle";
import { distance } from "@turf/distance";
import { lineString, point } from "@turf/helpers";
import { length } from "@turf/length";
import { cellToBoundary, latLngToCell } from "h3-js";
import type { IncidentState, SimView } from "./api";

type Coordinate = [number, number];
type RoadFeature = {
  properties: { segment_id: string };
  geometry: { type: "LineString"; coordinates: Coordinate[] };
};

const IMPACT_RADIUS_KM: Record<string, number> = {
  Critical: 0.65,
  High: 0.45,
  Medium: 0.3,
  Low: 0.18,
};

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

export function h3ResolutionForZoom(zoom: number): number {
  if (zoom < 12) return 7;
  if (zoom < 13.5) return 8;
  if (zoom < 15) return 9;
  return 10;
}

export function incidentImpactGeoJSON(
  incident: IncidentState | null,
  coordinate?: Coordinate | null,
  view?: SimView | null,
) {
  if (!incident || !coordinate) {
    return { type: "FeatureCollection" as const, features: [] };
  }
  const severity = String(incident.event.severity ?? "Medium");
  const radiusKm = IMPACT_RADIUS_KM[severity] ?? IMPACT_RADIUS_KM.Medium;
  const feature = circle(point(coordinate), radiusKm, { steps: 48, units: "kilometers" });
  feature.properties = {
    incident_id: incident.incident_id,
    severity,
    radius_m: Math.round(radiusKm * 1000),
    calculation: "@turf/circle",
    radius_policy: "Critical 650m｜High 450m｜Medium 300m｜Low 180m",
    affected_segment: String(incident.event.affected_segment ?? ""),
    changed_segment_ids: view?.simulation_context?.changed_segment_ids?.join(",") ?? "",
    interpretation: "決策提示與推播檢索圈；不是物理災害擴散預測",
  };
  return { type: "FeatureCollection" as const, features: [feature] };
}

export function distanceMeters(from: Coordinate, to: Coordinate): number {
  return Math.round(distance(point(from), point(to), { units: "kilometers" }) * 1000);
}

export function lineMidpointCoordinate(coordinates: Coordinate[]): Coordinate | null {
  if (coordinates.length < 2) return coordinates[0] ?? null;
  const line = lineString(coordinates);
  return along(line, length(line, { units: "kilometers" }) / 2, { units: "kilometers" })
    .geometry.coordinates as Coordinate;
}

export function riskGridGeoJSON(
  view: SimView | null,
  roads: RoadFeature[],
  stations: Record<string, Coordinate>,
  resolution: number,
) {
  const cells = new Map<string, {
    traffic: number[];
    crowd: number[];
    trafficIds: string[];
    stationIds: string[];
    trafficNames: string[];
    stationNames: string[];
  }>();
  const bucket = (cell: string) => {
    if (!cells.has(cell)) cells.set(cell, {
      traffic: [], crowd: [], trafficIds: [], stationIds: [], trafficNames: [], stationNames: [],
    });
    return cells.get(cell)!;
  };

  for (const road of roads) {
    const segmentId = road.properties.segment_id;
    const traffic = view?.traffic?.[segmentId];
    if (!traffic || road.geometry.coordinates.length < 2) continue;
    const [lng, lat] = lineMidpointCoordinate(road.geometry.coordinates)!;
    const cell = latLngToCell(lat, lng, resolution);
    const item = bucket(cell);
    item.traffic.push(clamp01(traffic.saturation_score / 1.05));
    item.trafficIds.push(segmentId);
    item.trafficNames.push(traffic.road_name || (road.properties as any).name || segmentId);
  }

  for (const [stationId, [lng, lat]] of Object.entries(stations)) {
    const crowd = view?.crowd?.[stationId];
    if (!crowd) continue;
    const load = clamp01(crowd.user_count / 40_000);
    const growth = clamp01(Math.abs(crowd.growth_rate) / 0.5);
    const roaming = clamp01(crowd.roaming_user_pct / 45);
    const item = bucket(latLngToCell(lat, lng, resolution));
    item.crowd.push(0.55 * load + 0.25 * growth + 0.2 * roaming);
    item.stationIds.push(stationId);
    item.stationNames.push(crowd.location_name || stationId);
  }

  const features = [...cells.entries()].map(([cell, values]) => {
    const trafficRisk = values.traffic.length ? Math.max(...values.traffic) : 0;
    const crowdRisk = values.crowd.length ? Math.max(...values.crowd) : 0;
    const risk = Math.round(Math.max(trafficRisk, crowdRisk) * 1000) / 1000;
    const boundary = cellToBoundary(cell, true) as Coordinate[];
    return {
      type: "Feature" as const,
      properties: {
        h3_index: cell,
        h3_resolution: resolution,
        risk,
        traffic_risk: Math.round(trafficRisk * 1000) / 1000,
        crowd_risk: Math.round(crowdRisk * 1000) / 1000,
        level: risk >= 0.9 ? "高" : risk >= 0.7 ? "中" : "低",
        traffic_entities: values.trafficIds.join(","),
        crowd_entities: values.stationIds.join(","),
        traffic_names: [...new Set(values.trafficNames)].join("、"),
        crowd_names: [...new Set(values.stationNames)].join("、"),
        calculation: "max(traffic_saturation/1.05, 0.55×people_load + 0.25×growth + 0.20×roaming)",
      },
      geometry: { type: "Polygon" as const, coordinates: [boundary] },
    };
  });
  return { type: "FeatureCollection" as const, features };
}
