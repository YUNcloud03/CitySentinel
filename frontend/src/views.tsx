// 監測中心與系統紀錄兩個分頁。
import { useEffect, useState } from "react";
import { api, type SimView } from "./api";
import { AlertFeed, CrowdPanel, ResourcePanel, TrafficPanel } from "./components";

// ---- 迷你趨勢圖（純 SVG，無外部套件） ----

function Sparkline({ points, max, thresholds }: {
  points: number[];
  max: number;
  thresholds?: [number, number]; // [黃, 紅]，以原始值計
}) {
  const w = 130, h = 30;
  if (points.length < 2) return <svg width={w} height={h} />;
  const step = w / (points.length - 1);
  const y = (v: number) => h - 2 - (Math.min(v, max) / max) * (h - 4);
  const path = points
    .map((p, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${y(p).toFixed(1)}`)
    .join(" ");
  const last = points[points.length - 1];
  const color = thresholds
    ? last >= thresholds[1] ? "#ef4444" : last >= thresholds[0] ? "#f59e0b" : "#22c55e"
    : "#38bdf8";
  return (
    <svg width={w} height={h}>
      {thresholds && (
        <>
          <line x1={0} x2={w} y1={y(thresholds[0])} y2={y(thresholds[0])}
            stroke="#f59e0b" strokeWidth={0.5} strokeDasharray="3 3" opacity={0.5} />
          <line x1={0} x2={w} y1={y(thresholds[1])} y2={y(thresholds[1])}
            stroke="#ef4444" strokeWidth={0.5} strokeDasharray="3 3" opacity={0.5} />
        </>
      )}
      <path d={path} fill="none" stroke={color} strokeWidth={1.6} />
      <circle cx={w - step * 0} cy={y(last)} r={2.2} fill={color}
        transform={`translate(${(points.length - 1) * step - w},0)`} />
    </svg>
  );
}

function TrendPanel({ simTime }: { simTime: string | null }) {
  const [history, setHistory] = useState<any>(null);

  useEffect(() => {
    api.history(simTime ?? undefined).then(setHistory).catch(() => {});
  }, [simTime]);

  if (!history) return null;
  const trafficRows = Object.entries<any>(history.traffic)
    .filter(([, v]) => v.points.length >= 2)
    .sort((a, b) => b[1].points.at(-1).sat - a[1].points.at(-1).sat);
  const crowdRows = Object.entries<any>(history.crowd)
    .filter(([, v]) => v.points.length >= 2)
    .sort((a, b) => b[1].points.at(-1).users - a[1].points.at(-1).users);

  return (
    <div className="panel">
      <h3>趨勢（至模擬時間 {simTime ?? "—"}）</h3>
      <div className="trend-grid">
        <div>
          <h4>路段飽和度</h4>
          {trafficRows.map(([id, v]) => (
            <div className="trend-row" key={id}>
              <span className="trend-name" title={id}>{v.name}</span>
              <Sparkline points={v.points.map((p: any) => p.sat)} max={1} thresholds={[0.85, 0.95]} />
              <span className="trend-value">{v.points.at(-1).sat.toFixed(2)}</span>
            </div>
          ))}
        </div>
        <div>
          <h4>場站人數</h4>
          {crowdRows.map(([id, v]) => (
            <div className="trend-row" key={id}>
              <span className="trend-name" title={id}>{v.name}</span>
              <Sparkline points={v.points.map((p: any) => p.users)} max={40000} />
              <span className="trend-value">{v.points.at(-1).users.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- 監測中心 ----

export function MonitorView({ view, resourceKey }: { view: SimView | null; resourceKey: number }) {
  return (
    <main className="monitor-grid">
      <div className="col">
        <TrafficPanel traffic={view?.traffic ?? {}} />
        <CrowdPanel crowd={view?.crowd ?? {}} />
      </div>
      <div className="col">
        <TrendPanel simTime={view?.sim_time ?? null} />
      </div>
      <div className="col">
        <AlertFeed alerts={view?.active_alerts ?? []} />
        <ResourcePanel refreshKey={resourceKey} />
      </div>
    </main>
  );
}

// ---- 系統紀錄 ----

const LOG_CATEGORIES = ["全部", "監測預警", "事件處理", "人工覆寫", "通報", "模擬"];
const CATEGORY_COLORS: Record<string, string> = {
  監測預警: "amber", 事件處理: "red", 人工覆寫: "cyan", 通報: "green", 模擬: "purple",
};

export function LogsView() {
  const [entries, setEntries] = useState<any[]>([]);
  const [filter, setFilter] = useState("全部");

  const reload = () => { api.logs().then(setEntries).catch(() => {}); };
  useEffect(() => {
    reload();
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, []);

  const shown = filter === "全部" ? entries : entries.filter((e) => e.category === filter);

  return (
    <main className="logs-view">
      <div className="panel">
        <h3>
          系統紀錄
          <span className="dim small">（{shown.length} 筆，5 秒自動更新）</span>
        </h3>
        <div className="log-filters">
          {LOG_CATEGORIES.map((c) => (
            <button key={c} className={filter === c ? "primary" : ""} onClick={() => setFilter(c)}>
              {c}
            </button>
          ))}
        </div>
        {shown.length === 0 && <p className="dim">尚無紀錄——啟動播放或注入事件後產生。</p>}
        <div className="log-list">
          {shown.map((e, i) => (
            <div className="log-entry" key={i}>
              <span className="log-time">{e.at}</span>
              <span className={`log-cat cat-${CATEGORY_COLORS[e.category] ?? ""}`}>{e.category}</span>
              <div className="log-body">
                <div className="log-title">
                  {e.title}
                  {e.sim_time && <span className="dim small">｜模擬時間 {e.sim_time}</span>}
                </div>
                <div className="log-detail dim">{e.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
