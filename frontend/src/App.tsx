import { useCallback, useEffect, useRef, useState } from "react";
import { api, type IncidentState, type SimView, type ValidationSlaMeasurement } from "./api";
import Cockpit from "./Cockpit";
import RecommendationView from "./RecommendationView";
import GlobeIntro from "./GlobeIntro";
import { AdvisorChatView, CitizenView, EmergencyModal, MonitorView, VerifyView } from "./views";

const TICK_MS = 2500; // 前端節奏：2.5 秒推進一個資料時間點

type Page = "overview" | "command" | "monitor" | "recommendation" | "verify" | "advisor" | "citizen";

const PAGES: [Page, string][] = [
  ["overview", "總覽"],
  ["command", "指揮中心"],
  ["monitor", "監測中心"],
  ["recommendation", "建議書"],
  ["verify", "紀錄與驗證"],
  ["advisor", "顧問對話"],
  ["citizen", "民眾端"],
];

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [view, setView] = useState<SimView | null>(null);
  const [incident, setIncident] = useState<IncidentState | null>(null);
  const [available, setAvailable] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(new Date());
  const [resourceKey, setResourceKey] = useState(0);
  const [simulationGeneration, setSimulationGeneration] = useState(0);
  const [validationSla, setValidationSla] = useState<ValidationSlaMeasurement | null>(null);
  const [acknowledgedIncidents, setAcknowledgedIncidents] = useState<Set<string>>(() => new Set());
  const playingRef = useRef(false);
  const pollingRef = useRef(false);
  const validationStartedRef = useRef<number | null>(null);

  useEffect(() => {
    api.incidents().then((r) => setAvailable(r.available)).catch(() => {});
    api.simState().then(setView).catch(() => {});
    const clock = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(clock);
  }, []);

  useEffect(() => {
    playingRef.current = view?.playing ?? false;
  }, [view?.playing]);

  useEffect(() => {
    if (page !== "command") return;
    const preventViewportWheelZoom = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) event.preventDefault();
    };
    const preventViewportKeyZoom = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && ["+", "-", "=", "0"].includes(event.key)) {
        event.preventDefault();
      }
    };
    window.addEventListener("wheel", preventViewportWheelZoom, { passive: false, capture: true });
    window.addEventListener("keydown", preventViewportKeyZoom, { capture: true });
    return () => {
      window.removeEventListener("wheel", preventViewportWheelZoom, { capture: true });
      window.removeEventListener("keydown", preventViewportKeyZoom, { capture: true });
    };
  }, [page]);

  useEffect(() => {
    const timer = setInterval(async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        const v = playingRef.current ? await api.simTick() : await api.simState();
        setView(v);
        const activeIncidentId = v.coordinator_cycle?.incident_id;
        if (playingRef.current && activeIncidentId) {
          setIncident(await api.incidentState(activeIncidentId));
        }
      } catch { /* 後端未啟動時靜默 */ }
      finally { pollingRef.current = false; }
    }, TICK_MS);
    return () => clearInterval(timer);
  }, []);

  const start = useCallback(async () => setView(await api.simStart(2)), []);
  const pause = useCallback(async () => {
    await api.simPause();
    setView(await api.simState());
  }, []);
  const seekPreIncident = useCallback(async () => {
    setView(await api.simSeek("2026-05-20 21:00"));
  }, []);

  const resetSimulation = useCallback(async () => {
    if (!window.confirm("將清除目前事件、調度、通報與救援走廊，並回到 21:00 基準。確定重新開始？")) return;
    setBusy(true);
    playingRef.current = false;
    try {
      const result = await api.simReset();
      setView(result.view);
      setIncident(null);
      setValidationSla(null);
      setAcknowledgedIncidents(new Set());
      validationStartedRef.current = null;
      setResourceKey((k) => k + 1);
      setSimulationGeneration((k) => k + 1);
    } catch (error) {
      window.alert(`重新開始失敗：${error instanceof Error ? error.message : "未知錯誤"}`);
    } finally {
      setBusy(false);
    }
  }, []);

  const inject = useCallback(async (id: string) => {
    setBusy(true);
    const started = performance.now();
    validationStartedRef.current = started;
    setValidationSla(null);
    try {
      const state = await api.inject(id);
      setAcknowledgedIncidents((current) => {
        const next = new Set(current);
        next.delete(state.incident_id);
        return next;
      });
      setIncident(state);
      setResourceKey((k) => k + 1); // 資源已被調度，刷新庫存
      // 事件時間點同步跳轉，讓地圖顏色與事件一致
      const nextView = await api.simSeek(state.event.timestamp);
      setView(nextView);
      setValidationSla({
        incident_id: state.incident_id,
        api_ready_ms: Math.round((performance.now() - started) * 100) / 100,
        map_rendered_ms: null,
        total_end_to_end_ms: null,
      });
    } finally {
      setBusy(false);
    }
  }, []);

  const markScenarioRendered = useCallback((incidentId: string) => {
    const started = validationStartedRef.current;
    if (started == null) return;
    setValidationSla((current) => {
      if (!current || current.incident_id !== incidentId || current.total_end_to_end_ms != null) return current;
      const total = Math.round((performance.now() - started) * 100) / 100;
      return {
        ...current,
        map_rendered_ms: Math.max(0, Math.round((total - current.api_ready_ms) * 100) / 100),
        total_end_to_end_ms: total,
      };
    });
  }, []);

  const refreshIncident = useCallback(async () => {
    if (!incident) return;
    const next = await api.incidentState(incident.incident_id);
    setIncident(next);
    if (next.operational_status === "RESOLVED") {
      setAcknowledgedIncidents((current) => new Set(current).add(next.incident_id));
    }
    setResourceKey((k) => k + 1);
  }, [incident]);

  const acknowledgeIncident = useCallback((incidentId: string) => {
    setAcknowledgedIncidents((current) => new Set(current).add(incidentId));
  }, []);

  const activateDecisionSimulation = useCallback(async () => {
    const nextView = await api.simStart(2);
    playingRef.current = true;
    setView(nextView);
    if (incident) {
      setIncident(await api.incidentState(incident.incident_id));
      setResourceKey((k) => k + 1);
    }
  }, [incident]);

  const seekTo = useCallback(async (ts: string) => {
    setView(await api.simSeek(ts));
  }, []);

  return (
    <div className={`app ${page === "command" ? "app-cockpit" : ""}`}>
      <header>
        <h1>城市應變 AI Command Center</h1>
        <nav className="page-nav">
          {PAGES.map(([id, label]) => (
            <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="clock">
          <span>模擬時間 <b>{view?.sim_time ?? "--:--"}</b></span>
          <span className="dim">系統時間 {now.toLocaleTimeString("zh-TW", { hour12: false })}</span>
        </div>
        <div className="controls">
          {view?.playing ? (
            <button onClick={pause}>⏸ 暫停</button>
          ) : (
            <button className="primary" onClick={start}>▶ 播放</button>
          )}
          <button onClick={seekPreIncident}>⏭ 跳至事件前 (21:00)</button>
          <button className="reset-simulation" disabled={busy} onClick={resetSimulation}>↺ 重新開始模擬</button>
          {view?.progress && (
            <span className="dim">{view.progress.index + 1}/{view.progress.total}</span>
          )}
        </div>
      </header>

      <EmergencyModal key={simulationGeneration} view={view} />

      {page === "command" && (
        <Cockpit
          view={view}
          incident={incident}
          available={available}
          busy={busy}
          resourceKey={resourceKey}
          simulationGeneration={simulationGeneration}
          validationSla={validationSla}
          incidentAcknowledged={Boolean(incident && acknowledgedIncidents.has(incident.incident_id))}
          onAcknowledgeIncident={acknowledgeIncident}
          onDecisionAccepted={activateDecisionSimulation}
          onScenarioRendered={markScenarioRendered}
          onInject={inject}
          onInjectedCustom={(state) => {
            setIncident(state);
            setAcknowledgedIncidents((current) => {
              const next = new Set(current);
              next.delete(state.incident_id);
              return next;
            });
            setValidationSla(null);
            validationStartedRef.current = null;
            setResourceKey((k) => k + 1);
            api.simSeek(state.event.timestamp).then(setView).catch(() => {});
          }}
          onRefresh={refreshIncident}
          onSeekIndex={seekTo}
        />
      )}

      {page === "overview" && <GlobeIntro onEnter={setPage} />}
      {page === "monitor" && <MonitorView view={view} resourceKey={resourceKey} />}
      {page === "recommendation" && <RecommendationView incident={incident} />}
      {page === "verify" && <VerifyView refreshKey={resourceKey} />}
      {page === "advisor" && <AdvisorChatView />}
      {page === "citizen" && <CitizenView />}
    </div>
  );
}
