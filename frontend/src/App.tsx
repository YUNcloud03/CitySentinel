import { useCallback, useEffect, useRef, useState } from "react";
import { api, type IncidentState, type SimView } from "./api";
import MapView from "./MapView";
import {
  AlertFeed,
  CrowdPanel,
  IncidentPanel,
  StatusCards,
  TracePanel,
  TrafficPanel,
  WhatIfPanel,
} from "./components";

const TICK_MS = 2500; // 前端節奏：2.5 秒推進一個資料時間點

export default function App() {
  const [view, setView] = useState<SimView | null>(null);
  const [incident, setIncident] = useState<IncidentState | null>(null);
  const [available, setAvailable] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(new Date());
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
      try {
        const v = playingRef.current ? await api.simTick() : await api.simState();
        setView(v);
      } catch { /* 後端未啟動時靜默 */ }
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

  const inject = useCallback(async (id: string) => {
    setBusy(true);
    try {
      const state = await api.inject(id);
      setIncident(state);
      // 事件時間點同步跳轉，讓地圖顏色與事件一致
      setView(await api.simSeek(state.event.timestamp));
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="app">
      <header>
        <h1>城市應變 AI Command Center</h1>
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

      <StatusCards view={view} incident={incident} />

      <main>
        <div className="col left">
          <TrafficPanel traffic={view?.traffic ?? {}} />
          <CrowdPanel crowd={view?.crowd ?? {}} />
        </div>
        <div className="col center">
          <MapView view={view} incident={incident} />
          <AlertFeed alerts={view?.active_alerts ?? []} />
        </div>
        <div className="col right">
          <IncidentPanel
            available={available}
            incident={incident}
            onInject={inject}
            busy={busy}
          />
        </div>
      </main>

      <footer>
        <TracePanel incident={incident} />
        <WhatIfPanel />
      </footer>
    </div>
  );
}
