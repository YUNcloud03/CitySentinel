import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { IncidentState, SimView } from "./api";
import {
  INCIDENT_COORDS,
  MAP_CENTER,
  MAP_ZOOM,
  SEGMENT_COORDS,
  STATION_COORDS,
} from "./geometry";

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

function roadsGeoJSON(view: SimView | null, incident: IncidentState | null) {
  const routing = incident?.routing_result;
  const primaryId = routing?.primary_route?.segment_id;
  const secondaryIds = new Set<string>(
    (routing?.secondary_routes ?? []).map((s: any) => s.segment_id)
  );
  const closedId = routing?.affected_segment?.segment_id;

  return {
    type: "FeatureCollection" as const,
    features: Object.entries(SEGMENT_COORDS).map(([segId, coords]) => {
      const t = view?.traffic?.[segId];
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
        },
        geometry: { type: "LineString" as const, coordinates: coords },
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
}: {
  view: SimView | null;
  incident: IncidentState | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current) return;
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

      // 路段：飽和度上色（綠 / 黃 / 紅），無資料為灰
      map.addLayer({
        id: "roads-base",
        type: "line",
        source: "roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 4.5,
          "line-color": [
            "case",
            ["<", ["get", "sat"], 0], "#475569",
            ["step", ["get", "sat"], "#22c55e", 0.85, "#f59e0b", 0.95, "#ef4444"],
          ],
          "line-opacity": 0.9,
        },
      });
      // 封閉路段：深紅粗虛線
      map.addLayer({
        id: "roads-closed",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "role"], "closed"],
        paint: {
          "line-width": 8,
          "line-color": "#991b1b",
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
        paint: { "line-width": 8, "line-color": "#22d3ee", "line-opacity": 0.95 },
      });
      // 次要疏散：白色虛線
      map.addLayer({
        id: "evac-secondary",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "role"], "secondary"],
        paint: {
          "line-width": 4,
          "line-color": "#e2e8f0",
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
            "case", [">=", ["get", "roaming"], 30], "#a855f7", "#38bdf8",
          ],
          "circle-opacity": 0.55,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#e0f2fe",
        },
      });
      // 事故點
      map.addLayer({
        id: "incident-pt",
        type: "circle",
        source: "incident",
        paint: {
          "circle-radius": 11,
          "circle-color": "#ef4444",
          "circle-opacity": 0.9,
          "circle-stroke-width": 3,
          "circle-stroke-color": "#fecaca",
        },
      });

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
      map.on("mousemove", "stations", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        popup
          .setLngLat(e.lngLat)
          .setHTML(`<b>${p.name}</b><br/>${Number(p.users).toLocaleString()} 人｜成長 ${p.growth}｜漫遊 ${p.roaming}%`)
          .addTo(map);
      });
      map.on("mouseleave", "stations", () => popup.remove());

      readyRef.current = true;
    });

    return () => {
      readyRef.current = false;
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    (map.getSource("roads") as maplibregl.GeoJSONSource)?.setData(
      roadsGeoJSON(view, incident)
    );
    (map.getSource("stations") as maplibregl.GeoJSONSource)?.setData(
      stationsGeoJSON(view)
    );
    (map.getSource("incident") as maplibregl.GeoJSONSource)?.setData(
      incidentGeoJSON(incident)
    );
  }, [view, incident]);

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map" />
      <div className="map-legend">
        <span><i className="sw" style={{ background: "#22c55e" }} /> 正常</span>
        <span><i className="sw" style={{ background: "#f59e0b" }} /> B 級</span>
        <span><i className="sw" style={{ background: "#ef4444" }} /> A 級</span>
        <span><i className="sw" style={{ background: "#22d3ee" }} /> 主疏散</span>
        <span><i className="sw dashed" style={{ background: "#e2e8f0" }} /> 次要疏散</span>
        <span><i className="sw" style={{ background: "#991b1b" }} /> 封閉</span>
        <span className="note">座標為示意，處置判定不使用</span>
      </div>
    </div>
  );
}
