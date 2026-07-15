// 監測中心、紀錄與驗證、顧問對話、民眾端手機模擬、緊急彈窗。
import { useEffect, useRef, useState } from "react";
import { api, type Alert, type SimView } from "./api";
import { AlertFeed, CrowdPanel, ResourcePanel, RuleBadge, TrafficPanel } from "./components";

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

function LogListPanel() {
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
  );
}

function ConfidencePanel({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    api.confidence().then(setItems).catch(() => {});
  }, [refreshKey]);

  return (
    <div className="panel">
      <h3>事件可信度（多源交叉驗證）</h3>
      {items.length === 0 && <p className="dim">注入事件後顯示信心分數與證據。</p>}
      {items.map((c) => (
        <div className="conf-card" key={c.incident_id}>
          <div className="conf-head">
            <b>{c.incident_id}</b>
            <span className={`conf-score lv-${c.level}`}>
              {(c.confidence_score * 100).toFixed(0)}%｜{c.level}
            </span>
          </div>
          <ul className="conf-evidence">
            {c.evidence.map((e: string, i: number) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      ))}
      {items.length > 0 && (
        <p className="dim small">分數僅供指揮官參考；正式處置依 SOP Rule Engine。</p>
      )}
    </div>
  );
}

function ProvenancePanel() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.provenance().then(setData).catch(() => {}); }, []);
  if (!data) return null;
  return (
    <div className="panel">
      <h3>資料佐證（可重算驗證）</h3>
      <table>
        <thead><tr><th>來源檔</th><th>筆數</th></tr></thead>
        <tbody>
          {data.data_sources.map((f: any) => (
            <tr key={f.file}>
              <td title={f.sha256 ? `SHA256 ${f.sha256}` : ""}>
                {f.file}{f.note && <span className="dim small">（{f.note}）</span>}
              </td>
              <td>{f.records}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details>
        <summary>引擎門檻常數</summary>
        <pre className="mono small">{JSON.stringify(data.engine_constants, null, 2)}</pre>
      </details>
      <p className="dim small">{data.note}</p>
    </div>
  );
}

export function VerifyView({ refreshKey }: { refreshKey: number }) {
  return (
    <main className="verify-grid">
      <LogListPanel />
      <div className="col">
        <ConfidencePanel refreshKey={refreshKey} />
        <ProvenancePanel />
      </div>
    </main>
  );
}

// ---- 顧問對話 ----

const CHAT_SUGGESTIONS = [
  "如果 17:00 BL17 人數增加到 40000 人會怎樣？",
  "SOP 2 的內容是什麼？",
  "目前事件的處置重點是什麼？",
  "如果封閉忠孝東路會怎樣？",
];

type ChatMsg = { role: "user" | "advisor"; text: string; meta?: any };

export function AdvisorChatView() {
  const [messages, setMessages] = useState<ChatMsg[]>([{
    role: "advisor",
    text: "我是交控 AI 顧問。可以問我 What-if 假設分析、SOP 條款內容，或當前事件的處置諮詢。我只提供建議，不會執行任何調度或發布。",
  }]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const ask = async (q: string) => {
    if (!q.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.advisorChat(q);
      setMessages((m) => [...m, { role: "advisor", text: res.answer, meta: res }]);
    } catch (e: any) {
      setMessages((m) => [...m, { role: "advisor", text: `查詢失敗：${e.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="chat-view">
      <div className="panel chat-panel">
        <h3>顧問對話</h3>
        <div className="chat-messages">
          {messages.map((m, i) => (
            <div className={`chat-msg ${m.role}`} key={i}>
              <div className="chat-bubble">
                <div className="chat-text">{m.text}</div>
                {m.meta?.cited_rule_ids?.length > 0 && (
                  <div className="chat-cites">
                    {m.meta.cited_rule_ids.map((r: number) => <RuleBadge key={r} id={r} />)}
                  </div>
                )}
                {m.meta?.kind === "whatif" && m.meta.whatif_result && (
                  <div className="chat-whatif dim small">
                    基準觸發 {JSON.stringify(m.meta.whatif_result.baseline.triggered_rules)} →
                    假設後 {JSON.stringify(m.meta.whatif_result.sandbox.triggered_rules)}
                    ｜正式狀態未修改｜解析方式 {m.meta.parsed_by}
                  </div>
                )}
                {m.meta?.provider && (
                  <div className="dim small">LLM：{m.meta.provider}</div>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="chat-msg advisor"><div className="chat-bubble dim">思考中…</div></div>}
          <div ref={bottomRef} />
        </div>
        <div className="presets">
          {CHAT_SUGGESTIONS.map((s) => (
            <button key={s} disabled={busy} onClick={() => ask(s)}>{s}</button>
          ))}
        </div>
        <div className="ask-row">
          <input
            value={input}
            placeholder="輸入問題…（What-if / SOP / 事件諮詢）"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask(input)}
          />
          <button className="primary" disabled={busy || !input.trim()} onClick={() => ask(input)}>
            送出
          </button>
        </div>
      </div>
    </main>
  );
}

// ---- 民眾端手機模擬（PWS 風格疏散警報） ----

const PHONE_LANGS: [string, string][] = [
  ["auto", "自動（依系統）"], ["zh", "中文"], ["en", "English"], ["ja", "日本語"], ["ko", "한국어"],
];
const PWS_TITLE: Record<string, string> = {
  zh: "緊急警報：交通疏散指示", en: "Emergency Alert: Traffic Evacuation",
  ja: "緊急速報：交通避難指示", ko: "긴급재난문자: 교통 대피 안내",
};

function resolveLang(setting: string): string {
  if (setting !== "auto") return setting;
  const nav = navigator.language.toLowerCase();
  if (nav.startsWith("ja")) return "ja";
  if (nav.startsWith("ko")) return "ko";
  if (nav.startsWith("en")) return "en";
  return "zh";
}

export function CitizenView() {
  const [langSetting, setLangSetting] = useState("auto");
  const [area, setArea] = useState("信義計畫區");
  const [delivered, setDelivered] = useState<any[]>([]);
  const [acked, setAcked] = useState<Set<string>>(new Set());
  const lang = resolveLang(langSetting);

  useEffect(() => {
    const poll = async () => {
      try {
        const all = await api.notifications();
        setDelivered(all.filter((n: any) =>
          n.target_area === area &&
          n.deliveries?.some((d: any) => d.channel === "Mobile_App" && d.status === "DELIVERY_CONFIRMED")
        ));
      } catch { /* ignore */ }
    };
    poll();
    const t = setInterval(poll, 2500);
    return () => clearInterval(t);
  }, [area]);

  const pickText = (n: any) =>
    n.messages?.[lang] ?? n.messages?.en ?? n.messages?.zh ?? n.cms ?? "";
  const active = delivered.find((n) => !acked.has(n.notification_id));

  return (
    <main className="citizen-view">
      <div className="panel citizen-controls">
        <h3>民眾端模擬設定</h3>
        <label>手機系統語言
          <select value={langSetting} onChange={(e) => setLangSetting(e.target.value)}>
            {PHONE_LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label>所在區域
          <select value={area} onChange={(e) => setArea(e.target.value)}>
            <option>信義計畫區</option>
            <option>大安區（範圍外）</option>
          </select>
        </label>
        <p className="dim small">
          警報依通報的目標區域推送——不在疏散範圍內的手機不會收到。
          App 推播可依裝置語言自動顯示對應語言（細胞廣播則為固定多語並列）；
          此模擬採裝置語言自動比對，亦可手動切換。
        </p>
        <p className="dim small">
          （指揮中心「核准 → 發布」通報後，此手機即收到警報）
        </p>
      </div>

      <div className="phone-frame">
        <div className="phone-notch" />
        <div className="phone-screen">
          <div className="phone-statusbar">
            <span>{new Date().toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false })}</span>
            <span>📶 5G 🔋</span>
          </div>
          {active ? (
            <div className="pws-alert">
              <div className="pws-header">⚠️ {PWS_TITLE[lang] ?? PWS_TITLE.zh}</div>
              <div className="pws-body">{pickText(active)}</div>
              <div className="pws-meta dim">{active.notification_id}｜{active.target_area}</div>
              <button className="pws-ack"
                onClick={() => setAcked((s) => new Set(s).add(active.notification_id))}>
                {lang === "en" ? "OK" : lang === "ja" ? "確認" : lang === "ko" ? "확인" : "我知道了"}
              </button>
            </div>
          ) : (
            <div className="phone-idle">
              <div className="phone-clock">
                {new Date().toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false })}
              </div>
              <div className="dim small">{area}｜{PHONE_LANGS.find(([v]) => v === langSetting)?.[1]}（顯示：{lang}）</div>
              {delivered.length === 0 && <div className="dim small">尚未收到警報</div>}
            </div>
          )}
          <div className="phone-inbox">
            {delivered.map((n) => (
              <div className="phone-inbox-item" key={n.notification_id}>
                <div className="small"><b>{PWS_TITLE[lang] ?? PWS_TITLE.zh}</b></div>
                <div className="small">{pickText(n)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}

// ---- 緊急彈窗（全域 message box） ----

function isEmergency(a: Alert): boolean {
  if (a.rule_id === 3 || a.rule_id === 4) return true;
  return a.rule_id === 1 && (a.evidence as any)?.congestion_level === "A";
}

export function EmergencyModal({ view }: { view: SimView | null }) {
  const seen = useRef<Set<string>>(new Set());
  const [queue, setQueue] = useState<Alert[]>([]);

  useEffect(() => {
    const alerts = view?.active_alerts ?? [];
    const fresh: Alert[] = [];
    for (const a of alerts) {
      if (!isEmergency(a)) continue;
      // 去重：同一實體＋同一規則只彈一次（B→A 升級因僅 A 級入列，天然只彈升級後）
      const key = `${a.rule_id}|${a.entity_id}`;
      if (!seen.current.has(key)) {
        seen.current.add(key);
        fresh.push(a);
      }
    }
    if (fresh.length) setQueue((q) => [...q, ...fresh]);
  }, [view?.active_alerts]);

  const current = queue[0];
  if (!current) return null;
  const ev = current.evidence as any;

  return (
    <div className="modal-backdrop">
      <div className="emergency-modal">
        <div className="em-title">🚨 緊急狀況警報</div>
        <div className="em-body">
          <RuleBadge id={current.rule_id} />
          <b className="em-entity">{current.entity_id}</b>
          <div className="mono small">{JSON.stringify(ev, null, 1)}</div>
          <ul>{current.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </div>
        <div className="em-footer">
          <span className="dim small">尚有 {queue.length - 1} 則待確認</span>
          <button className="primary" onClick={() => setQueue((q) => q.slice(1))}>確認接收</button>
        </div>
      </div>
    </div>
  );
}
