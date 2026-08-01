import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { useState } from "react";
import type { GreenCorridorResult, IncidentState, SimView } from "./api";
import officialRoadGeometry from "./data/roads.json";
import {
  INCIDENT_COORDS,
  MAP_CENTER,
  MAP_ZOOM,
  STATION_COORDS,
} from "./geometry";

type AssetLayer = "crosswalks" | "signals" | "cms";

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
  properties: { segment_id: string };
  geometry: { type: "LineString"; coordinates: [number, number][] };
};

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
) {
  const routing = incident?.routing_result;
  const primaryId = routing?.primary_route?.segment_id;
  const secondaryIds = new Set<string>(
    (routing?.secondary_routes ?? []).map((s: any) => s.segment_id)
  );
  const closedId = routing?.affected_segment?.segment_id;
  const corridorIds = new Set(greenCorridor?.route_segment_ids ?? []);
  const corridorBlockedIds = new Set(greenCorridor?.blocked_segment_ids ?? []);

  return {
    type: "FeatureCollection" as const,
    features: (officialRoadGeometry.features as unknown as OfficialRoadFeature[]).map((road) => {
      const segId = road.properties.segment_id;
      const t = projectedTraffic?.[segId] ?? view?.traffic?.[segId];
      let role = "none";
      if (segId === closedId) role = "closed";
      else if (segId === primaryId) role = "primary";
      else if (secondaryIds.has(segId)) role = "secondary";
      return {
        type: "Feature" as const,
        properties: {
          segment_id: segId,
          name: t?.road_name ?? segId,
          sat: t?.saturation_score ?? -1,
          level: t?.congestion_level ?? "NoData",
          speed: t?.avg_speed ?? null,
          role,
          selected: segId === selectedSegmentId,
          simulated: Boolean(projectedTraffic?.[segId]),
          corridor: corridorIds.has(segId),
          corridor_approved: greenCorridor?.approval_status === "APPROVED_FOR_SIMULATION" && corridorIds.has(segId),
          corridor_blocked: corridorBlockedIds.has(segId),
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
  const coord = INCIDENT_COORDS[incident.incident_id];
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

export default function MapView({
  view,
  incident,
  projectedTraffic,
  greenCorridor,
  selectedSegmentId,
  onSelectSegment,
}: {
  view: SimView | null;
  incident: IncidentState | null;
  projectedTraffic?: Record<string, any> | null;
  greenCorridor?: GreenCorridorResult | null;
  selectedSegmentId?: string | null;
  onSelectSegment?: (segmentId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const markerIncidentRef = useRef<string | null>(null);
  const signalMarkersRef = useRef<{ marker: maplibregl.Marker; element: HTMLButtonElement; offset: number; deviceId: string }[]>([]);
  const selectRef = useRef(onSelectSegment);
  selectRef.current = onSelectSegment;
  const [assetLayers, setAssetLayers] = useState<Record<AssetLayer, boolean>>({
    crosswalks: true,
    signals: true,
    cms: true,
  });
  const assetLayersRef = useRef(assetLayers);
  assetLayersRef.current = assetLayers;
  const [signalCount, setSignalCount] = useState(0);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.on("load", () => {
      map.addSource("roads", { type: "geojson", data: roadsGeoJSON(null, null) });
      map.addSource("stations", { type: "geojson", data: stationsGeoJSON(null) });
      map.addSource("incident", { type: "geojson", data: incidentGeoJSON(null) });
      map.addSource("crosswalks", { type: "geojson", data: "/data/crosswalks.geojson" });
      map.addSource("cms-assets", { type: "geojson", data: "/data/cms.geojson" });

      // 臺北市交工處行穿線：以官方 Polygon 呈現，縮放至街廓層級才顯示細節。
      map.addLayer({
        id: "crosswalk-fill",
        type: "fill",
        source: "crosswalks",
        minzoom: 14,
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
          "line-width": 4.5,
          "line-color": [
            "case",
            ["<", ["get", "sat"], 0], "#333943",
            ["step", ["get", "sat"], "#2fbf71", 0.85, "#f5a623", 0.95, "#e5484d"],
          ],
          "line-opacity": 0.9,
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
        source: "roads",
        filter: ["==", ["get", "corridor"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 15,
          "line-color": ["case", ["==", ["get", "corridor_approved"], true], "#00f5a0", "#f5a623"],
          "line-opacity": 0.18,
        },
      });
      map.addLayer({
        id: "green-corridor-route",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "corridor_approved"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": 6, "line-color": "#00f5a0", "line-opacity": 0.98 },
      });
      map.addLayer({
        id: "green-corridor-proposal",
        type: "line",
        source: "roads",
        filter: ["all", ["==", ["get", "corridor"], true], ["==", ["get", "corridor_approved"], false]],
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
      // 事故點改用 HTML pulse marker（CSS 擴散動畫），此 source 保留供未來擴充

      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
      map.on("mousemove", "roads-base", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        map.getCanvas().style.cursor = "pointer";
        const sat = Number(p.sat) >= 0 ? Number(p.sat).toFixed(2) : "無資料";
        popup
          .setLngLat(e.lngLat)
          .setHTML(`<b>${p.name}</b><br/>飽和度 ${sat}｜等級 ${p.level}${p.speed != null ? `｜${p.speed} km/h` : ""}`)
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

      readyRef.current = true;
    });

    return () => {
      disposed = true;
      readyRef.current = false;
      signalMarkersRef.current.forEach(({ marker }) => marker.remove());
      signalMarkersRef.current = [];
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
    // 事件擴散 pulse marker（DOM overlay，不需等 style load）
    const coord = incident ? INCIDENT_COORDS[incident.incident_id] : null;
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
      roadsGeoJSON(view, incident, projectedTraffic, selectedSegmentId, greenCorridor)
    );
    (map.getSource("stations") as maplibregl.GeoJSONSource)?.setData(
      stationsGeoJSON(view)
    );
    (map.getSource("incident") as maplibregl.GeoJSONSource)?.setData(
      incidentGeoJSON(incident)
    );
  }, [view, incident, projectedTraffic, greenCorridor, selectedSegmentId, signalCount]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const visibility = (visible: boolean) => visible ? "visible" : "none";
    ["crosswalk-fill"].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", visibility(assetLayers.crosswalks)));
    ["cms-halo", "cms-core"].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", visibility(assetLayers.cms)));
    signalMarkersRef.current.forEach(({ element }) => { element.hidden = !assetLayers.signals; });
  }, [assetLayers]);

  const toggleAssetLayer = (layer: AssetLayer) => {
    setAssetLayers((current) => ({ ...current, [layer]: !current[layer] }));
  };

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map" />
      {onSelectSegment && !selectedSegmentId && (
        <div className="map-pick-hint">點選路段，建立人工決策方案</div>
      )}
      {projectedTraffic && (
        <div className="map-sim-badge"><span />方案推演結果｜非正式狀態</div>
      )}
      {greenCorridor && (
        <div className={`map-corridor-badge ${greenCorridor.approval_status === "APPROVED_FOR_SIMULATION" ? "approved" : "pending"}`}>
          <span />綠色救援走廊｜{greenCorridor.eta.before_minutes} → {greenCorridor.eta.after_minutes} 分｜
          {greenCorridor.approval_status === "APPROVED_FOR_SIMULATION" ? "模擬啟動" : "待核准"}
        </div>
      )}
      <div className="asset-layer-control" role="group" aria-label="交通設施圖層">
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
