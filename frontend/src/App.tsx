import { useCallback, useEffect, useRef, useState } from "react";
import { api, type IncidentState, type SimView } from "./api";
import Cockpit from "./Cockpit";
import RecommendationView from "./RecommendationView";
import GlobeIntro from "./GlobeIntro";
import { AdvisorChatView, CitizenView, MonitorView, VerifyView } from "./views";

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
  const playingRef = useRef(false);

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
    const timer = setInterval(async () => {
      // 分頁不可見時不推進，避免背景空轉；切回來會立即補一次。
      if (document.hidden) return;
      try {
        const v = playingRef.current ? await api.simTick() : await api.simState();
        setView(v);
      } catch { /* 後端未啟動時靜默 */ }
    }, TICK_MS);
    const onVisible = () => {
      if (document.hidden) return;
      api.simState().then((v) => { if (v?.sim_time) setView(v); }).catch(() => {});
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const start = useCallback(async () => setView(await api.simStart(2)), []);
  const pause = useCallback(async () => {
    await api.simPause();
    setView(await api.simState());
  }, []);
  const seekPreIncident = useCallback(async () => {
    setView(await api.simSeek("2026-05-20 21:00"));
  }, []);

  const inject = useCallback(async (id: string) => {
    setBusy(true);
    try {
      const state = await api.inject(id);
      setIncident(state);
      setResourceKey((k) => k + 1); // 資源已被調度，刷新庫存
      // 事件時間點同步跳轉，讓地圖顏色與事件一致
      setView(await api.simSeek(state.event.timestamp));
    } finally {
      setBusy(false);
    }
  }, []);

  const refreshIncident = useCallback(async () => {
    if (!incident) return;
    // 調度／核准後立刻同步事件、庫存與地圖快照，不等下一次輪詢。
    const [state, v] = await Promise.all([
      api.incidentState(incident.incident_id),
      api.simState().catch(() => null),
    ]);
    setIncident(state);
    // 播放器尚未定位時 simState 沒有快照欄位，覆蓋上去會讓地圖整片清空。
    if (v?.sim_time) setView(v);
    setResourceKey((k) => k + 1);
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
          {view?.progress && (
            <span className="dim">{view.progress.index + 1}/{view.progress.total}</span>
          )}
        </div>
      </header>

      {page === "command" && (
        <Cockpit
          view={view}
          incident={incident}
          available={available}
          busy={busy}
          resourceKey={resourceKey}
          onInject={inject}
          onInjectedCustom={(state) => {
            setIncident(state);
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
