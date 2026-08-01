import { describe, expect, it } from "vitest";
import { customIncidentInputSchema, simViewSchema, validatePayload } from "./schemas";

describe("Zod trust boundary", () => {
  it("accepts a valid operator incident", () => {
    const event = {
      type: "Road_Collapse",
      affected_segment: "RD_TPE_003",
      status: "Closed",
      severity: "High",
      location: "基隆路一段",
      description: "道路發生塌陷，進行模擬",
      timestamp: "2026-05-20 22:00",
      source_type: "operator",
      human_confirmed: true,
      affected_direction: "northbound",
      lanes_total: 3,
      lanes_closed: 2,
      review_interval_minutes: 15,
    };
    expect(customIncidentInputSchema.safeParse(event).success).toBe(true);
  });

  it("rejects invalid road IDs and impossible source dates", () => {
    const invalid = {
      type: "Road_Collapse", affected_segment: "MADE_UP_ROAD", status: "Closed",
      severity: "High", location: "未知", description: "測試事件",
      timestamp: "2027-01-01 99:99",
    };
    expect(customIncidentInputSchema.safeParse(invalid).success).toBe(false);
  });

  it("blocks malformed simulation payloads before they reach the UI", () => {
    expect(() => validatePayload(simViewSchema, {
      playing: true,
      sim_time: "2026-05-20 22:00",
      traffic: { RD_TPE_001: { saturation_score: "critical" } },
    }, "simulation")).toThrow(/資料驗證失敗/);
  });

  it("accepts a traceable incident projection snapshot", () => {
    const parsed = simViewSchema.safeParse({
      playing: true,
      sim_time: "2026-05-20 22:10",
      traffic: {
        RD_TPE_002: {
          road_name: "光復南路", avg_speed: 1, vehicle_count: 900,
          saturation_score: 1.2, lane_status: "Closed · incident projection",
          congestion_level: "A", data_time: "2026-05-20 22:00",
          simulation_source: "incident_projection", baseline_avg_speed: 2,
          baseline_vehicle_count: 800, baseline_saturation_score: 1,
        },
      },
      simulation_context: {
        active: true, model: "deterministic-incident-v1", deterministic: true,
        incident_id: "TPE_2026_ACC_001", changed_segment_ids: ["RD_TPE_002"],
        baseline_source: "city_traffic_flow.csv", production_state_modified: false,
      },
    });
    expect(parsed.success).toBe(true);
  });
});
