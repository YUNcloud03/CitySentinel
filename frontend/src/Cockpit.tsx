// 指揮中心「固定駕駛艙」（依 UI/UX 改版規格核心包）：
//   固定高度不捲動 · 一張常駐地圖 · 右側 Tab 情境抽屜（事件/決策/通知/證據）
//   底部時間條 + 抽屜入口（預警/決策鏈/What-if）· 分級告警（Alert Rail + 快報卡 + 限定 modal）
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type DecisionResult, type IncidentState, type Resource, type SimView } from "./api";
import MapView from "./MapView";
import DecisionSandbox from "./DecisionSandbox";
import {
  AlertFeed,
  CoordinatorSummaryCard,
  CustomEventForm,
  DecisionStages,
  EvidenceTab,
  IncidentDetail,
  NotificationLifecyclePanel,
  RuleBadge,
  WhatIfPanel,
} from "./components";

type DrawerTab = "event" | "decision" | "sandbox" | "notify" | "evidence";
type BottomPanel = "alerts" | "trace" | "whatif" | null;

interface Props {
  view: SimView | null;
  incident: IncidentState | null;
  available: any[];
  busy: boolean;
  resourceKey: number;
  onInject: (id: string) => void;
  onInjectedCustom: (state: IncidentState) => void;
  onRefresh: () => void;
  onSeekIndex: (timestamp: string) => void;
}

// ---- 城市狀態列（僅可決策摘要，非原始表） ----
function CityStatusBar({ view, incident, resources, pendingNotis }: {
  view: SimView | null; incident: IncidentState | null;
  resources: Resource[]; pendingNotis: number;
}) {
  const rows = Object.values(view?.traffic ?? {});
  const nA = rows.filter((r) => r.congestion_level === "A").length;
  const nB = rows.filter((r) => r.congestion_level === "B").length;
  const alert = nA > 0 ? { t: "紅色警戒", c: "red" } : nB > 0 ? { t: "黃色警戒", c: "amber" } : { t: "正常", c: "green" };
  const police = resources.filter((r) => r.resource_type === "Police");
  const polAvail = police.reduce((s, r) => s + r.available_count, 0);
  const polTotal = police.reduce((s, r) => s + r.total_count, 0);
  const ete = incident?.ete_result;
  return (
    <div className="status-bar">
      <div className={`sb-item sb-${alert.c}`}>
        <span className="sb-k">城市警戒</span><b>{alert.t}</b>
      </div>
      <div className="sb-item"><span className="sb-k">異常路段</span>
        <b>{nA + nB > 0 ? `${nA + nB} 需處置` : "—"}</b></div>
      <div className="sb-item"><span className="sb-k">進行中事件</span>
        <b>{incident ? incident.incident_id.slice(-7) : "無"}</b></div>
      <div className="sb-item"><span className="sb-k">預計恢復</span>
        <b>{ete ? `${ete.ete_minutes_display} 分` : "—"}</b></div>
      <div className="sb-item"><span className="sb-k">交通警力</span>
        <b className={polAvail === 0 ? "warn" : ""}>{polAvail}/{polTotal}</b></div>
      <div className="sb-item"><span className="sb-k">通知</span>
        <b>{pendingNotis > 0 ? `待核准 ${pendingNotis}` : "—"}</b></div>
    </div>
  );
}

// ---- Alert Rail（告警摘要列，不阻塞） ----
function AlertRail({ view, onOpen }: { view: SimView | null; onOpen: () => void }) {
  const alerts = view?.active_alerts ?? [];
  if (!alerts.length) return null;
  const high = alerts.filter((a) => a.rule_id === 2 || a.rule_id === 3 || a.rule_id === 4
    || (a.rule_id === 1 && (a.evidence as any)?.congestion_level === "A")).length;
  const warn = alerts.filter((a) => a.rule_id === 1 && (a.evidence as any)?.congestion_level === "B").length;
  const info = alerts.length - high - warn;
  return (
    <button className="alert-rail" onClick={onOpen} title="點擊查看預警詳情">
      {high > 0 && <span className="ar red">🔴 高風險 {high}</span>}
      {warn > 0 && <span className="ar amber">🟡 注意 {warn}</span>}
      {info > 0 && <span className="ar blue">🔵 資訊 {info}</span>}
    </button>
  );
}

// ---- 事件快報卡（右側滑出，需處置事件） ----
function EventReportCard({ incident, onView, onMute }: {
  incident: IncidentState; onView: () => void; onMute: () => void;
}) {
  const conf = incident.confidence;
  const routing = incident.routing_result;
  const impacted = (routing?.secondary_routes?.length ?? 0) + (routing?.primary_route ? 1 : 0);
  return (
    <div className="report-card">
      <div className="rc-head">🔴 高風險事件｜等待指揮官確認</div>
      <div className="rc-title">{incident.event.location}</div>
      <div className="rc-meta">
        影響：{impacted} 路段｜預估延誤 {incident.ete_result?.ete_minutes_display ?? "—"} 分
        ｜可信度 {conf ? `${Math.round(conf.confidence_score * 100)}%` : "—"}
      </div>
      <div className="rc-actions">
        <button className="primary" onClick={onView}>查看決策</button>
        <button onClick={onMute}>暫時靜音</button>
      </div>
    </div>
  );
}

// ---- 時間條（精簡回放：拖曳 seek 車流/地圖快照） ----
function TimeBar({ view, onSeekIndex }: { view: SimView | null; onSeekIndex: (ts: string) => void }) {
  const [timeline, setTimeline] = useState<{ timestamps: string[]; markers: any[] }>({ timestamps: [], markers: [] });
  useEffect(() => { api.timeline().then(setTimeline).catch(() => {}); }, []);
  const total = timeline.timestamps.length;
  const idx = view?.progress?.index ?? 0;
  return (
    <div className="time-bar">
      <div className="tb-track">
        <input type="range" min={0} max={Math.max(0, total - 1)} value={idx}
          onChange={(e) => { const ts = timeline.timestamps[Number(e.target.value)]; if (ts) onSeekIndex(ts); }} />
        <div className="tb-markers">
          {timeline.markers.filter((m) => m.kind).map((m) => (
            <span key={m.index}
              className={`tb-marker ${m.kind}`}
              style={{ left: `${(m.index / Math.max(1, total - 1)) * 100}%` }}
              title={`${m.time}｜${m.kind === "incident" ? "事件" : "A 級壅塞"}`}
              onClick={() => onSeekIndex(m.time)} />
          ))}
        </div>
      </div>
      <div className="tb-readout dim">
        Step {idx + 1}/{total || "—"}｜{view?.sim_time ?? "--:--"}
      </div>
    </div>
  );
}

// ---- 事件佇列（需決策 / 已處置） ----
function EventQueue({ available, incident, onInject, busy }: {
  available: any[]; incident: IncidentState | null; onInject: (id: string) => void; busy: boolean;
}) {
  return (
    <div className="event-queue">
      <div className="eq-label">待注入事件</div>
      {available.map((ev) => {
        const active = incident?.incident_id === ev.event_id;
        return (
          <button key={ev.event_id} className={`eq-card ${active ? "active" : ""}`}
            disabled={busy} onClick={() => onInject(ev.event_id)} title={ev.description}>
            <div className="eq-row">
              <b>{ev.event_id.slice(-7)}</b>
              <span className={`chip ${ev.severity === "Critical" ? "red" : ev.severity === "High" ? "amber" : "green"}`}>
                {ev.severity}
              </span>
            </div>
            <div className="dim small">{ev.location}</div>
          </button>
        );
      })}
    </div>
  );
}

export default function Cockpit(p: Props) {
  const [tab, setTab] = useState<DrawerTab>("event");
  const [bottom, setBottom] = useState<BottomPanel>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [notis, setNotis] = useState<any[]>([]);
  const [muted, setMuted] = useState<string | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);
  const [preview, setPreview] = useState<DecisionResult | null>(null);
  const prevIncidentRef = useRef<string | null>(null);

  useEffect(() => {
    api.resources().then(setResources).catch(() => {});
    api.notifications().then(setNotis).catch(() => {});
  }, [p.resourceKey]);

  // 新事件建立 → 自動切到「決策」Tab、顯示快報卡（非阻塞）
  useEffect(() => {
    const id = p.incident?.incident_id ?? null;
    if (id && id !== prevIncidentRef.current) {
      setTab("decision");
      setMuted(null);
    }
    prevIncidentRef.current = id;
  }, [p.incident?.incident_id]);

  const pendingNotis = notis.filter((n) => n.status === "READY_FOR_APPROVAL").length;
  // 限定 modal：資源缺口（無可用資源）——真正需人工決策才阻塞
  const shortfall = p.incident?.dispatch?.has_shortfall
    ? p.incident.dispatch.gaps?.[0] : null;

  const showReport = p.incident && muted !== p.incident.incident_id
    && p.incident.event.severity && ["Critical", "High"].includes(p.incident.event.severity);

  const alertCount = p.view?.active_alerts?.length ?? 0;
  const traceCount = p.incident?.decision_trace?.length ?? 0;

  return (
    <div className="cockpit">
      <CityStatusBar view={p.view} incident={p.incident} resources={resources} pendingNotis={pendingNotis} />

      <div className="cockpit-body">
        <div className="map-region">
          <MapView view={p.view} incident={p.incident}
            selectedSegmentId={selectedSegment}
            projectedTraffic={preview?.projected_traffic}
            onSelectSegment={(segmentId) => {
              setSelectedSegment(segmentId);
              setPreview(null);
              setTab("sandbox");
            }} />
          <AlertRail view={p.view} onOpen={() => setBottom("alerts")} />
          {showReport && p.incident && (
            <EventReportCard incident={p.incident}
              onView={() => setTab("decision")}
              onMute={() => setMuted(p.incident!.incident_id)} />
          )}
        </div>

        <aside className="right-drawer">
          <div className="rd-tabs">
            {([["event", "事件"], ["decision", "建議"], ["sandbox", "推演"], ["notify", "通知"], ["evidence", "證據"]] as [DrawerTab, string][])
              .map(([id, label]) => (
                <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
                  {label}
                  {id === "notify" && pendingNotis > 0 && <span className="tab-dot" />}
                  {id === "decision" && p.incident && <span className="tab-dot blue" />}
                </button>
              ))}
          </div>
          <div className="rd-body">
            {tab === "event" && (
              <>
                {p.incident && <CoordinatorSummaryCard incident={p.incident} />}
                <EventQueue available={p.available} incident={p.incident} onInject={p.onInject} busy={p.busy} />
                <CustomEventForm onInjected={p.onInjectedCustom} />
              </>
            )}
            {tab === "decision" && (
              p.incident
                ? <IncidentDetail incident={p.incident} onRefresh={p.onRefresh} />
                : <p className="dim">從「事件」Tab 注入事件後，此處顯示 Coordinator 建議、疏散方案與資源調度。</p>
            )}
            {tab === "sandbox" && <DecisionSandbox selectedSegmentId={selectedSegment} view={p.view} onPreview={setPreview} />}
            {tab === "notify" && <NotificationLifecyclePanel refreshKey={p.resourceKey} />}
            {tab === "evidence" && <EvidenceTab incident={p.incident} />}
          </div>
        </aside>
      </div>

      <div className="cockpit-foot">
        <TimeBar view={p.view} onSeekIndex={p.onSeekIndex} />
        <div className="foot-entries">
          <button className={bottom === "alerts" ? "active" : ""} onClick={() => setBottom(bottom === "alerts" ? null : "alerts")}>
            預警 {alertCount}
          </button>
          <button className={bottom === "trace" ? "active" : ""} onClick={() => setBottom(bottom === "trace" ? null : "trace")}>
            決策鏈 {traceCount ? `${traceCount} 步` : ""}
          </button>
          <button className={bottom === "whatif" ? "active" : ""} onClick={() => setBottom(bottom === "whatif" ? null : "whatif")}>
            What-if
          </button>
        </div>
      </div>

      {bottom && (
        <div className="bottom-panel">
          <div className="bp-head">
            <b>{bottom === "alerts" ? "自動預警" : bottom === "trace" ? "決策依據與執行進度" : "What-if 策略諮詢"}</b>
            <button onClick={() => setBottom(null)}>✕ 收合</button>
          </div>
          <div className="bp-body">
            {bottom === "alerts" && <AlertFeed alerts={p.view?.active_alerts ?? []} />}
            {bottom === "trace" && <DecisionStages incident={p.incident} />}
            {bottom === "whatif" && <WhatIfPanel />}
          </div>
        </div>
      )}

      {shortfall && (
        <div className="modal-backdrop">
          <div className="emergency-modal">
            <div className="em-title">🚨 資源不足，需人工決策</div>
            <div className="em-body">
              <p>{p.incident!.incident_id}：{(shortfall as any).resource_type} 尚缺 {(shortfall as any).gap} 單位。</p>
              <p className="dim small">系統已於「決策」Tab 提出抽調建議，或請跨區支援。維持局部疏導並持續監測。</p>
            </div>
            <div className="em-footer">
              <button className="primary" onClick={() => setTab("decision")}>前往決策抽屜</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
