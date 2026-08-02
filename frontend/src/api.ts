// 後端 API 封裝。關鍵決策資料會在 API 邊界經 Zod 驗證後才進入 UI。
import type { ZodType } from "zod";
import {
  advisorAnswerSchema,
  customIncidentInputSchema,
  greenCorridorSchema,
  incidentStateSchema,
  planComparisonSchema,
  planReplaySchema,
  runtimeStateSchema,
  simViewSchema,
  validatePayload,
} from "./schemas";

export interface TrafficRow {
  road_name: string;
  avg_speed: number;
  vehicle_count: number;
  saturation_score: number;
  lane_status: string;
  congestion_level: "A" | "B" | "Normal";
  data_time: string;
  simulation_source?: "organizer_dataset" | "incident_projection";
  baseline_avg_speed?: number;
  baseline_vehicle_count?: number;
  baseline_saturation_score?: number;
  event_avg_speed?: number;
  event_vehicle_count?: number;
  event_saturation_score?: number;
}

export interface CrowdRow {
  location_name: string;
  user_count: number;
  growth_rate: number;
  roaming_user_pct: number;
  data_time: string;
}

export interface Alert {
  rule_id: number;
  entity_id: string;
  evidence: Record<string, unknown>;
  actions: string[];
}

export interface SimView {
  playing: boolean;
  speed?: number;
  sim_time: string | null;
  progress?: { index: number; total: number };
  traffic?: Record<string, TrafficRow>;
  crowd?: Record<string, CrowdRow>;
  active_alerts?: Alert[];
  simulation_context?: {
    active: boolean;
    model: string;
    incident_id?: string;
    starts_at?: string;
    elapsed_minutes?: number;
    affected_segment_id?: string;
    affected_station_id?: string;
    changed_segment_ids?: string[];
    changed_station_ids?: string[];
    dynamic_routing?: any;
    baseline_source?: string;
    deterministic?: boolean;
    formula?: Record<string, string>;
    response_phase?: "OBSTACLE_ACTIVE" | "DISPATCHING" | "CLEARANCE_ACTIVE" | "CLEARED";
    response_started_at?: string | null;
    accepted_action_ids?: string[];
    action_effectiveness?: Record<string, number>;
    accepted_action_ratio?: number;
    mitigation_progress?: number;
    capacity_factor?: number;
    next_review_at?: string;
    review_overdue?: boolean;
    production_state_modified?: false;
    reason?: string;
  };
  scenario_comparison?: ScenarioComparison | null;
  coordinator_cycle?: {
    active: boolean;
    incident_id?: string | null;
    replanned_run_id?: string;
    closed_loop?: ClosedLoopState | null;
  };
  message?: string;
}

export interface ClosedLoopState {
  mode: "SUPERVISED_CLOSED_LOOP" | string;
  status: string;
  cycle_count: number;
  replan_count: number;
  review_interval_minutes: number;
  next_review_at: string;
  last_evaluated_at?: string | null;
  pending_human_gate?: string | null;
  latest_plan_run_id?: string | null;
  latest_metrics?: Record<string, any> | null;
  objectives: Record<string, any>;
  safety_policy: {
    automatic: string[];
    approval_required: string[];
    llm_authority: string;
  };
  cycles: any[];
}

export interface ScenarioComparisonMetrics {
  avg_speed: number;
  vehicle_count: number;
  saturation_score: number;
  congestion_level: "A" | "B" | "Normal";
}

export interface ScenarioComparisonRow {
  available: boolean;
  state: string;
  locked_reason?: string | null;
  effect_started?: boolean;
  metrics: ScenarioComparisonMetrics | null;
  ete: {
    ete_minutes: number;
    ete_minutes_display: number;
    formula: string;
  } | null;
  source: string | null;
}

export interface ScenarioComparison {
  simulation_run_id: string;
  input_sha256: string;
  as_of: string;
  affected_segment_id: string;
  affected_road_name: string;
  model: string;
  randomness_used: false;
  scenarios: {
    baseline: ScenarioComparisonRow;
    incident: ScenarioComparisonRow;
    treatment: ScenarioComparisonRow;
  };
  ete_definition: string;
}

export interface ValidationSlaMeasurement {
  incident_id: string;
  api_ready_ms: number;
  map_rendered_ms: number | null;
  total_end_to_end_ms: number | null;
}

export interface SimulationResetResult {
  status: "reset";
  baseline_timestamp: string;
  cleared: {
    incidents: number;
    notifications: number;
    green_corridors: number;
    custom_runs: number;
    plan_comparison_runs: number;
    llm_audit_entries: number;
  };
  view: SimView;
}

export interface IncidentState {
  incident_id: string;
  workflow_status: string;
  operational_status?: "IMPACT_ACTIVE" | "RESPONSE_AUTHORIZED" | "RESOLVED" | string;
  resolved_at?: string | null;
  current_step: string;
  event: Record<string, any>;
  as_of: string;
  triggered_rules: number[];
  trigger_details?: Alert[];
  routing_result: any;
  ete_result: any;
  dispatch: any;
  rule_attribution?: {
    caused_by_incident: number[];
    context_rules: number[];
    calculation_rules: number[];
  };
  sop_evidence: { rule_id: number; title: string; text: string }[];
  notifications: any;
  decision_trace: { step: string; at: string; detail: any }[];
  coordinator_summary?: {
    verdict: string;
    situation?: string;
    impact?: string;
    actions: string[];
    recommendation?: string;
    tradeoffs?: string;
    expected_improvement?: string;
    escalation: string;
    basis: string;
    evidence_contract?: Record<string, any>;
  };
  confidence?: {
    confidence_score: number;
    level: string;
    evidence: string[];
  };
  notification_id?: string;
  performance?: {
    routing_latency_ms?: number | null;
    total_processing_ms: number;
    requirement_limit_ms: number;
    within_60_seconds: boolean;
    measurement_scope: string;
  };
  simulation_run_id?: string;
  input_sha256?: string;
  errors: string[];
  closed_loop?: ClosedLoopState;
}

export interface PlanComparisonKpis {
  emergency_eta_minutes: number;
  average_vehicle_wait_seconds: number;
  maximum_queue_vehicles: number;
  congested_segment_count: number;
  crowd_evacuation_minutes: number | null;
  pedestrian_service: string;
  control_side_effect_wait_seconds: number;
  focus_speed_kmh: number;
  focus_saturation: number;
  ete_minutes: number | null;
}

export interface PlanComparisonPlan {
  plan_id: string;
  name: string;
  eligible: boolean;
  ineligible_reason?: string | null;
  state: string;
  tradeoff: string;
  score: number | null;
  kpis: PlanComparisonKpis;
  controls?: ManualPlanControls | null;
  constraints?: { code: string; passed: boolean; detail: string }[];
  executable_commands?: Record<string, unknown>[];
  forecast_series?: { minute: number; focus_saturation: number; focus_speed_kmh: number }[];
}

export interface ManualPlanControls {
  green_extension_pct: number;
  diversion_share: number;
  police_units: number;
}

export interface PlanComparisonRun {
  simulation_run_id: string;
  scenario_id: string;
  data_snapshot_id: string;
  dataset_versions: Record<string, string>;
  simulation_config: {
    step_seconds: number;
    horizon_minutes: number;
    random_seed: number;
    controller_version: string;
  };
  model_version: string;
  randomness_used: false;
  input_sha256: string;
  output_sha256: string;
  recommended_plan_id: string | null;
  recommendation_reason: string;
  score_formula: string;
  plans: PlanComparisonPlan[];
  kpi_evidence: Record<string, string>;
  limitations: string[];
  approval_status: "READY_FOR_APPROVAL" | "NO_FEASIBLE_PLAN" | "APPROVED_FOR_SIMULATION";
  optimizer: {
    method: string; evaluated_candidate_count: number; eligible_candidate_count: number;
    decision_variables: Record<string, number[]>; hard_constraints: string[];
    forecast_horizon_minutes: number; rolling_reoptimization_minutes: number;
  };
}

export interface PlanComparisonReplay {
  simulation_run_id: string;
  replay_output_sha256: string;
  original_output_sha256: string;
  matches: boolean;
  replayed_at: string;
  random_seed: number;
  model_version: string;
}

async function post<T>(url: string, body?: unknown, schema?: ZodType): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
  const payload: unknown = await res.json();
  return schema ? validatePayload<T>(schema, payload, url) : payload as T;
}

async function get<T>(url: string, schema?: ZodType): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.statusText);
  const payload: unknown = await res.json();
  return schema ? validatePayload<T>(schema, payload, url) : payload as T;
}

export interface Resource {
  resource_id: string;
  resource_type: string;
  label: string;
  total_count: number;
  available_count: number;
  current_location: string;
  eta_minutes: number;
  status: string;
}

export interface DecisionAction {
  type: "extend_green" | "open_lane" | "divert" | "police_control";
  segment_id: string;
  target_segment_id?: string;
  share?: number;
  strength?: number;
}

export interface DecisionResult {
  scenario_name: string;
  as_of: string;
  focus_segment_id: string;
  focus_name: string;
  baseline_traffic: Record<string, any>;
  projected_traffic: Record<string, any>;
  baseline_metrics: Record<string, number>;
  projected_metrics: Record<string, number>;
  delta: Record<string, number>;
  series: { minute: number; focus_saturation: number; network_saturation: number }[];
  applied_actions: any[];
  disruption: string;
  verdict: string;
  model: string;
  production_state_modified: boolean;
  signal_plan?: {
    cycle_seconds: number; formula: string; model: string;
    approaches: { segment_id: string; name: string; demand_score: number; next_green_seconds: number;
      safety_minimum_green_seconds: number; wait_time_source: string }[];
  } | null;
  evidence_contract?: Record<string, any>;
}

export interface GreenCorridorResult {
  scenario_id: string;
  as_of: string;
  vehicle_type: "Ambulance" | "FireEngine";
  priority: "EMERGENCY";
  route_segment_ids: string[];
  route_names: string[];
  route_geometry: [number, number][];
  route_details: {
    segment_id: string; name: string; length_m: number; signal_count: number;
    baseline_speed_kmh: number; corridor_speed_kmh: number; saturation_score: number;
    baseline_minutes: number; corridor_minutes: number; source: string; data_time: string | null;
    route_cost_seconds: number; congestion_multiplier: number; impassable: boolean;
  }[];
  blocked_segment_ids: string[];
  eta: {
    before_minutes: number; after_minutes: number; saved_minutes: number;
    improvement_pct: number; formula: string;
  };
  signal_actions: {
    intersection_id: string; device_id: string; name: string; segment_id: string; coordinates: [number, number];
    action: "EMERGENCY_GREEN"; prepare_at_seconds: number; activate_at_seconds: number;
    passage_at_seconds: number; restore_at_seconds: number;
    pedestrian_clearance_seconds: number; reason: string;
  }[];
  dispatch_recommendation: {
    resource_type: string; requested_units: number; critical_segment_ids: string[]; reason: string; unit_id?: string;
  };
  mission?: {
    mode: "AUTO_HOSPITAL_ROUND_TRIP";
    incident_id: string;
    status?: "TO_SCENE" | "ON_SCENE" | "TO_HOSPITAL" | "COMPLETED";
    scene: { name: string; segment_id: string; coordinates: [number, number] };
    ambulance: { unit_id: string; status: string; inventory_source: string };
    dispatch_hospital: { hospital_id: string; name: string; address: string; coordinates: [number, number]; segment_id: string };
    receiving_hospital: { hospital_id: string; name: string; address: string; coordinates: [number, number]; segment_id: string; ed_load: number; accepting: boolean };
    on_scene_service_seconds: number;
    legs: {
      leg_id: "TO_SCENE" | "TO_HOSPITAL"; label: string; start_name: string; end_name: string;
      route_segment_ids: string[]; route_names: string[]; route_geometry: [number, number][];
      route_details: GreenCorridorResult["route_details"]; eta: GreenCorridorResult["eta"];
      start_seconds: number; travel_end_seconds: number; end_seconds: number;
    }[];
  };
  messages: Record<"zh" | "en" | "ja" | "ko", string>;
  evidence: Record<string, any>;
  decision_trace: { step: string; detail: any }[];
  model: string;
  approval_status: "READY_FOR_APPROVAL" | "APPROVED_FOR_SIMULATION";
  approved_by?: string;
  approved_at?: string;
  runtime_state: {
    elapsed_seconds: number; total_seconds: number; completed: boolean;
    current_intersection_id: string | null;
    current_intersection_name?: string | null;
    active_signal_device_ids: string[]; clearance_signal_device_ids: string[];
    vehicle_position: [number, number] | null;
    vehicle_progress_pct: number;
    current_leg_progress_pct?: number;
    mission_phase?: "AWAITING_APPROVAL" | "TO_SCENE" | "ON_SCENE" | "TO_HOSPITAL" | "COMPLETED" | "SINGLE_LEG";
    current_leg_id?: "TO_SCENE" | "TO_HOSPITAL" | null;
    vehicle_position_source: "simulated_from_route_geometry_and_corridor_elapsed_time";
    next_intersection_id: string | null;
    next_intersection_name?: string | null;
    intersection_states: { intersection_id: string; name: string; state: string; device_ids: string[];
      prepare_at_seconds: number; activate_at_seconds: number; passage_at_seconds: number; restore_at_seconds: number }[];
  };
  production_state_modified: false;
  limitations: string;
}

export const api = {
  simStart: (speed: number, start?: string) =>
    post<SimView>("/api/simulation/start", { speed, start_timestamp: start ?? null }, simViewSchema),
  simPause: () => post<SimView>("/api/simulation/pause"),
  simSeek: (timestamp: string) => post<SimView>("/api/simulation/seek", { timestamp }, simViewSchema),
  simTick: () => post<SimView>("/api/simulation/tick", undefined, simViewSchema),
  simState: () => get<SimView>("/api/simulation/state", simViewSchema),
  simReset: () => post<SimulationResetResult>("/api/simulation/reset"),
  createPlanComparison: (incidentId: string, randomSeed = 42, manualControls?: ManualPlanControls) =>
    post<PlanComparisonRun>("/api/simulation/plan-comparison", {
      incident_id: incidentId,
      random_seed: randomSeed,
      manual_controls: manualControls,
    }, planComparisonSchema),
  approvePlanComparison: (runId: string, planId: string, approvedBy = "指揮官") =>
    post<{ simulation_run_id: string; scenario_id: string; approval_status: string; approved_plan: Record<string, unknown> }>(
      `/api/simulation/plan-comparison/${runId}/approve`, { plan_id: planId, approved_by: approvedBy }),
  replayPlanComparison: (runId: string) =>
    post<PlanComparisonReplay>(`/api/simulation/plan-comparison/${runId}/replay`, undefined, planReplaySchema),
  timeline: () => get<{ timestamps: string[]; markers: { index: number; time: string; kind: string | null }[] }>("/api/simulation/timeline"),
  inject: (event_id: string) => post<IncidentState>("/api/incidents/inject", { event_id }, incidentStateSchema),
  incidents: () => get<{ available: any[]; processed: string[] }>("/api/incidents"),
  whatIfNL: (question: string) => post<any>("/api/what-if/nl", { question }),
  decisionSandbox: (payload: {
    name: string; at: string; focus_segment_id: string; actions: DecisionAction[];
    disruption?: string; disruption_segment_id?: string; disruption_load?: number;
  }) => post<DecisionResult>("/api/decision-sandbox", payload),
  greenCorridor: (payload: {
    at: string; origin_segment_id?: string; destination_segment_id?: string;
    vehicle_type: "Ambulance" | "FireEngine"; blocked_segment_ids: string[];
    auto_dispatch?: boolean; incident_id?: string;
  }) => post<GreenCorridorResult>("/api/green-corridor/simulate", payload, greenCorridorSchema),
  approveGreenCorridor: (scenarioId: string, approvedBy = "指揮官") =>
    post<GreenCorridorResult>(`/api/green-corridor/${scenarioId}/approve`, { approved_by: approvedBy }, greenCorridorSchema),
  greenCorridorState: (scenarioId: string, elapsedSeconds: number) =>
    get<GreenCorridorResult["runtime_state"]>(`/api/green-corridor/${scenarioId}/state?elapsed_seconds=${elapsedSeconds}`, runtimeStateSchema),
  roadNetwork: () => get<any[]>("/api/road-network"),
  crowdStations: () => get<{ station_id: string; name: string }[]>("/api/crowd-stations"),
  sop: () => get<{ rule_id: number; title: string; text: string }[]>("/api/sop"),
  resources: () => get<Resource[]>("/api/resources"),
  resetResources: () => post<any>("/api/resources/reset"),
  incidentState: (id: string) => get<IncidentState>(`/api/incidents/${id}`),
  resolveIncident: (id: string, reason: string, operator = "traffic_commander_01") =>
    post<IncidentState>(`/api/incidents/${id}/resolve`, { reason, operator }, incidentStateSchema),
  notifications: () => get<any[]>("/api/notifications"),
  notificationOp: (id: string, op: "approve" | "dispatch" | "retry") =>
    post<any>(`/api/notifications/${id}/${op}`),
  customIncident: (payload: any) => {
    const validated = validatePayload<Record<string, unknown>>(customIncidentInputSchema, payload, "自訂事件輸入");
    return post<IncidentState>("/api/incidents/custom", validated, incidentStateSchema);
  },
  recommendation: (incidentId: string) =>
    get<any>(`/api/incidents/${incidentId}/recommendation`),
  aiSummary: (incidentId: string) => post<any>(`/api/incidents/${incidentId}/ai-summary`),
  llmStatus: () => get<{ provider: string | null; available: boolean }>("/api/llm/status"),
  logs: () => get<any[]>("/api/logs"),
  history: (until?: string) =>
    get<any>(`/api/history${until ? `?until=${encodeURIComponent(until)}` : ""}`),
  advisorChat: (question: string, history: { role: string; text: string }[] = []) =>
    post<any>("/api/advisor/chat", { question, history }, advisorAnswerSchema),
  alertSummary: (alert: { rule_id: number; entity_id: string; sim_time?: string | null; evidence?: any; actions?: string[] }) =>
    post<{ summary: string; source: string }>("/api/alerts/summary", alert),
  confidence: () => get<any[]>("/api/confidence"),
  provenance: () => get<any>("/api/provenance"),
  dispatchAction: (
    incidentId: string,
    actionId: string,
    op: "accept" | "reject" | "adjust" | "preempt",
    extra: {
      count?: number; reason?: string; operator?: string;
      source_incident_id?: string; source_action_id?: string;
    } = {}
  ) => post<any>(`/api/incidents/${incidentId}/dispatch/${actionId}`, { op, ...extra }),
};
