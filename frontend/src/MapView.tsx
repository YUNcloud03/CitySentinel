import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { useState } from "react";
import type { GreenCorridorResult, IncidentState, SimView } from "./api";
import officialRoadGeometry from "./data/roads.json";
import {
  INCIDENT_COORDS,
  STATION_COORDS,
} from "./geometry";
import {
  distanceMeters,
  h3ResolutionForZoom,
  incidentImpactGeoJSON,
  lineMidpointCoordinate,
  riskGridGeoJSON,
} from "./geoAnalytics";

type AssetLayer = "crosswalks" | "signals" | "cms" | "hospitals" | "risk";
export type ComparisonMode = "baseline" | "event" | "current";

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function signalPhase(view: SimView | null, offset: number) {
  const index = view?.progress?.index ?? 0;
  const clock = (index * 7 + offset) % 75;
  if (clock < 35) return { phase: "green", remaining: 35 - clock, label: "綠燈" };
  if (clock < 40) return { phase: "yellow", remaining: 40 - clock, label: "黃燈" };
  return { phase: "red", remaining: 75 - clock, label: "紅燈" };
}

function signalOffset(deviceId: string) {
  return [...deviceId].reduce((total, char) => total + char.charCodeAt(0), 0) % 75;
}

type OfficialSignalFeature = {
  properties: {
    device_id: string;
    name: string;
    group?: string;
    report_url?: string;
    segment_id: string;
  };
  geometry: { type: "Point"; coordinates: [number, number] };
};

type OfficialRoadFeature = {
  properties: { segment_id: string; name: string };
  geometry: { type: "LineString"; coordinates: [number, number][] };
};

const OFFICIAL_ROADS = officialRoadGeometry.features as unknown as OfficialRoadFeature[];

function organizerRoadBounds(): [[number, number], [number, number]] {
  const coordinates = OFFICIAL_ROADS.flatMap((feature) => feature.geometry.coordinates);
  return [
    [Math.min(...coordinates.map(([lng]) => lng)), Math.min(...coordinates.map(([, lat]) => lat))],
    [Math.max(...coordinates.map(([lng]) => lng)), Math.max(...coordinates.map(([, lat]) => lat))],
  ];
}

const ORGANIZER_ROAD_BOUNDS = organizerRoadBounds();
const ORGANIZER_OVERVIEW_OPTIONS: maplibregl.FitBoundsOptions = {
  padding: { top: 64, right: 64, bottom: 142, left: 64 },
  maxZoom: 13.1,
  animate: false,
};

function fitOrganizerRoadOverview(map: maplibregl.Map, animate = false) {
  map.fitBounds(ORGANIZER_ROAD_BOUNDS, {
    ...ORGANIZER_OVERVIEW_OPTIONS,
    animate,
    duration: animate ? 550 : 0,
  });
}

type HospitalFeature = {
  properties: { name: string; address: string; source: string; source_url?: string };
  geometry: { type: "Point"; coordinates: [number, number] };
};

function coordinateForIncident(incident: IncidentState | null): [number, number] | null {
  if (!incident) return null;
  const known = INCIDENT_COORDS[incident.incident_id];
  if (known) return known;
  const segmentId = String(incident.event.affected_segment ?? "");
  const road = OFFICIAL_ROADS.find((feature) => feature.properties.segment_id === segmentId);
  return road ? lineMidpointCoordinate(road.geometry.coordinates) : null;
}

const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors © CARTO",
    },
  },
  layers: [{ id: "carto", type: "raster", source: "carto" }],
};

function roadsGeoJSON(
  view: SimView | null,
  incident: IncidentState | null,
  projectedTraffic?: Record<string, any> | null,
  selectedSegmentId?: string | null,
  greenCorridor?: GreenCorridorResult | null,
  comparisonMode: ComparisonMode = "current",
) {
  const routing = view?.simulation_context?.dynamic_routing ?? incident?.routing_result;
  const primaryId = routing?.primary_route?.segment_id;
  const secondaryIds = new Set<string>(
    (routing?.secondary_routes ?? []).map((s: any) => s.segment_id)
  );
  const closedId = routing?.affected_segment?.segment_id;
  const corridorIds = new Set(greenCorridor?.route_segment_ids ?? []);
  const corridorBlockedIds = new Set(greenCorridor?.blocked_segment_ids ?? []);

  return {
    type: "FeatureCollection" as const,
    features: OFFICIAL_ROADS.map((road) => {
      const segId = road.properties.segment_id;
      const source = projectedTraffic?.[segId] ?? view?.traffic?.[segId];
      const t = source && comparisonMode === "baseline"
        ? {
            ...source,
            avg_speed: source.baseline_avg_speed ?? source.avg_speed,
            vehicle_count: source.baseline_vehicle_count ?? source.vehicle_count,
            saturation_score: source.baseline_saturation_score ?? source.saturation_score,
          }
        : source && comparisonMode === "event"
          ? {
              ...source,
              avg_speed: source.event_avg_speed ?? source.avg_speed,
              vehicle_count: source.event_vehicle_count ?? source.vehicle_count,
              saturation_score: source.event_saturation_score ?? source.saturation_score,
            }
          : source;
      const saturation = t?.saturation_score ?? -1;
      const displayLevel = saturation >= .95 ? "A" : saturation >= .85 ? "B" : saturation >= 0 ? "Normal" : "NoData";
      const comparisonChanged = source?.event_saturation_score != null;
      let role = "none";
      if (segId === closedId) role = "closed";
      else if (segId === primaryId) role = "primary";
      else if (secondaryIds.has(segId)) role = "secondary";
      return {
        type: "Feature" as const,
        properties: {
          segment_id: segId,
          name: t?.road_name ?? road.properties.name,
          sat: t?.saturation_score ?? -1,
          level: displayLevel,
          speed: t?.avg_speed ?? null,
          baseline_speed: t?.baseline_avg_speed ?? null,
          baseline_sat: t?.baseline_saturation_score ?? null,
          event_speed: source?.event_avg_speed ?? null,
          event_sat: source?.event_saturation_score ?? null,
          current_speed: source?.avg_speed ?? null,
          role,
          selected: segId === selectedSegmentId,
          simulated: Boolean(projectedTraffic?.[segId]) || t?.simulation_source === "incident_projection",
          corridor: corridorIds.has(segId),
          corridor_approved: greenCorridor?.approval_status === "APPROVED_FOR_SIMULATION" && corridorIds.has(segId),
          corridor_blocked: corridorBlockedIds.has(segId),
          comparison_mode: comparisonMode,
          comparison_changed: comparisonChanged,
          comparison_active: Boolean(view?.simulation_context?.active),
        },
        geometry: road.geometry,
      };
    }),
  };
}

function stationsGeoJSON(view: SimView | null) {
  return {
    type: "FeatureCollection" as const,
    features: Object.entries(STATION_COORDS).map(([bsId, coord]) => {
      const c = view?.crowd?.[bsId];
      return {
        type: "Feature" as const,
        properties: {
          bs_id: bsId,
          name: c?.location_name ?? bsId,
          users: c?.user_count ?? 0,
          growth: c?.growth_rate ?? 0,
          roaming: c?.roaming_user_pct ?? 0,
        },
        geometry: { type: "Point" as const, coordinates: coord },
      };
    }),
  };
}

function incidentGeoJSON(incident: IncidentState | null) {
  if (!incident) return { type: "FeatureCollection" as const, features: [] };
  const coord = coordinateForIncident(incident);
  if (!coord) return { type: "FeatureCollection" as const, features: [] };
  return {
    type: "FeatureCollection" as const,
    features: [
      {
        type: "Feature" as const,
        properties: { id: incident.incident_id, type: incident.event.type },
        geometry: { type: "Point" as const, coordinates: coord },
      },
    ],
  };
}

function corridorGeoJSON(greenCorridor?: GreenCorridorResult | null) {
  return {
    type: "FeatureCollection" as const,
    features: greenCorridor?.route_geometry?.length
      ? [{
          type: "Feature" as const,
          properties: { approved: greenCorridor.approval_status === "APPROVED_FOR_SIMULATION" },
          geometry: { type: "LineString" as const, coordinates: greenCorridor.route_geometry },
        }]
      : [],
  };
}

export default function MapView({
  view,
  incident,
  projectedTraffic,
  greenCorridor,
  selectedSegmentId,
  onSelectSegment,
  comparisonMode: controlledComparisonMode,
  onComparisonModeChange,
  onScenarioRendered,
}: {
  view: SimView | null;
  incident: IncidentState | null;
  projectedTraffic?: Record<string, any> | null;
  greenCorridor?: GreenCorridorResult | null;
  selectedSegmentId?: string | null;
  onSelectSegment?: (segmentId: string) => void;
  comparisonMode?: ComparisonMode;
  onComparisonModeChange?: (mode: ComparisonMode) => void;
  onScenarioRendered?: (incidentId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  const readyRef = useRef(false);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const markerIncidentRef = useRef<string | null>(null);
  const ambulanceMarkerRef = useRef<maplibregl.Marker | null>(null);
  const signalMarkersRef = useRef<{ marker: maplibregl.Marker; element: HTMLButtonElement; offset: number; deviceId: string }[]>([]);
  const hospitalMarkersRef = useRef<{ marker: maplibregl.Marker; element: HTMLButtonElement }[]>([]);
  const renderedIncidentRef = useRef<string | null>(null);
  const scenarioRenderedCallbackRef = useRef(onScenarioRendered);
  scenarioRenderedCallbackRef.current = onScenarioRendered;
  const selectRef = useRef(onSelectSegment);
  selectRef.current = onSelectSegment;
  const [assetLayers, setAssetLayers] = useState<Record<AssetLayer, boolean>>({
    crosswalks: false,
    signals: true,
    cms: false,
    hospitals: false,
    risk: false,
  });
  const [localComparisonMode, setLocalComparisonMode] = useState<ComparisonMode>("current");
  const comparisonMode = controlledComparisonMode ?? localComparisonMode;
  const setComparisonMode = (mode: ComparisonMode) => {
    setLocalComparisonMode(mode);
    onComparisonModeChange?.(mode);
  };
  const [layersCollapsed, setLayersCollapsed] = useState(true);
  const assetLayersRef = useRef(assetLayers);
  assetLayersRef.current = assetLayers;
  const [signalCount, setSignalCount] = useState(0);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      bounds: ORGANIZER_ROAD_BOUNDS,
      fitBoundsOptions: ORGANIZER_OVERVIEW_OPTIONS,
      attributionControl: { compact: true },
    });
    map.scrollZoom.enable();
    map.doubleClickZoom.enable();
    map.dragPan.enable();
    map.touchZoomRotate.enable();
    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }), "bottom-right");
    mapRef.current = map;

    map.on("load", () => {
      window.requestAnimationFrame(() => {
        if (disposed) return;
        map.resize();
        fitOrganizerRoadOverview(map);
      });
      map.addSource("roads", { type: "geojson", data: roadsGeoJSON(null, null) });
      map.addSource("corridor-route", { type: "geojson", data: corridorGeoJSON(null) });
      map.addSource("stations", { type: "geojson", data: stationsGeoJSON(null) });
      map.addSource("incident", { type: "geojson", data: incidentGeoJSON(null) });
      map.addSource("incident-impact", { type: "geojson", data: incidentImpactGeoJSON(null) });
      map.addSource("risk-grid", {
        type: "geojson",
        data: riskGridGeoJSON(
          viewRef.current,
          OFFICIAL_ROADS,
          STATION_COORDS,
          h3ResolutionForZoom(map.getZoom()),
        ),
      });
      map.addSource("crosswalks", { type: "geojson", data: "/data/crosswalks.geojson" });
      map.addSource("cms-assets", { type: "geojson", data: "/data/cms.geojson" });

      map.addLayer({
        id: "risk-grid-fill",
        type: "fill",
        source: "risk-grid",
        minzoom: 10,
        maxzoom: 17,
        layout: { visibility: "none" },
        paint: {
          "fill-color": ["interpolate", ["linear"], ["get", "risk"],
            0, "#17344f", .7, "#f5a623", .9, "#e5484d", 1, "#ff1738"],
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 10, .12, 14, .28, 17, .08],
        },
      });
      map.addLayer({
        id: "risk-grid-line",
        type: "line",
        source: "risk-grid",
        minzoom: 10,
        maxzoom: 17,
        layout: { visibility: "none" },
        paint: { "line-color": "#7bb7e8", "line-width": 1, "line-opacity": .28 },
      });
      map.addLayer({
        id: "incident-impact-fill",
        type: "fill",
        source: "incident-impact",
        paint: { "fill-color": "#e5484d", "fill-opacity": .1 },
      });
      map.addLayer({
        id: "incident-impact-line",
        type: "line",
        source: "incident-impact",
        paint: { "line-color": "#ff6b72", "line-width": 2, "line-dasharray": [2, 1.5], "line-opacity": .75 },
      });

      // 臺北市交工處行穿線：以官方 Polygon 呈現，縮放至街廓層級才顯示細節。
      map.addLayer({
        id: "crosswalk-fill",
        type: "fill",
        source: "crosswalks",
        minzoom: 14,
        layout: { visibility: "none" },
        paint: {
          "fill-color": ["case", ["==", ["get", "kind"], "斑馬紋"], "#ffffff", "#d8dee9"],
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 14, 0.38, 16, 0.82],
          "fill-outline-color": "#ffffff",
        },
      });

      // 路段：飽和度上色（綠 / 黃 / 紅），無資料為灰；顏色平滑過渡
      map.addLayer({
        id: "roads-base",
        type: "line",
        source: "roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": ["interpolate", ["linear"], ["zoom"], 10, 7, 13.1, 6, 16, 5],
          "line-color": [
            "case",
            ["<", ["get", "sat"], 0], "#333943",
            ["step", ["get", "sat"], "#2fbf71", 0.85, "#f5a623", 0.95, "#e5484d"],
          ],
          "line-opacity": ["case",
            ["!", ["get", "comparison_active"]], .9,
            ["get", "comparison_changed"], .95,
            .28,
          ],
        },
      });
      map.addLayer({
        id: "incident-projection-outline",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "simulated"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 10,
          "line-color": "#ff9f43",
          "line-opacity": 0.2,
          "line-dasharray": [1.4, 1],
        },
      });
      map.addLayer({
        id: "road-selected",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "selected"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": 12, "line-color": "#ffffff", "line-opacity": 0.32 },
      });
      map.addLayer({
        id: "green-corridor-glow",
        type: "line",
        source: "corridor-route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 15,
          "line-color": ["case", ["==", ["get", "approved"], true], "#00f5a0", "#f5a623"],
          "line-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "green-corridor-route",
        type: "line",
        source: "corridor-route",
        filter: ["==", ["get", "approved"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": 6, "line-color": "#00f5a0", "line-opacity": 0.98 },
      });
      map.addLayer({
        id: "green-corridor-proposal",
        type: "line",
        source: "corridor-route",
        filter: ["==", ["get", "approved"], false],
        paint: { "line-width": 5, "line-color": "#f5a623", "line-opacity": 0.9, "line-dasharray": [2, 1.5] },
      });
      map.addLayer({
        id: "green-corridor-blocked",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "corridor_blocked"], true],
        paint: { "line-width": 9, "line-color": "#ff3b3f", "line-dasharray": [1, 1] },
      });
      // 顏色平滑過渡（runtime 支援、TS 型別未涵蓋 transition 鍵）
      (map as any).setPaintProperty("roads-base", "line-color-transition", { duration: 700 });
      // 封閉路段：深紅粗虛線
      map.addLayer({
        id: "roads-closed",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "role"], "closed"],
        paint: {
          "line-width": 8,
          "line-color": "#8c2f33",
          "line-dasharray": [1.2, 1.2],
        },
      });
      // 主疏散：粗青色實線
      map.addLayer({
        id: "evac-primary",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "role"], "primary"],
        layout: { "line-cap": "round" },
        paint: { "line-width": 8, "line-color": "#007afc", "line-opacity": 0.95 },
      });
      // 次要疏散：白色虛線
      map.addLayer({
        id: "evac-secondary",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "role"], "secondary"],
        paint: {
          "line-width": 4,
          "line-color": "#d5dae2",
          "line-dasharray": [2, 2],
        },
      });
      // 基地台：人數決定半徑、漫遊率 >= 30% 轉紫
      map.addLayer({
        id: "stations",
        type: "circle",
        source: "stations",
        paint: {
          "circle-radius": [
            "interpolate", ["linear"], ["get", "users"],
            0, 4, 10000, 10, 40000, 22,
          ],
          "circle-color": [
            "case", [">=", ["get", "roaming"], 30], "#a06bfa", "#7f8b9e",
          ],
          "circle-opacity": 0.55,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#d5dae2",
        },
      });
      // 資訊可變標誌（CMS）官方靜態點位。
      map.addLayer({
        id: "cms-halo",
        type: "circle",
        source: "cms-assets",
        minzoom: 13,
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 9,
          "circle-color": "rgba(245, 166, 35, 0.16)",
          "circle-stroke-width": 1,
          "circle-stroke-color": "#f5a623",
        },
      });
      map.addLayer({
        id: "cms-core",
        type: "circle",
        source: "cms-assets",
        minzoom: 13,
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 3.5,
          "circle-color": "#f5a623",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#15171b",
        },
      });
      // 點位與設備資料來自臺北市交通局；燈相仍是決策沙盒的模擬狀態。
      void fetch("/data/signals.geojson")
        .then((response) => {
          if (!response.ok) throw new Error(`signals.geojson ${response.status}`);
          return response.json();
        })
        .then((collection: { features?: OfficialSignalFeature[] }) => {
          if (disposed) return;
          const features = collection.features ?? [];
          signalMarkersRef.current = features.map((signal) => {
            const { device_id: deviceId, name, group, report_url: reportUrl, segment_id: segmentId } = signal.properties;
            const offset = signalOffset(deviceId);
            const initialState = signalPhase(null, offset);
            const element = document.createElement("button");
            element.type = "button";
            element.hidden = !assetLayersRef.current.signals;
            element.className = `traffic-signal-marker phase-${initialState.phase}`;
            element.setAttribute("aria-label", `${name}官方號誌點位，燈相為模擬`);
            element.innerHTML = `
              <span class="signal-housing" aria-hidden="true">
                <i class="lamp red"></i><i class="lamp yellow"></i><i class="lamp green"></i>
              </span>
              <span class="signal-countdown">${initialState.remaining}s</span>
              <span class="signal-sim-tag">官點</span>`;
            element.addEventListener("click", (event) => {
              event.stopPropagation();
              selectRef.current?.(segmentId);
            });
            const reportLink = reportUrl
              ? `<br/><a href="${escapeHtml(reportUrl)}" target="_blank" rel="noreferrer">查看官方時制報表</a>`
              : "";
            const marker = new maplibregl.Marker({ element, anchor: "bottom" })
              .setLngLat(signal.geometry.coordinates)
              .setPopup(new maplibregl.Popup({ offset: 22 }).setHTML(
                `<b>${escapeHtml(name)}</b><br/>設備 ${escapeHtml(deviceId)}｜群組 ${escapeHtml(group) || "—"}<br/>點位：臺北市交通局｜燈相：沙盒模擬${reportLink}<br/>點擊號誌可開啟路段推演`
              ))
              .addTo(map);
            return { marker, element, offset, deviceId };
          });
          setSignalCount(features.length);
        })
        .catch((error) => {
          if (!disposed) console.error("無法載入官方號誌點位", error);
        });
      void fetch("/data/hospitals.geojson")
        .then((response) => {
          if (!response.ok) throw new Error(`hospitals.geojson ${response.status}`);
          return response.json();
        })
        .then((collection: { features?: HospitalFeature[] }) => {
          if (disposed) return;
          hospitalMarkersRef.current = (collection.features ?? []).map((hospital) => {
            const { name, address, source, source_url: sourceUrl } = hospital.properties;
            const element = document.createElement("button");
            element.type = "button";
            element.hidden = !assetLayersRef.current.hospitals;
            element.className = "hospital-map-marker";
            element.setAttribute("aria-label", `${name}，醫院`);
            element.innerHTML = `<span aria-hidden="true">✚</span>`;
            const sourceLink = sourceUrl
              ? `<br/><a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">查看官方院區資料</a>`
              : "";
            const marker = new maplibregl.Marker({ element, anchor: "center" })
              .setLngLat(hospital.geometry.coordinates)
              .setPopup(new maplibregl.Popup({ offset: 20 }).setHTML(
                `<b>${escapeHtml(name)}</b><br/>${escapeHtml(address)}<br/>點位來源：${escapeHtml(source)}${sourceLink}`
              ))
              .addTo(map);
            return { marker, element };
          });
        })
        .catch((error) => {
          if (!disposed) console.error("無法載入官方醫院點位", error);
        });
      // 事故點改用 HTML pulse marker（CSS 擴散動畫），此 source 保留供未來擴充

      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
      map.on("mousemove", "roads-base", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        map.getCanvas().style.cursor = "pointer";
        const sat = Number(p.sat) >= 0 ? Number(p.sat).toFixed(2) : "無資料";
        const modeLabel = p.comparison_mode === "baseline" ? "基準情境"
          : p.comparison_mode === "event" ? "障礙發生（未處置）" : "目前處置結果";
        const projection = p.simulated
          ? `<br/><span style="color:#ffbd72">${modeLabel}</span>${p.baseline_speed != null && p.event_speed != null ? `｜基準 ${p.baseline_speed} → 障礙 ${p.event_speed} → 目前 ${p.current_speed} km/h` : ""}`
          : "<br/>主辦方資料快照";
        popup
          .setLngLat(e.lngLat)
          .setHTML(`<b>${escapeHtml(p.name)}</b><br/>飽和度 ${sat}｜等級 ${escapeHtml(p.level)}${p.speed != null ? `｜${escapeHtml(p.speed)} km/h` : ""}${projection}`)
          .addTo(map);
      });
      map.on("mouseleave", "roads-base", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      map.on("click", "roads-base", (e) => {
        const segmentId = e.features?.[0]?.properties?.segment_id;
        if (segmentId) selectRef.current?.(segmentId);
      });
      map.on("mousemove", "stations", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        popup
          .setLngLat(e.lngLat)
          .setHTML(`<b>${p.name}</b><br/>${Number(p.users).toLocaleString()} 人｜成長 ${p.growth}｜漫遊 ${p.roaming}%`)
          .addTo(map);
      });
      map.on("mouseleave", "stations", () => popup.remove());
      map.on("mousemove", "crosswalk-fill", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        map.getCanvas().style.cursor = "help";
        popup.setLngLat(e.lngLat).setHTML(
          `<b>${escapeHtml(p.kind)}行人穿越線</b><br/>代碼 ${escapeHtml(p.licode)}｜長 ${escapeHtml(p.length)}｜寬 ${escapeHtml(p.width)}`
        ).addTo(map);
      });
      map.on("mouseleave", "crosswalk-fill", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      map.on("mousemove", "cms-core", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        map.getCanvas().style.cursor = "pointer";
        popup.setLngLat(e.lngLat).setHTML(
          `<b>CMS ${escapeHtml(p.cms_id)}</b><br/>${escapeHtml(p.road_name) || "未提供道路名稱"}｜方向 ${escapeHtml(p.direction) || "—"}`
        ).addTo(map);
      });
      map.on("mouseleave", "cms-core", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      map.on("mousemove", "risk-grid-fill", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        map.getCanvas().style.cursor = "help";
        popup.setLngLat(e.lngLat).setHTML(
          `<b>H3 風險格｜${escapeHtml(p.level)}風險</b><br/>分數 ${Number(p.risk).toFixed(2)}｜解析度 ${escapeHtml(p.h3_resolution)}<br/>道路 ${escapeHtml(p.traffic_entities) || "—"}<br/>基地台 ${escapeHtml(p.crowd_entities) || "—"}`
        ).addTo(map);
      });
      map.on("mouseleave", "risk-grid-fill", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      map.on("mousemove", "incident-impact-fill", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        popup.setLngLat(e.lngLat).setHTML(
          `<b>事件推播影響範圍</b><br/>半徑 ${escapeHtml(p.radius_m)} 公尺｜${escapeHtml(p.severity)}<br/>依事件座標以 Turf 計算`
        ).addTo(map);
      });
      map.on("mouseleave", "incident-impact-fill", () => popup.remove());

      map.on("zoomend", () => {
        (map.getSource("risk-grid") as maplibregl.GeoJSONSource)?.setData(
          riskGridGeoJSON(
            viewRef.current,
            OFFICIAL_ROADS,
            STATION_COORDS,
            h3ResolutionForZoom(map.getZoom()),
          )
        );
      });

      readyRef.current = true;
    });

    return () => {
      disposed = true;
      readyRef.current = false;
      signalMarkersRef.current.forEach(({ marker }) => marker.remove());
      signalMarkersRef.current = [];
      hospitalMarkersRef.current.forEach(({ marker }) => marker.remove());
      hospitalMarkersRef.current = [];
      ambulanceMarkerRef.current?.remove();
      ambulanceMarkerRef.current = null;
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const plannedSignalIds = new Set(greenCorridor?.signal_actions.map((action) => action.device_id) ?? []);
    const activeSignalIds = new Set(greenCorridor?.runtime_state?.active_signal_device_ids ?? []);
    const clearanceSignalIds = new Set(greenCorridor?.runtime_state?.clearance_signal_device_ids ?? []);
    const corridorApproved = greenCorridor?.approval_status === "APPROVED_FOR_SIMULATION";
    signalMarkersRef.current.forEach(({ element, offset, deviceId }) => {
      const state = signalPhase(view, offset);
      const corridorActive = corridorApproved && activeSignalIds.has(deviceId);
      const corridorSelected = corridorApproved
        ? clearanceSignalIds.has(deviceId)
        : plannedSignalIds.has(deviceId);
      element.classList.remove("phase-red", "phase-yellow", "phase-green", "corridor-preempt", "corridor-proposed");
      element.classList.add(corridorActive ? "phase-green" : `phase-${state.phase}`);
      if (corridorActive) element.classList.add("corridor-preempt");
      else if (corridorSelected) element.classList.add("corridor-proposed");
      const countdown = element.querySelector<HTMLElement>(".signal-countdown");
      if (countdown) countdown.textContent = corridorActive ? "優先" : corridorSelected
        ? corridorApproved ? "清空" : "待核"
        : `${state.remaining}s`;
      element.title = corridorActive
        ? "官方號誌點位；已核准啟動救援走廊模擬優先綠燈"
        : corridorSelected
          ? "官方號誌點位；救援走廊優先綠燈提案（待核准）"
          : `官方號誌點位；模擬${state.label}，剩餘 ${state.remaining} 秒`;
    });
    const vehiclePosition = greenCorridor?.runtime_state?.vehicle_position;
    if (corridorApproved && vehiclePosition) {
      const runtime = greenCorridor.runtime_state;
      if (!ambulanceMarkerRef.current) {
        const element = document.createElement("button");
        element.type = "button";
        element.className = "ambulance-map-marker";
        element.setAttribute("aria-label", "救護車模擬位置");
        element.innerHTML = `
          <span class="ambulance-pulse" aria-hidden="true"></span>
          <span class="ambulance-symbol" aria-hidden="true">🚑</span>
          <span class="ambulance-label">模擬定位</span>`;
        ambulanceMarkerRef.current = new maplibregl.Marker({ element, anchor: "center" })
          .setLngLat(vehiclePosition)
          .addTo(map);
      }
      const nextLabel = runtime.next_intersection_id ?? "目的地";
      const statusLabel = runtime.completed ? "已抵達" : `前往 ${nextLabel}`;
      const nextSignal = greenCorridor.signal_actions.find(
        (action) => action.intersection_id === runtime.next_intersection_id
      );
      const nextDistance = nextSignal ? distanceMeters(vehiclePosition, nextSignal.coordinates) : null;
      ambulanceMarkerRef.current
        .setLngLat(vehiclePosition)
        .setPopup(new maplibregl.Popup({ offset: 28 }).setHTML(
          `<b>救護車｜${escapeHtml(statusLabel)}</b><br/>路線進度 ${runtime.vehicle_progress_pct}%${nextDistance != null ? `<br/>距下一路口約 ${nextDistance} 公尺（Turf）` : ""}<br/>定位來源：走廊路徑與模擬時間推算（非 GPS）`
        ));
      const element = ambulanceMarkerRef.current.getElement();
      element.classList.toggle("arrived", runtime.completed);
      element.setAttribute("aria-label", `救護車模擬定位，進度 ${runtime.vehicle_progress_pct}%，${statusLabel}`);
      element.title = `救護車模擬定位｜進度 ${runtime.vehicle_progress_pct}%｜${statusLabel}`;
    } else {
      ambulanceMarkerRef.current?.remove();
      ambulanceMarkerRef.current = null;
    }
    // 事件擴散 pulse marker（DOM overlay，不需等 style load）
    const coord = coordinateForIncident(incident);
    const incidentId = incident?.incident_id ?? null;
    if (markerIncidentRef.current !== incidentId) {
      markerRef.current?.remove();
      markerRef.current = null;
      markerIncidentRef.current = incidentId;
      if (coord) {
        const el = document.createElement("div");
        el.className = "pulse-marker";
        markerRef.current = new maplibregl.Marker({ element: el })
          .setLngLat(coord)
          .addTo(map);
      }
    }
    if (!readyRef.current) return;
    (map.getSource("roads") as maplibregl.GeoJSONSource)?.setData(
      roadsGeoJSON(view, incident, projectedTraffic, selectedSegmentId, greenCorridor, comparisonMode)
    );
    (map.getSource("corridor-route") as maplibregl.GeoJSONSource)?.setData(
      corridorGeoJSON(greenCorridor)
    );
    (map.getSource("stations") as maplibregl.GeoJSONSource)?.setData(
      stationsGeoJSON(view)
    );
    (map.getSource("incident") as maplibregl.GeoJSONSource)?.setData(
      incidentGeoJSON(incident)
    );
    (map.getSource("incident-impact") as maplibregl.GeoJSONSource)?.setData(
      incidentImpactGeoJSON(incident, coordinateForIncident(incident))
    );
    (map.getSource("risk-grid") as maplibregl.GeoJSONSource)?.setData(
      riskGridGeoJSON(
        view,
        OFFICIAL_ROADS,
        STATION_COORDS,
        h3ResolutionForZoom(map.getZoom()),
      )
    );
    const activeIncidentId = view?.simulation_context?.active
      ? view.simulation_context.incident_id ?? null : null;
    if (!activeIncidentId) {
      renderedIncidentRef.current = null;
    } else if (renderedIncidentRef.current !== activeIncidentId) {
      renderedIncidentRef.current = activeIncidentId;
      map.once("render", () => scenarioRenderedCallbackRef.current?.(activeIncidentId));
    }
  }, [view, incident, projectedTraffic, greenCorridor, selectedSegmentId, signalCount, comparisonMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const visibility = (visible: boolean) => visible ? "visible" : "none";
    ["crosswalk-fill"].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", visibility(assetLayers.crosswalks)));
    ["cms-halo", "cms-core"].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", visibility(assetLayers.cms)));
    ["risk-grid-fill", "risk-grid-line"].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", visibility(assetLayers.risk)));
    signalMarkersRef.current.forEach(({ element }) => { element.hidden = !assetLayers.signals; });
    hospitalMarkersRef.current.forEach(({ element }) => { element.hidden = !assetLayers.hospitals; });
  }, [assetLayers]);

  const toggleAssetLayer = (layer: AssetLayer) => {
    setAssetLayers((current) => ({ ...current, [layer]: !current[layer] }));
  };

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map" />
      <button type="button" className="map-scope-badge"
        aria-label="返回主辦方十五條路段完整總覽"
        onClick={() => mapRef.current && fitOrganizerRoadOverview(mapRef.current, true)}>
        15/15 路段總覽
      </button>
      {onSelectSegment && !selectedSegmentId && (
        <div className="map-pick-hint">點選路段，建立人工決策方案</div>
      )}
      {(projectedTraffic || view?.simulation_context?.active) && (
        <div className={`map-sim-badge ${view?.simulation_context?.active ? "incident" : ""} ${view?.simulation_context?.response_phase === "CLEARANCE_ACTIVE" ? "clearance" : ""}`}>
          <span />{view?.simulation_context?.active
            ? view.simulation_context.response_phase === "CLEARANCE_ACTIVE"
              ? `疏通處理中｜恢復 ${Math.round((view.simulation_context.mitigation_progress ?? 0) * 100)}%｜已核准 ${view.simulation_context.accepted_action_ids?.length ?? 0} 項決策`
              : view.simulation_context.response_phase === "DISPATCHING"
                ? `資源前往現場｜已核准 ${view.simulation_context.accepted_action_ids?.length ?? 0} 項｜尚未開始改善`
              : view.simulation_context.response_phase === "CLEARED"
                ? "模擬疏通完成｜等待現場確認結案"
                : `障礙已發生｜等待決策核准${view.simulation_context.review_overdue ? "｜狀態逾時待複核" : ""}`
            : "方案推演結果｜非正式狀態"}
        </div>
      )}
      {view?.simulation_context?.active && (
        <div className="scenario-compare" role="group" aria-label="情境比較模式">
          <span>同時間比較</span>
          <button className={comparisonMode === "baseline" ? "active" : ""}
            onClick={() => setComparisonMode("baseline")}>① 基準</button>
          <button className={comparisonMode === "event" ? "active" : ""}
            onClick={() => setComparisonMode("event")}>② 障礙發生</button>
          <button className={comparisonMode === "current" ? "active" : ""}
            disabled={!view.scenario_comparison?.scenarios.treatment.available}
            title={view.scenario_comparison?.scenarios.treatment.locked_reason ?? undefined}
            onClick={() => setComparisonMode("current")}>③ 目前處置</button>
        </div>
      )}
      {greenCorridor && (
        <div className={`map-corridor-badge ${greenCorridor.approval_status === "APPROVED_FOR_SIMULATION" ? "approved" : "pending"}`}>
          <span />綠色救援走廊｜{greenCorridor.eta.before_minutes} → {greenCorridor.eta.after_minutes} 分｜
          {greenCorridor.approval_status === "APPROVED_FOR_SIMULATION" ? "模擬啟動" : "待核准"}
        </div>
      )}
      <div className={`asset-layer-control ${layersCollapsed ? "collapsed" : ""}`} role="group" aria-label="交通設施圖層">
        <button type="button" className="asset-layer-collapse" aria-expanded={!layersCollapsed}
          onClick={() => setLayersCollapsed((value) => !value)}>
          {layersCollapsed ? "圖層 ▴" : "收合 ▾"}
        </button>
        {!layersCollapsed && <>
        <button className={assetLayers.crosswalks ? "active" : ""} aria-pressed={assetLayers.crosswalks}
          onClick={() => toggleAssetLayer("crosswalks")}>
          <i className="crosswalk-mini" aria-hidden="true" /><span><b>行穿線</b><small>官方 19,643</small></span>
        </button>
        <button className={assetLayers.signals ? "active" : ""} aria-pressed={assetLayers.signals}
          onClick={() => toggleAssetLayer("signals")}>
          <i className="signal-mini" aria-hidden="true"><em /><em /><em /></i><span><b>智慧號誌</b><small>官方 {signalCount || "—"}</small></span>
        </button>
        <button className={assetLayers.cms ? "active" : ""} aria-pressed={assetLayers.cms}
          onClick={() => toggleAssetLayer("cms")}>
          <i className="cms-mini" aria-hidden="true">CMS</i><span><b>資訊看板</b><small>官方 178</small></span>
        </button>
        <button className={assetLayers.hospitals ? "active" : ""} aria-pressed={assetLayers.hospitals}
          onClick={() => toggleAssetLayer("hospitals")}>
          <i className="hospital-mini" aria-hidden="true">✚</i><span><b>醫院</b><small>官方 11</small></span>
        </button>
        <button className={assetLayers.risk ? "active" : ""} aria-pressed={assetLayers.risk}
          onClick={() => toggleAssetLayer("risk")}>
          <i className="risk-mini" aria-hidden="true">⬡</i><span><b>H3 風險格</b><small>即時計算</small></span>
        </button>
        </>}
      </div>
      <div className="map-legend">
        <span><i className="sw" style={{ background: "#2fbf71" }} /> 正常</span>
        <span><i className="sw" style={{ background: "#f5a623" }} /> B 級</span>
        <span><i className="sw" style={{ background: "#e5484d" }} /> A 級</span>
        <span><i className="sw" style={{ background: "#007afc" }} /> 主疏散</span>
        <span><i className="sw dashed" style={{ background: "#d5dae2" }} /> 次要疏散</span>
        <span><i className="sw" style={{ background: "#8c2f33" }} /> 封閉</span>
        <span><i className="sw corridor" /> 救援綠廊</span>
        <span className="note">號誌點位、行穿線、CMS 為官方圖資；道路情境與號誌燈相為模擬</span>
      </div>
    </div>
  );
}
