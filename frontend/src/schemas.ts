import * as z from "zod";
import { corridorSafetyViolations } from "./corridorSafety";

const coordinate = z.tuple([
  z.number().min(119).max(123),
  z.number().min(21).max(26),
]);

const alert = z.object({
  rule_id: z.number().int().min(1).max(7),
  entity_id: z.string().min(1),
  evidence: z.record(z.string(), z.unknown()),
  actions: z.array(z.string()),
}).passthrough();

export const simViewSchema = z.object({
  playing: z.boolean(),
  sim_time: z.string().nullable(),
  progress: z.object({ index: z.number().int().nonnegative(), total: z.number().int().positive() }).optional(),
  traffic: z.record(z.string(), z.object({
    road_name: z.string(), avg_speed: z.number().nonnegative(), vehicle_count: z.number().nonnegative(),
    saturation_score: z.number().min(0).max(1.5), lane_status: z.string(),
    congestion_level: z.enum(["A", "B", "Normal"]), data_time: z.string(),
    simulation_source: z.enum(["organizer_dataset", "incident_projection"]).optional(),
    baseline_avg_speed: z.number().nonnegative().optional(),
    baseline_vehicle_count: z.number().nonnegative().optional(),
    baseline_saturation_score: z.number().min(0).max(1.5).optional(),
    event_avg_speed: z.number().nonnegative().optional(),
    event_vehicle_count: z.number().nonnegative().optional(),
    event_saturation_score: z.number().min(0).max(1.5).optional(),
  }).passthrough()).optional(),
  crowd: z.record(z.string(), z.object({
    location_name: z.string(), user_count: z.number().nonnegative(), growth_rate: z.number(),
    roaming_user_pct: z.number().min(0).max(100), data_time: z.string(),
  })).optional(),
  active_alerts: z.array(alert).optional(),
  simulation_context: z.object({
    active: z.boolean(), model: z.string(), incident_id: z.string().optional(),
    starts_at: z.string().optional(), elapsed_minutes: z.number().nonnegative().optional(),
    affected_segment_id: z.string().optional(), changed_segment_ids: z.array(z.string()).optional(),
    dynamic_routing: z.unknown().optional(), baseline_source: z.string().optional(),
    deterministic: z.boolean().optional(), formula: z.record(z.string(), z.string()).optional(),
    production_state_modified: z.literal(false).optional(), reason: z.string().optional(),
  }).passthrough().optional(),
}).passthrough();

export const incidentStateSchema = z.object({
  incident_id: z.string().min(1),
  workflow_status: z.string(),
  current_step: z.string(),
  event: z.record(z.string(), z.unknown()),
  as_of: z.string(),
  triggered_rules: z.array(z.number().int().min(1).max(7)),
  sop_evidence: z.array(z.object({ rule_id: z.number().int().min(1).max(7), title: z.string(), text: z.string() })),
  decision_trace: z.array(z.object({ step: z.string(), at: z.string(), detail: z.unknown() })),
  errors: z.array(z.string()),
}).passthrough();

export const runtimeStateSchema = z.object({
  elapsed_seconds: z.number().int().nonnegative(),
  total_seconds: z.number().int().nonnegative(),
  completed: z.boolean(),
  current_intersection_id: z.string().nullable(),
  active_signal_device_ids: z.array(z.string()),
  clearance_signal_device_ids: z.array(z.string()),
  vehicle_position: coordinate.nullable(),
  vehicle_progress_pct: z.number().min(0).max(100),
  vehicle_position_source: z.literal("simulated_from_route_geometry_and_corridor_elapsed_time"),
  next_intersection_id: z.string().nullable(),
  intersection_states: z.array(z.object({
    intersection_id: z.string(), name: z.string(), state: z.string(), device_ids: z.array(z.string()),
    prepare_at_seconds: z.number(), activate_at_seconds: z.number(), passage_at_seconds: z.number(), restore_at_seconds: z.number(),
  })),
}).passthrough();

export const greenCorridorSchema = z.object({
  scenario_id: z.string().min(1),
  as_of: z.string(),
  vehicle_type: z.enum(["Ambulance", "FireEngine"]),
  priority: z.literal("EMERGENCY"),
  route_segment_ids: z.array(z.string()).min(1),
  route_names: z.array(z.string()).min(1),
  route_geometry: z.array(coordinate).min(2),
  eta: z.object({
    before_minutes: z.number().nonnegative(), after_minutes: z.number().nonnegative(),
    saved_minutes: z.number().nonnegative(), improvement_pct: z.number(), formula: z.string(),
  }),
  signal_actions: z.array(z.object({
    intersection_id: z.string(), device_id: z.string(), name: z.string(), segment_id: z.string(), coordinates: coordinate,
    action: z.literal("EMERGENCY_GREEN"), prepare_at_seconds: z.number(), activate_at_seconds: z.number(),
    passage_at_seconds: z.number(), restore_at_seconds: z.number(), pedestrian_clearance_seconds: z.number(), reason: z.string(),
  })),
  runtime_state: runtimeStateSchema,
  approval_status: z.enum(["READY_FOR_APPROVAL", "APPROVED_FOR_SIMULATION"]),
  production_state_modified: z.literal(false),
}).passthrough().superRefine((result, context) => {
  for (const message of corridorSafetyViolations(result)) {
    context.addIssue({ code: "custom", message });
  }
});

export const customIncidentInputSchema = z.object({
  type: z.enum(["Road_Collapse", "Traffic_Accident", "Power_Failure", "Flooding", "Crowd_Surge_Injury"]),
  location: z.string().min(2),
  affected_segment: z.string().regex(/^(RD|BS)_[A-Z0-9_]+$/),
  status: z.enum(["Closed", "Blocked", "Restricted", "Caution", "Crowded", "Surging", "Dispersing"]),
  severity: z.enum(["Critical", "High", "Medium", "Low"]),
  description: z.string().min(4),
  timestamp: z.string().regex(/^2026-05-20 \d{2}:\d{2}$/),
  source_type: z.enum(["official", "operator", "iot", "camera", "citizen", "unknown"]).optional(),
  human_confirmed: z.boolean().optional(),
  affected_direction: z.enum(["both", "northbound", "southbound", "eastbound", "westbound"]).optional(),
  lanes_total: z.number().int().min(1).max(8).optional(),
  lanes_closed: z.number().int().min(0).max(8).optional(),
  review_interval_minutes: z.number().int().min(5).max(120).optional(),
  roaming_override_pct: z.number().min(0).max(100).nullable().optional(),
  crowd_user_count_override: z.number().int().min(0).max(200_000).nullable().optional(),
  crowd_growth_rate_override: z.number().min(-1).max(5).nullable().optional(),
  crowd_roaming_user_pct_override: z.number().min(0).max(100).nullable().optional(),
  crowd_stay_time_avg_override: z.number().min(0).max(600).nullable().optional(),
}).passthrough().superRefine((value, context) => {
  const isCrowd = value.type === "Crowd_Surge_Injury";
  if (isCrowd && !value.affected_segment.startsWith("BS_")) {
    context.addIssue({ code: "custom", path: ["affected_segment"], message: "人潮事件必須選擇站點" });
  }
  if (!isCrowd && !value.affected_segment.startsWith("RD_")) {
    context.addIssue({ code: "custom", path: ["affected_segment"], message: "道路事件必須選擇路段" });
  }
});

export const advisorAnswerSchema = z.object({
  answer: z.string().min(1),
  mode: z.string().optional(),
  tool_trace: z.array(z.unknown()).optional(),
}).passthrough();

const planComparisonKpisSchema = z.object({
  emergency_eta_minutes: z.number().nonnegative(),
  average_vehicle_wait_seconds: z.number().nonnegative(),
  maximum_queue_vehicles: z.number().int().nonnegative(),
  congested_segment_count: z.number().int().nonnegative(),
  crowd_evacuation_minutes: z.number().nonnegative().nullable(),
  pedestrian_service: z.string(),
  control_side_effect_wait_seconds: z.number(),
  focus_speed_kmh: z.number().nonnegative(),
  focus_saturation: z.number().min(0).max(1.5),
  ete_minutes: z.number().nonnegative().nullable(),
});

export const planComparisonSchema = z.object({
  simulation_run_id: z.string().min(1),
  scenario_id: z.string().min(1),
  data_snapshot_id: z.string().min(1),
  dataset_versions: z.record(z.string(), z.string().startsWith("sha256:")),
  simulation_config: z.object({
    step_seconds: z.number().int().positive(),
    horizon_minutes: z.number().int().positive(),
    random_seed: z.number().int().nonnegative(),
    controller_version: z.string(),
    manual_controls: z.object({
      green_extension_pct: z.number().min(0).max(25),
      diversion_share: z.number().min(0).max(.75),
      police_units: z.number().int().min(0),
    }).optional(),
  }),
  model_version: z.string(),
  randomness_used: z.literal(false),
  input_sha256: z.string().length(64),
  output_sha256: z.string().length(64),
  recommended_plan_id: z.string().nullable(),
  recommendation_reason: z.string(),
  score_formula: z.string(),
  plans: z.array(z.object({
    plan_id: z.string().min(1),
    name: z.string(),
    eligible: z.boolean(),
    ineligible_reason: z.string().nullable().optional(),
    state: z.string(),
    tradeoff: z.string(),
    score: z.number().nullable(),
    kpis: planComparisonKpisSchema,
    controls: z.object({
      green_extension_pct: z.number(), diversion_share: z.number(), police_units: z.number().int(),
    }).nullable().optional(),
    constraints: z.array(z.object({ code: z.string(), passed: z.boolean(), detail: z.string() })).optional(),
    executable_commands: z.array(z.record(z.string(), z.unknown())).optional(),
    forecast_series: z.array(z.object({
      minute: z.number(), focus_saturation: z.number(), focus_speed_kmh: z.number(),
    })).optional(),
  }).passthrough()).min(2),
  approval_status: z.enum(["READY_FOR_APPROVAL", "NO_FEASIBLE_PLAN", "APPROVED_FOR_SIMULATION"]),
  optimizer: z.object({
    method: z.string(), evaluated_candidate_count: z.number().int().nonnegative(),
    eligible_candidate_count: z.number().int().nonnegative(),
    decision_variables: z.record(z.string(), z.array(z.number())),
    hard_constraints: z.array(z.string()), forecast_horizon_minutes: z.number(),
    rolling_reoptimization_minutes: z.number(),
  }),
  kpi_evidence: z.record(z.string(), z.string()),
  limitations: z.array(z.string()),
}).passthrough();

export const planReplaySchema = z.object({
  simulation_run_id: z.string().min(1),
  replay_output_sha256: z.string().length(64),
  original_output_sha256: z.string().length(64),
  matches: z.boolean(),
  replayed_at: z.string(),
  random_seed: z.number().int().nonnegative(),
  model_version: z.string(),
});

export function validatePayload<T>(schema: z.ZodType, payload: unknown, label: string): T {
  const result = schema.safeParse(payload);
  if (!result.success) {
    const detail = result.error.issues.map((issue) => `${issue.path.join(".") || "root"}: ${issue.message}`).join("; ");
    throw new Error(`${label}資料驗證失敗：${detail}`);
  }
  return result.data as T;
}
