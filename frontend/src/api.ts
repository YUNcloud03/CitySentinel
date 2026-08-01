// 後端 API 封裝。型別對應 backend/app 的回傳結構（demo 用寬鬆型別）。

export interface TrafficRow {
  road_name: string;
  avg_speed: number;
  vehicle_count: number;
  saturation_score: number;
  lane_status: string;
  congestion_level: "A" | "B" | "Normal";
  data_time: string;
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
  message?: string;
}

export interface IncidentState {
  incident_id: string;
  workflow_status: string;
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
  errors: string[];
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
  return res.json();
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
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
  route_details: {
    segment_id: string; name: string; length_m: number; signal_count: number;
    baseline_speed_kmh: number; corridor_speed_kmh: number; saturation_score: number;
    baseline_minutes: number; corridor_minutes: number; source: string; data_time: string | null;
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
    resource_type: string; requested_units: number; critical_segment_ids: string[]; reason: string;
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
    active_signal_device_ids: string[]; clearance_signal_device_ids: string[];
    intersection_states: { intersection_id: string; name: string; state: string; device_ids: string[];
      prepare_at_seconds: number; activate_at_seconds: number; passage_at_seconds: number; restore_at_seconds: number }[];
  };
  production_state_modified: false;
  limitations: string;
}

export const api = {
  simStart: (speed: number, start?: string) =>
    post<SimView>("/api/simulation/start", { speed, start_timestamp: start ?? null }),
  simPause: () => post<SimView>("/api/simulation/pause"),
  simSeek: (timestamp: string) => post<SimView>("/api/simulation/seek", { timestamp }),
  simTick: () => post<SimView>("/api/simulation/tick"),
  simState: () => get<SimView>("/api/simulation/state"),
  timeline: () => get<{ timestamps: string[]; markers: { index: number; time: string; kind: string | null }[] }>("/api/simulation/timeline"),
  inject: (event_id: string) => post<IncidentState>("/api/incidents/inject", { event_id }),
  incidents: () => get<{ available: any[]; processed: string[] }>("/api/incidents"),
  whatIfNL: (question: string) => post<any>("/api/what-if/nl", { question }),
  decisionSandbox: (payload: {
    name: string; at: string; focus_segment_id: string; actions: DecisionAction[];
    disruption?: string; disruption_segment_id?: string; disruption_load?: number;
  }) => post<DecisionResult>("/api/decision-sandbox", payload),
  greenCorridor: (payload: {
    at: string; origin_segment_id: string; destination_segment_id: string;
    vehicle_type: "Ambulance" | "FireEngine"; blocked_segment_ids: string[];
  }) => post<GreenCorridorResult>("/api/green-corridor/simulate", payload),
  approveGreenCorridor: (scenarioId: string, approvedBy = "指揮官") =>
    post<GreenCorridorResult>(`/api/green-corridor/${scenarioId}/approve`, { approved_by: approvedBy }),
  greenCorridorState: (scenarioId: string, elapsedSeconds: number) =>
    get<GreenCorridorResult["runtime_state"]>(`/api/green-corridor/${scenarioId}/state?elapsed_seconds=${elapsedSeconds}`),
  roadNetwork: () => get<any[]>("/api/road-network"),
  sop: () => get<{ rule_id: number; title: string; text: string }[]>("/api/sop"),
  resources: () => get<Resource[]>("/api/resources"),
  resetResources: () => post<any>("/api/resources/reset"),
  incidentState: (id: string) => get<IncidentState>(`/api/incidents/${id}`),
  notifications: () => get<any[]>("/api/notifications"),
  notificationOp: (id: string, op: "approve" | "dispatch" | "retry") =>
    post<any>(`/api/notifications/${id}/${op}`),
  customIncident: (payload: any) => post<IncidentState>("/api/incidents/custom", payload),
  aiSummary: (incidentId: string) => post<any>(`/api/incidents/${incidentId}/ai-summary`),
  llmStatus: () => get<{ provider: string | null; available: boolean }>("/api/llm/status"),
  logs: () => get<any[]>("/api/logs"),
  history: (until?: string) =>
    get<any>(`/api/history${until ? `?until=${encodeURIComponent(until)}` : ""}`),
  advisorChat: (question: string, history: { role: string; text: string }[] = []) =>
    post<any>("/api/advisor/chat", { question, history }),
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
