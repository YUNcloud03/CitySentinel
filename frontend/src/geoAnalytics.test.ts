import { describe, expect, it } from "vitest";
import type { SimView } from "./api";
import {
  distanceMeters,
  h3ResolutionForZoom,
  incidentImpactGeoJSON,
  riskGridGeoJSON,
} from "./geoAnalytics";

describe("geospatial evidence", () => {
  it("changes H3 resolution with map zoom", () => {
    expect(h3ResolutionForZoom(11)).toBe(7);
    expect(h3ResolutionForZoom(14)).toBe(9);
    expect(h3ResolutionForZoom(16)).toBe(10);
  });

  it("creates an H3 risk cell from organizer traffic", () => {
    const view: SimView = {
      playing: false,
      sim_time: "2026-05-20 22:00",
      traffic: {
        RD_TPE_001: {
          road_name: "測試路", avg_speed: 8, vehicle_count: 1200,
          saturation_score: 1, lane_status: "Gridlock", congestion_level: "A",
          data_time: "2026-05-20 22:00",
        },
      },
    };
    const grid = riskGridGeoJSON(view, [{
      properties: { segment_id: "RD_TPE_001" },
      geometry: { type: "LineString", coordinates: [[121.55, 25.04], [121.56, 25.04]] },
    }], {}, 9);
    expect(grid.features).toHaveLength(1);
    expect(grid.features[0].properties.h3_resolution).toBe(9);
    expect(grid.features[0].properties.risk).toBeGreaterThan(.9);
    expect(grid.features[0].geometry.coordinates[0].length).toBeGreaterThanOrEqual(6);
  });

  it("uses Turf for metric distance and incident impact radius", () => {
    expect(distanceMeters([121.55, 25.04], [121.55, 25.04])).toBe(0);
    const impact = incidentImpactGeoJSON({
      incident_id: "TEST", workflow_status: "completed", current_step: "COMPLETED",
      event: { severity: "Critical" }, as_of: "2026-05-20 22:00", triggered_rules: [],
      routing_result: null, ete_result: null, dispatch: null, sop_evidence: [], notifications: {},
      decision_trace: [], errors: [],
    }, [121.55, 25.04]);
    expect(impact.features[0].properties.radius_m).toBe(650);
    expect(impact.features[0].geometry.coordinates[0].length).toBeGreaterThan(40);
  });
});

