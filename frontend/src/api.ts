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

export const api = {
  simStart: (speed: number, start?: string) =>
    post<SimView>("/api/simulation/start", { speed, start_timestamp: start ?? null }),
  simPause: () => post<SimView>("/api/simulation/pause"),
  simSeek: (timestamp: string) => post<SimView>("/api/simulation/seek", { timestamp }),
  simTick: () => post<SimView>("/api/simulation/tick"),
  simState: () => get<SimView>("/api/simulation/state"),
  inject: (event_id: string) => post<IncidentState>("/api/incidents/inject", { event_id }),
  incidents: () => get<{ available: any[]; processed: string[] }>("/api/incidents"),
  whatIfNL: (question: string) => post<any>("/api/what-if/nl", { question }),
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
  dispatchAction: (
    incidentId: string,
    actionId: string,
    op: "accept" | "reject" | "adjust",
    extra: { count?: number; reason?: string; operator?: string } = {}
  ) => post<any>(`/api/incidents/${incidentId}/dispatch/${actionId}`, { op, ...extra }),
};
