import { useEffect, useRef, useState } from "react";
import { api, type Alert, type CrowdRow, type IncidentState, type Resource, type SimView, type TrafficRow } from "./api";

/** 數字平滑計數（ease-out cubic）。 */
export function useCountUp(target: number, duration = 600): number {
  const [val, setVal] = useState(target);
  const prevRef = useRef(target);
  useEffect(() => {
    const from = prevRef.current;
    prevRef.current = target;
    if (from === target) return;
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      setVal(Math.round(from + (target - from) * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return val;
}

const RES_TYPE_LABEL: Record<string, string> = {
  Police: "交通警力",
  Shuttle: "接駁車",
  SignalMaintenance: "號誌維修",
  SignalControl: "號誌控制",
  MRTLiaison: "北捷聯絡",
};

const RULE_NAMES: Record<number, string> = {
  1: "壅塞分級",
  2: "車禍路障",
  3: "人潮分流",
  4: "大巨蛋散場",
  5: "號誌故障",
  6: "多語通報",
  7: "ETE 計算",
};

export function RuleBadge({ id }: { id: number }) {
  return (
    <span className={`badge rule-${id}`}>
      SOP {id}｜{RULE_NAMES[id] ?? ""}
    </span>
  );
}

function LevelChip({ level }: { level: string }) {
  const cls = level === "A" ? "chip red" : level === "B" ? "chip amber" : "chip green";
  const label = level === "A" ? "A 級" : level === "B" ? "B 級" : "正常";
  return <span className={cls}>{label}</span>;
}

// ---- 城市狀態卡 ----

export function StatusCards({
  view,
  incident,
}: {
  view: SimView | null;
  incident: IncidentState | null;
}) {
  const traffic = view?.traffic ?? {};
  const rows = Object.values(traffic);
  const nA = useCountUp(rows.filter((r) => r.congestion_level === "A").length);
  const nB = useCountUp(rows.filter((r) => r.congestion_level === "B").length);
  const alertLevel = nA > 0 ? "紅色警戒" : nB > 0 ? "黃色警戒" : "正常";
  const alertCls = nA > 0 ? "red" : nB > 0 ? "amber" : "green";
  const ete = incident?.ete_result;
  const eteVal = useCountUp(ete?.ete_minutes_display ?? 0);
  const multi = incident?.notifications?.multilingual_required;

  return (
    <div className="cards">
      <div className={`card ${alertCls}`}>
        <div className="card-label">城市警戒</div>
        <div className="card-value">{alertLevel}</div>
        <div className="card-sub">A級 {nA}｜B級 {nB}</div>
      </div>
      <div className="card">
        <div className="card-label">進行中事件</div>
        <div className="card-value">{incident ? incident.incident_id : "—"}</div>
        <div className="card-sub">{incident ? incident.event.type : "無"}</div>
      </div>
      <div className="card">
        <div className="card-label">預計恢復 ETE</div>
        <div className="card-value">{ete ? `${eteVal} 分` : "—"}</div>
        <div className="card-sub">{ete ? `基準${ete.base_clearance_minutes}+壅塞${ete.congestion_penalty_minutes.toFixed(1)}` : ""}</div>
      </div>
      <div className="card">
        <div className="card-label">觸發 SOP</div>
        <div className="card-value">{incident?.triggered_rules.join("、") || "—"}</div>
        <div className="card-sub">{incident ? `狀態 ${incident.workflow_status}` : ""}</div>
      </div>
      <div className={`card ${multi ? "purple" : ""}`}>
        <div className="card-label">多語通報</div>
        <div className="card-value">{multi ? "已啟動" : "未觸發"}</div>
        <div className="card-sub">{multi ? "中英日韓同步" : "漫遊率 < 30%"}</div>
      </div>
    </div>
  );
}

// ---- 車流／人流清單 ----

export function TrafficPanel({ traffic }: { traffic: Record<string, TrafficRow> }) {
  const rows = Object.entries(traffic).sort(
    (a, b) => b[1].saturation_score - a[1].saturation_score
  );
  return (
    <div className="panel">
      <h3>車流監測</h3>
      <table>
        <thead>
          <tr><th>路段</th><th>速度</th><th>飽和度</th><th>等級</th></tr>
        </thead>
        <tbody>
          {rows.map(([id, r]) => (
            <tr key={id}>
              <td title={id}>{r.road_name}</td>
              <td>{r.avg_speed}</td>
              <td>{r.saturation_score.toFixed(2)}</td>
              <td><LevelChip level={r.congestion_level} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CrowdPanel({ crowd }: { crowd: Record<string, CrowdRow> }) {
  const rows = Object.entries(crowd).sort((a, b) => b[1].user_count - a[1].user_count);
  return (
    <div className="panel">
      <h3>人流監測</h3>
      <table>
        <thead>
          <tr><th>場站</th><th>人數</th><th>成長率</th><th>漫遊</th></tr>
        </thead>
        <tbody>
          {rows.map(([id, r]) => (
            <tr key={id}>
              <td title={id}>{r.location_name}</td>
              <td>{r.user_count.toLocaleString()}</td>
              <td className={r.growth_rate > 0.3 ? "warn" : ""}>{r.growth_rate.toFixed(2)}</td>
              <td className={r.roaming_user_pct >= 30 ? "purple-text" : ""}>{r.roaming_user_pct}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- 預警清單 ----

function alertEntityName(alert: Alert, view?: SimView | null) {
  return view?.traffic?.[alert.entity_id]?.road_name
    ?? view?.crowd?.[alert.entity_id]?.location_name
    ?? alert.entity_id;
}

function alertEvidenceText(evidence: Record<string, unknown>) {
  const labels: Record<string, string> = {
    saturation_score: "飽和度", congestion_level: "分級", user_count: "人數",
    growth_rate: "增幅", roaming_user_pct: "漫遊率", historical_peak: "歷史峰值",
  };
  return Object.entries(evidence)
    .filter(([key, value]) => labels[key] && ["string", "number"].includes(typeof value))
    .slice(0, 3)
    .map(([key, value]) => `${labels[key]} ${typeof value === "number" && key === "growth_rate" ? `${Math.round(value * 100)}%` : value}`)
    .join("｜");
}

export function AlertFeed({ alerts, view, onLocate, onEvidence }: {
  alerts: Alert[];
  view?: SimView | null;
  onLocate?: (alert: Alert) => void;
  onEvidence?: (alert: Alert) => void;
}) {
  // 未讀狀態：新預警帶低頻呼吸光，hover 即標記已讀（不閃爍干擾閱讀）
  const readRef = useRef<Set<string>>(new Set());
  const [, force] = useState(0);
  if (!alerts.length) return null;
  const keyOf = (a: Alert) => `${a.rule_id}|${a.entity_id}`;
  return (
    <div className="panel alert-feed">
      <h3>自動預警</h3>
      {alerts.map((a, i) => {
        const k = keyOf(a);
        const unread = !readRef.current.has(k);
        return (
          <div
            className={`alert-item ${unread ? "unread" : ""}`}
            key={k}
            style={{ animationDelay: `${i * 60}ms` }}
            onMouseEnter={() => {
              if (unread) { readRef.current.add(k); force((n) => n + 1); }
            }}
          >
            <RuleBadge id={a.rule_id} />
            <span className="alert-entity">{alertEntityName(a, view)}</span>
            <div className="alert-evidence-summary">{alertEvidenceText(a.evidence) || "已達規則門檻"}</div>
            <div className="alert-actions">{a.actions.join("；")}</div>
            {(onLocate || onEvidence) && <div className="alert-command-actions">
              {onLocate && <button type="button" onClick={() => onLocate(a)}>定位／推演</button>}
              {onEvidence && <button type="button" onClick={() => onEvidence(a)}>查看決策依據</button>}
            </div>}
          </div>
        );
      })}
    </div>
  );
}

// ---- 資源庫存面板 ----

export function ResourcePanel({ refreshKey }: { refreshKey: number }) {
  const [resources, setResources] = useState<Resource[]>([]);

  useEffect(() => {
    api.resources().then(setResources).catch(() => {});
  }, [refreshKey]);

  const reset = async () => {
    await api.resetResources();
    setResources(await api.resources());
  };

  return (
    <div className="panel">
      <h3>
        資源庫存
        <button className="mini" onClick={reset}>重置</button>
      </h3>
      <table>
        <thead>
          <tr><th>資源</th><th>可用/總量</th><th>ETA</th><th>狀態</th></tr>
        </thead>
        <tbody>
          {resources.map((r) => {
            const ratio = r.available_count / r.total_count;
            const cls = ratio === 0 ? "red" : ratio < 0.5 ? "amber" : "green";
            return (
              <tr key={r.resource_id}>
                <td title={r.current_location}>{r.label}</td>
                <td>
                  <span className={`chip ${cls}`}>{r.available_count}/{r.total_count}</span>
                </td>
                <td>{r.eta_minutes} 分</td>
                <td className="dim">{RES_TYPE_LABEL[r.resource_type] ?? r.resource_type}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---- 事件中心 ----

export function IncidentPanel({
  available,
  incident,
  onInject,
  onRefresh,
  busy,
}: {
  available: any[];
  incident: IncidentState | null;
  onInject: (id: string) => void;
  onRefresh: () => void;
  busy: boolean;
}) {
  return (
    <div className="panel">
      <h3>事件注入</h3>
      <div className="inject-buttons">
        {available.map((ev) => (
          <button
            key={ev.event_id}
            disabled={busy}
            onClick={() => onInject(ev.event_id)}
            title={ev.description}
          >
            {ev.event_id.slice(-7)}｜{ev.location}
          </button>
        ))}
      </div>
      {incident && <IncidentDetail incident={incident} onRefresh={onRefresh} />}
    </div>
  );
}

// ---- 調度動作卡（可 Challenge） ----

function DispatchSection({
  incident,
  onRefresh,
  onDecisionAccepted,
}: {
  incident: IncidentState;
  onRefresh: () => void;
  onDecisionAccepted?: () => Promise<void> | void;
}) {
  const dispatch = incident.dispatch;
  const [busyId, setBusyId] = useState<string | null>(null);
  if (!dispatch || !dispatch.actions?.length) return null;

  const act = async (
    actionId: string,
    op: "accept" | "reject" | "adjust" | "preempt",
    extra: {
      count?: number; reason?: string;
      source_incident_id?: string; source_action_id?: string;
    } = {}
  ) => {
    setBusyId(actionId);
    try {
      await api.dispatchAction(incident.incident_id, actionId, op, {
        ...extra,
        operator: "traffic_commander_01",
      });
      onRefresh();
      if (["accept", "adjust", "preempt"].includes(op)) await onDecisionAccepted?.();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <h4>
        資源調度與人工指揮
        {dispatch.has_shortfall && <span className="chip red">資源缺口</span>}
      </h4>
      {dispatch.actions.map((a: any) => (
        <div className={`dispatch-action status-${a.status}`} key={a.action_id}>
          <div className="da-head">
            <RuleBadge id={a.rule_id} />
            <span className="da-title">{a.action}</span>
            <span className={`da-status ${a.status}`}>{statusLabel(a.status)}</span>
          </div>
          <div className="da-detail">{a.deterministic_result}</div>
          <div className="da-assign">
            {a.allocation_state === "committed" ? "正式派遣：" : "預留資源："}
            {a.assignments.length
              ? a.assignments.map((x: any) => `${x.label} ×${x.count}（ETA ${x.eta_minutes}分）`).join("、")
              : "—"}
            {a.gap > 0 && <span className="warn"> 缺 {a.gap} 單位</span>}
          </div>
          {a.escalation && <div className="da-escalation">⚠ {a.escalation}</div>}
          {a.gap > 0 && a.preemption_candidates?.length > 0 && (
            <div className="da-preempt">
              {a.preemption_candidates.map((c: any) => (
                <button
                  key={c.source_action_id}
                  disabled={busyId === a.action_id}
                  onClick={() => act(a.action_id, "preempt", {
                    count: c.suggested_count,
                    source_incident_id: c.source_incident_id,
                    source_action_id: c.source_action_id,
                    reason: `高優先事件抽調（來源 ${c.source_severity}）`,
                  })}
                >
                  ⚡ 核准抽調 {c.suggested_count} 單位（自 {c.source_incident_id}／{c.source_severity}）
                </button>
              ))}
            </div>
          )}
          {a.agent_recommended_count && a.agent_recommended_count !== a.requested_count && (
            <div className="dim">（Agent 原建議 {a.agent_recommended_count} 單位，已人工調整為 {a.requested_count}）</div>
          )}
          <details className="da-challenge">
            <summary>Challenge：查看證據</summary>
            <div className="mono small">
              action_id: {a.action_id}{"\n"}
              rule_id: {a.rule_id}｜source: {a.source}{"\n"}
              input_snapshot: {a.input_snapshot_id}{"\n"}
              challenge: {a.challenge_question}
            </div>
          </details>
          {a.override && (
            <div className="da-override">
              人工覆寫：{a.override.override_by}｜{a.override.op}｜{a.override.override_reason || "（未填理由）"}｜{a.override.override_at}
            </div>
          )}
          {(a.status === "proposed" || a.status === "shortfall") && (
            <div className="da-actions">
              <button disabled={busyId === a.action_id} onClick={() => act(a.action_id, "accept")}>接受</button>
              <button disabled={busyId === a.action_id} onClick={() => {
                const c = prompt(`調整 ${a.action} 的派遣數量：`, String(a.requested_count));
                if (c && !Number.isNaN(Number(c))) act(a.action_id, "adjust", { count: Number(c), reason: "現場人工調整" });
              }}>調整</button>
              <button disabled={busyId === a.action_id} onClick={() => {
                const r = prompt("拒絕理由：", "現場已有資源");
                if (r !== null) act(a.action_id, "reject", { reason: r });
              }}>拒絕</button>
            </div>
          )}
          {(a.status === "accepted" || a.status === "adjusted") && (
            <div className="dispatch-execution-note">
              ✓ 決策已核准，系統已自動播放；資源抵達前維持障礙，抵達後才逐步疏通
              {a.accepted_sim_time ? `｜啟動 ${a.accepted_sim_time}` : ""}
            </div>
          )}
        </div>
      ))}
    </>
  );
}

function statusLabel(s: string): string {
  return { proposed: "待核准", accepted: "已接受", adjusted: "已調整", rejected: "已拒絕", shortfall: "資源不足" }[s] ?? s;
}

// ---- Coordinator 一句話決策摘要（駕駛艙頭條） ----

export function CoordinatorSummaryCard({ incident }: { incident: IncidentState }) {
  const s = incident.coordinator_summary;
  if (!s) return null;
  return (
    <div className="coord-summary">
      <div className="cs-head">🎯 Coordinator 判定</div>
      <div className="cs-verdict">{s.verdict}</div>
      <div className="cs-row"><span className="cs-label">影響</span>
        <span>{s.impact ?? "尚待評估"}</span></div>
      <div className="cs-row"><span className="cs-label">建議</span>
        <span>{s.recommendation ?? s.actions.join("、")}</span></div>
      <div className="cs-row"><span className="cs-label">代價</span>
        <span>{s.tradeoffs ?? "尚待評估"}</span></div>
      <div className="cs-row"><span className="cs-label">改善</span>
        <span>{s.expected_improvement ?? "尚未模擬"}</span></div>
      <div className="cs-row"><span className="cs-label">升級條件</span>
        <span>{s.escalation}</span></div>
      <div className="cs-row"><span className="cs-label">依據</span>
        <span className="dim">{s.basis}</span></div>
    </div>
  );
}

// ---- 五階段決策鏈（決策依據與執行進度） ----

const STAGES: { name: string; steps: string[]; hint: (t: any[]) => string }[] = [
  { name: "事件驗證", steps: ["NEW", "VALIDATED", "CONFIDENCE_ASSESSED"],
    hint: (t) => { const c = t.find((x) => x.step === "CONFIDENCE_ASSESSED"); return c ? `可信度 ${Math.round((c.detail.score ?? 0) * 100)}%` : "來源驗證"; } },
  { name: "影響評估", steps: ["RULE_EVALUATED", "ETE_CALCULATED"],
    hint: (t) => { const e = t.find((x) => x.step === "ETE_CALCULATED"); return e?.detail?.ete_minutes ? `ETE ${Math.round(e.detail.ete_minutes)} 分` : "規則判定"; } },
  { name: "方案規劃", steps: ["ROUTE_PLANNED", "SOP_RETRIEVED"],
    hint: (t) => { const r = t.find((x) => x.step === "ROUTE_PLANNED"); return r?.detail?.primary ? `主疏散 ${r.detail.primary}` : "SOP 檢索"; } },
  { name: "資源與核准", steps: ["DISPATCH_PLANNED", "HUMAN_OVERRIDE", "DISPATCH_PREEMPTED", "RESOURCE_REBALANCED"],
    hint: (t) => { const d = t.find((x) => x.step === "DISPATCH_PLANNED"); return d?.detail?.has_shortfall ? "資源缺口待升級" : d?.detail?.actions != null ? `派遣 ${d.detail.actions} 項` : "資源檢查"; } },
  { name: "通知與追蹤", steps: ["CONTENT_GENERATED", "PUBLISHED", "COMPLETED"],
    hint: (t) => { const p = t.find((x) => x.step === "PUBLISHED"); return p?.detail?.notification_status ? "通報待核准" : "內容生成"; } },
];

const TRACE_DETAIL_LABELS: Record<string, string> = {
  score: "可信度", level: "等級", actions: "建議動作數", primary: "主疏導路段",
  has_shortfall: "資源缺口", notification_status: "通知狀態", ete_minutes: "預估處理時間",
  caused_by_incident: "事件觸發規則", context_rules: "環境規則", rule_ids: "引用規則",
  execution_policy: "執行政策", simulation_time: "模擬時間", op: "人工操作",
  override_by: "操作人員", override_reason: "調整原因", adjusted_to: "調整數量",
};

function traceDetailRows(detail: Record<string, any>) {
  return Object.entries(detail)
    .filter(([key, value]) => TRACE_DETAIL_LABELS[key] && value != null)
    .map(([key, value]) => ({
      label: TRACE_DETAIL_LABELS[key],
      value: typeof value === "object" ? JSON.stringify(value) : String(value),
    }));
}

export function DecisionStages({ incident, onGoDecision, onGoEvidence, onGoNotify }: {
  incident: IncidentState | null;
  onGoDecision?: () => void;
  onGoEvidence?: () => void;
  onGoNotify?: () => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => setOpen(null), [incident?.incident_id]);
  if (!incident) return <p className="dim">注入事件後顯示決策依據與執行進度。</p>;

  const trace = incident.decision_trace;
  const done = new Set(trace.map((t) => t.step));
  const failed = incident.workflow_status === "failed";
  const pendingActions = incident.dispatch?.actions.filter((action: any) => ["proposed", "shortfall"].includes(action.status)).length ?? 0;
  const nextAction = failed
    ? { label: "流程失敗，查看證據", action: onGoEvidence }
    : pendingActions > 0
      ? { label: `${pendingActions} 項處置待核准`, action: onGoDecision }
      : { label: "檢查並核准通知", action: onGoNotify };

  return (
    <div className="stages">
      <div className={`decision-next-action ${failed ? "failed" : ""}`}>
        <span>指揮官下一步</span><b>{nextAction.label}</b>
        {nextAction.action && <button type="button" onClick={nextAction.action}>立即處理</button>}
      </div>
      <div className="stage-rail">
        {STAGES.map((st, i) => {
          const hit = st.steps.some((s) => done.has(s));
          return (
            <div key={i} className={`stage ${hit ? "done" : "pending"} ${open === i ? "sel" : ""}`}
              onClick={() => setOpen(open === i ? null : i)}>
              <div className="stage-dot">{hit ? "●" : "○"}</div>
              <div className="stage-name">{i + 1}. {st.name}</div>
              <div className="stage-hint dim">{hit ? st.hint(trace) : "待處理"}</div>
            </div>
          );
        })}
      </div>
      {open != null && (
        <div className="stage-detail">
          <div className="td-step">{STAGES[open].name}</div>
          {trace.filter((t) => STAGES[open].steps.includes(t.step)).map((t, i) => (
            <div key={i} className="stage-step">
              <b>{t.step}</b> <span className="dim">{t.at.slice(11, 19)}</span>
              {traceDetailRows(t.detail).length > 0
                ? <dl>{traceDetailRows(t.detail).map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
                : <p className="dim small">此步驟已完成，沒有額外的指揮官輸入。</p>}
            </div>
          ))}
          <div className="stage-detail-actions">
            {open <= 1 && onGoEvidence && <button type="button" onClick={onGoEvidence}>查看完整證據</button>}
            {(open === 2 || open === 3) && onGoDecision && <button type="button" className="primary" onClick={onGoDecision}>前往核准／調整</button>}
            {open === 4 && onGoNotify && <button type="button" className="primary" onClick={onGoNotify}>前往通知核准</button>}
          </div>
          {failed && <div className="warn">流程未完成，以上為已完成階段。</div>}
        </div>
      )}
    </div>
  );
}

// ---- 證據 Tab（可信度 + 觸發證據） ----

export function EvidenceTab({ incident }: { incident: IncidentState | null }) {
  if (!incident) return <p className="dim">注入事件後顯示可信度與資料佐證。</p>;
  const conf = incident.confidence;
  return (
    <div>
      {conf && (
        <div className="conf-card">
          <div className="conf-head">
            <b>事件可信度</b>
            <span className={`conf-score lv-${conf.level}`}>
              {Math.round(conf.confidence_score * 100)}%｜{conf.level}
            </span>
          </div>
          <ul className="conf-evidence">
            {conf.evidence.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}
      {incident.trigger_details && incident.trigger_details.length > 0 && (
        <>
          <h4>觸發證據</h4>
          {incident.trigger_details.map((t, i) => (
            <div className="evidence" key={i}>
              <RuleBadge id={t.rule_id} /> <b>{t.entity_id}</b>
              <div className="mono small">{JSON.stringify(t.evidence, null, 1)}</div>
            </div>
          ))}
        </>
      )}
      {incident.sop_evidence.length > 0 && (
        <details>
          <summary>SOP 依據原文（{incident.sop_evidence.map((s) => s.rule_id).join("、")}）</summary>
          {incident.sop_evidence.map((s) => (
            <div className="sop-text" key={s.rule_id}>
              <b>第 {s.rule_id} 條 {s.title}</b>
              <pre>{s.text}</pre>
            </div>
          ))}
        </details>
      )}
      <p className="dim small">完整資料佐證（SHA256、引擎門檻）見「紀錄與驗證」頁。</p>
    </div>
  );
}

export function IncidentDetail({ incident, onRefresh, onDecisionAccepted }: {
  incident: IncidentState;
  onRefresh: () => void;
  onDecisionAccepted?: () => Promise<void> | void;
}) {
  const routing = incident.routing_result;
  const ete = incident.ete_result;
  const noti = incident.notifications;
  const attr = incident.rule_attribution;
  const [resolving, setResolving] = useState(false);
  const resolveIncident = async () => {
    const reason = prompt("請輸入現場確認事件已排除的依據：", "現場人員確認障礙排除，道路恢復通行");
    if (!reason) return;
    setResolving(true);
    try {
      await api.resolveIncident(incident.incident_id, reason);
      onRefresh();
    } finally {
      setResolving(false);
    }
  };
  return (
    <div className="incident-detail">
      <div className={`operational-state state-${String(incident.operational_status ?? "IMPACT_ACTIVE").toLowerCase()}`}>
        <div><small>事件作業狀態</small><b>{incident.operational_status === "RESOLVED" ? "已確認排除"
          : incident.operational_status === "RESPONSE_AUTHORIZED" ? "處置已核准"
          : "障礙影響中"}</b></div>
        {incident.operational_status !== "RESOLVED" && (
          <button type="button" disabled={resolving} onClick={resolveIncident}>
            {resolving ? "結案中…" : "現場確認排除"}
          </button>
        )}
      </div>
      {incident.closed_loop && <ClosedLoopCoordinatorCard loop={incident.closed_loop} />}
      {attr ? (
        <div className="attribution">
          <div><span className="attr-label caused">事件觸發</span>
            {attr.caused_by_incident.length ? attr.caused_by_incident.map((r) => <RuleBadge key={r} id={r} />) : <span className="dim">無</span>}</div>
          {attr.calculation_rules.length > 0 && (
            <div><span className="attr-label calc">計算條款</span>
              {attr.calculation_rules.map((r) => <RuleBadge key={r} id={r} />)}</div>
          )}
          {attr.context_rules.length > 0 && (
            <div><span className="attr-label context">情境參考</span>
              {attr.context_rules.map((r) => <RuleBadge key={r} id={r} />)}
              <span className="dim">（同時段環境監測，非本事件造成）</span></div>
          )}
        </div>
      ) : (
        <div className="row">{incident.triggered_rules.map((r) => <RuleBadge key={r} id={r} />)}</div>
      )}
      <p className="desc">{incident.event.description}</p>

      {routing && (
        <>
          <h4>疏散策略</h4>
          {routing.primary_route && (
            <div className="route primary">
              主疏散：<b>{routing.primary_route.name}</b>
              （容量 {routing.primary_route.capacity_vph}｜飽和 {routing.primary_route.saturation_score?.toFixed(2) ?? "—"}）
              {routing.primary_route.congested && <div className="warn">{routing.primary_route.advisory}</div>}
            </div>
          )}
          {routing.secondary_routes.map((s: any) => (
            <div className="route secondary" key={s.segment_id}>
              次要：{s.name}（{s.role_reason === "DOWNSTREAM" ? "位於下游" : "上游備援"}）
            </div>
          ))}
          {routing.excluded_routes.length > 0 && (
            <details>
              <summary>排除路段（{routing.excluded_routes.length}）</summary>
              {routing.excluded_routes.map((e: any) => (
                <div className="excluded" key={e.segment_id}>
                  ✕ {e.name ?? e.segment_id}：{e.detail}
                </div>
              ))}
            </details>
          )}
        </>
      )}

      {ete && (
        <>
          <h4>ETE 計算</h4>
          <div className="mono">{ete.formula}</div>
          {ete.saturation_source_segments && (
            <div className="dim small">飽和度來源：{ete.saturation_source_segments.join("、")}</div>
          )}
        </>
      )}

      <DispatchSection incident={incident} onRefresh={onRefresh} onDecisionAccepted={onDecisionAccepted} />

      <AISummarySection incident={incident} />

      {incident.trigger_details && incident.trigger_details.length > 0 && (
        <details>
          <summary>觸發證據與處置動作</summary>
          {incident.trigger_details.map((t, i) => (
            <div className="evidence" key={i}>
              <RuleBadge id={t.rule_id} /> <b>{t.entity_id}</b>
              <div className="mono small">{JSON.stringify(t.evidence, null, 1)}</div>
              <ul>{t.actions.map((a, j) => <li key={j}>{a}</li>)}</ul>
            </div>
          ))}
        </details>
      )}

      {incident.sop_evidence.length > 0 && (
        <details>
          <summary>SOP 依據原文（{incident.sop_evidence.map((s) => s.rule_id).join("、")}）</summary>
          {incident.sop_evidence.map((s) => (
            <div className="sop-text" key={s.rule_id}>
              <b>第 {s.rule_id} 條 {s.title}</b>
              <pre>{s.text}</pre>
            </div>
          ))}
        </details>
      )}

      {noti && (
        <>
          <h4>
            通報內容
            {noti.messages_meta && (
              <span className={`chip ${noti.messages_meta.source?.startsWith("llm") ? "green" : "amber"}`}>
                {noti.messages_meta.source?.startsWith("llm")
                  ? `LLM 生成（${noti.messages_meta.source.slice(4)}）` : "模板"}
              </span>
            )}
          </h4>
          {(noti.cms_meta?.guardrail_rejected || noti.messages_meta?.guardrail_rejected) && (
            <div className="warn small">
              ⚠ {noti.cms_meta?.guardrail_rejected ?? noti.messages_meta?.guardrail_rejected}
            </div>
          )}
          {noti.multilingual_decision && (
            <div className="small dim">
              <span className={`chip ${noti.multilingual_decision.triggered ? "purple" : ""}`}>
                SOP 6 {noti.multilingual_decision.triggered ? "已觸發" : "未觸發"}
              </span>
              {noti.multilingual_decision.assumed && (
                <span className="chip amber" title={
                  `實際最高漫遊率 ${noti.multilingual_decision.actual_max_pct}%`
                }>假設值</span>
              )}
              {noti.multilingual_decision.reason}
            </div>
          )}
          {noti.cms && <div className="cms">CMS：{noti.cms}</div>}
          {noti.messages &&
            Object.entries(noti.messages as Record<string, string>).map(([lang, msg]) => (
              <div className="msg" key={lang}>
                <span className="lang">{lang}</span> {msg}
              </div>
            ))}
        </>
      )}
    </div>
  );
}

// ---- 通報生命週期（核准 → 發布 → 送達） ----

const NOTI_STATUS_LABEL: Record<string, string> = {
  READY_FOR_APPROVAL: "待核准",
  APPROVED: "已核准",
  DISPATCHING: "發送中",
  DELIVERY_CONFIRMED: "已送達",
  DELIVERY_FAILED: "送達失敗",
  RETRYING: "重試中",
};

export function NotificationLifecyclePanel({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<any[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [previewLang, setPreviewLang] = useState<string>("zh");

  const reload = () => { api.notifications().then(setItems).catch(() => {}); };
  useEffect(reload, [refreshKey]);

  const op = async (id: string, action: "approve" | "dispatch" | "retry") => {
    setBusyId(id);
    try {
      await api.notificationOp(id, action);
      reload();
    } finally {
      setBusyId(null);
    }
  };

  if (!items.length) return null;
  return (
    <div className="panel">
      <h3>通報發布中心</h3>
      {items.map((n) => (
        <div className={`noti noti-${n.status}`} key={n.notification_id}>
          <div className="noti-head">
            <b>{n.notification_id}</b>
            <span className={`noti-status s-${n.status}`}>{NOTI_STATUS_LABEL[n.status] ?? n.status}</span>
          </div>
          <div className="dim small">{n.incident_id}｜{n.target_area}</div>
          {/* 語言切換預覽（點選切換中英日韓） */}
          {n.messages && Object.keys(n.messages).length > 0 && (
            <>
              <div className="lang-tabs">
                {Object.keys(n.messages).map((lang) => (
                  <button key={lang} className={previewLang === lang ? "active" : ""}
                    onClick={() => setPreviewLang(lang)}>
                    {lang}
                  </button>
                ))}
              </div>
              <div className="noti-preview" key={previewLang}>
                {n.messages[previewLang] ?? n.messages.zh}
              </div>
            </>
          )}
          {n.deliveries && (
            <>
              <div className="noti-deliveries">
                {n.deliveries.map((d: any) => (
                  <span key={d.channel}
                    className={`chip ${d.status === "DELIVERY_CONFIRMED" ? "green" : "red"}`}
                    title={d.detail}>
                    {d.channel} {d.status === "DELIVERY_CONFIRMED" ? "✓" : "✕"}
                  </span>
                ))}
              </div>
              <div className="delivery-rate">
                <div className="delivery-bar">
                  <i style={{
                    width: `${Math.round(
                      (n.deliveries.filter((d: any) => d.status === "DELIVERY_CONFIRMED").length /
                        n.channels.length) * 100)}%`,
                  }} />
                </div>
                <span className="rate-num">
                  送達 {n.deliveries.filter((d: any) => d.status === "DELIVERY_CONFIRMED").length}/{n.channels.length}
                </span>
              </div>
            </>
          )}
          <div className="da-actions">
            {n.status === "READY_FOR_APPROVAL" && (
              <button disabled={busyId === n.notification_id}
                onClick={() => op(n.notification_id, "approve")}>核准</button>
            )}
            {n.status === "APPROVED" && (
              <button disabled={busyId === n.notification_id}
                onClick={() => op(n.notification_id, "dispatch")}>發布</button>
            )}
            {n.status === "DELIVERY_FAILED" && (
              <button disabled={busyId === n.notification_id}
                onClick={() => op(n.notification_id, "retry")}>重試失敗通道</button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---- 自訂事件模擬器 ----

const FALLBACK_SEGMENT_OPTIONS = [
  ["RD_TPE_001", "忠孝東路四段"], ["RD_TPE_002", "光復南路"], ["RD_TPE_003", "基隆路一段"],
  ["RD_TPE_004", "市民大道四段"], ["RD_TPE_005", "仁愛路四段"], ["RD_TPE_006", "敦化南路一段"],
  ["RD_TPE_007", "松高路"], ["RD_TPE_008", "延吉街"], ["RD_TPE_009", "基隆路地下道"],
  ["RD_TPE_010", "市府路"], ["RD_TPE_011", "松壽路"], ["RD_TPE_012", "敦化南路二段"],
  ["RD_TPE_013", "信義路五段"], ["RD_TPE_014", "松智路"], ["RD_TPE_015", "復興南路一段"],
];
const FALLBACK_STATION_OPTIONS = [
  ["BS_MRT_BL17", "捷運國父紀念館站"], ["BS_MRT_BL18", "捷運市政府站"],
  ["BS_TPE_DOME", "臺北大巨蛋"], ["BS_TPE_101", "台北 101 廣場"],
  ["BS_XY_VIESHOW", "信義威秀商圈"], ["BS_XY_ATT", "ATT 4 FUN 周邊"],
] as [string, string][];

const CUSTOM_EVENT_TYPES = [
  ["Road_Collapse", "路面塌陷", 1],
  ["Traffic_Accident", "交通事故", .9],
  ["Power_Failure", "號誌故障", .7],
  ["Flooding", "道路積水", .82],
  ["Crowd_Surge_Injury", "人潮擁擠／暴增", .55],
] as const;
const CUSTOM_EVENT_STATUSES = [
  ["Closed", "完全封閉", "一般車輛不可通行，路線規劃排除事故路段", 1],
  ["Blocked", "嚴重阻塞", "道路接近無法通行，僅保留極低通行能力", .88],
  ["Restricted", "部分管制", "依封閉車道數降低道路容量", .64],
  ["Caution", "警戒通行", "仍可通行，但需降速並持續監測", .42],
] as const;
const CUSTOM_CROWD_STATUSES = [
  ["Crowded", "人潮擁擠", "人數高但仍可控制，啟動站點監測與分流評估"],
  ["Surging", "人潮快速增加", "依 5 分鐘增幅判斷是否達到預警門檻"],
  ["Dispersing", "大型活動散場", "人潮由場館向車站及周邊道路移動"],
] as const;
const SEVERITY_PREVIEW = {
  Critical: { saturation: .38, speedLoss: .78, label: "最高優先" },
  High: { saturation: .29, speedLoss: .62, label: "高優先" },
  Medium: { saturation: .19, speedLoss: .43, label: "一般應變" },
  Low: { saturation: .10, speedLoss: .24, label: "持續監測" },
} as const;

export function CustomEventForm({ onInjected, simTime }: {
  onInjected: (state: IncidentState) => void;
  simTime?: string | null;
}) {
  const initialForm = (timestamp: string) => ({
    type: "Road_Collapse",
    affected_segment: "RD_TPE_003",
    status: "Closed",
    severity: "High",
    timestamp: simTime ?? "2026-05-20 22:00",
    affected_direction: "both",
    lanes_total: 2,
    lanes_closed: 2,
    review_interval_minutes: 15,
    human_confirmed: true,
    description: "",
    roaming_override_pct: "",  // ""＝依實際資料
    crowd_user_count: 30_000,
    crowd_growth_pct: 50,
    crowd_roaming_pct: 30,
    crowd_stay_time_avg: 45,
  });
  const [form, setForm] = useState(() => initialForm(simTime ?? "2026-05-20 22:00"));
  const [segments, setSegments] = useState(FALLBACK_SEGMENT_OPTIONS);
  const [stations, setStations] = useState(FALLBACK_STATION_OPTIONS);
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api.roadNetwork(), api.timeline(), api.crowdStations()]).then(([roads, timeline, crowdStations]) => {
      if (!active) return;
      const options = roads
        .filter((road: any) => String(road.segment_id).startsWith("RD_"))
        .map((road: any) => [String(road.segment_id), String(road.name)] as [string, string]);
      if (options.length) setSegments(options);
      const stationOptions = crowdStations.map((station) => (
        [station.station_id, station.name] as [string, string]
      ));
      if (stationOptions.length) setStations(stationOptions);
      setTimestamps(timeline.timestamps);
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (simTime) setForm((current) => ({ ...current, timestamp: simTime }));
  }, [simTime]);

  const set = (key: keyof typeof form, value: string | number | boolean) => {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "status" && value === "Closed") next.lanes_closed = next.lanes_total;
      if (key === "lanes_total") {
        next.lanes_closed = next.status === "Closed"
          ? Number(value)
          : Math.min(next.lanes_closed, Number(value));
      }
      return next;
    });
  };

  const isCrowd = form.type === "Crowd_Surge_Injury";
  const changeType = (type: string) => {
    setForm((current) => type === "Crowd_Surge_Injury"
      ? { ...current, type, affected_segment: "BS_MRT_BL17", status: "Surging", description: "" }
      : { ...current, type, affected_segment: "RD_TPE_003", status: "Blocked", description: "" });
  };
  const resetForm = () => {
    setForm(initialForm(simTime ?? form.timestamp));
    setError("");
  };

  const statusOption = CUSTOM_EVENT_STATUSES.find(([value]) => value === form.status)
    ?? CUSTOM_EVENT_STATUSES[1];
  const crowdStatusOption = CUSTOM_CROWD_STATUSES.find(([value]) => value === form.status)
    ?? CUSTOM_CROWD_STATUSES[0];
  const typeOption = CUSTOM_EVENT_TYPES.find(([value]) => value === form.type)!;
  const severity = SEVERITY_PREVIEW[form.severity as keyof typeof SEVERITY_PREVIEW];
  const initialIntensity = statusOption[3] * typeOption[2] * .55;
  const previewSpeedLoss = form.status === "Closed"
    ? 100
    : Math.round(severity.speedLoss * initialIntensity * 100);
  const previewSaturation = Math.round(severity.saturation * initialIntensity * 100) / 100;
  const capacityPct = form.status === "Closed"
    ? 0
    : Math.round((1 - form.lanes_closed / form.lanes_total) * 100);

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const segName = (isCrowd ? stations : segments)
        .find(([id]) => id === form.affected_segment)?.[1] ?? "";
      const state = await api.customIncident({
        ...form,
        source_type: "operator", // 自訂事件只來自已登入的指揮中心操作員
        // 空字串＝不覆寫，須送 null 而非 ""（後端欄位為 float | None）
        roaming_override_pct: form.roaming_override_pct === ""
          ? null : Number(form.roaming_override_pct),
        crowd_user_count_override: isCrowd ? Number(form.crowd_user_count) : null,
        crowd_growth_rate_override: isCrowd ? Number(form.crowd_growth_pct) / 100 : null,
        crowd_roaming_user_pct_override: isCrowd ? Number(form.crowd_roaming_pct) : null,
        crowd_stay_time_avg_override: isCrowd ? Number(form.crowd_stay_time_avg) : null,
        location: segName,
        description: form.description.trim() || (isCrowd
          ? `自訂人潮事件：${segName} ${crowdStatusOption[1]}，5 分鐘增幅 ${form.crowd_growth_pct}%`
          : `自訂模擬事件：${segName} ${typeOption[1]}，${statusOption[1]}`),
      });
      onInjected(state);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="panel custom-event">
      <summary><h3 style={{ display: "inline" }}>自訂事件模擬器</h3></summary>
      <p className="custom-event-intro">建立可重播的模擬事件；所有選項在注入前先顯示計算影響，不會直接修改真實設備。</p>
      <div className="form-grid">
        <label>{isCrowd ? "人潮站點" : "路段"}
          <select value={form.affected_segment} onChange={(e) => set("affected_segment", e.target.value)}>
            {(isCrowd ? stations : segments).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </label>
        <label>類型
          <select value={form.type} onChange={(e) => changeType(e.target.value)}>
            {CUSTOM_EVENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>狀態
          <select value={form.status} onChange={(e) => set("status", e.target.value)}>
            {(isCrowd ? CUSTOM_CROWD_STATUSES : CUSTOM_EVENT_STATUSES)
              .map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <small>{isCrowd ? crowdStatusOption[2] : statusOption[2]}</small>
        </label>
        <label>嚴重度
          <select value={form.severity} onChange={(e) => set("severity", e.target.value)}>
            <option value="Critical">重大｜最高優先</option><option value="High">高｜立即處理</option>
            <option value="Medium">中｜一般應變</option><option value="Low">低｜持續監測</option>
          </select>
        </label>
        {!isCrowd && <><label>影響方向
          <select value={form.affected_direction} onChange={(e) => set("affected_direction", e.target.value)}>
            <option value="both">雙向</option><option value="northbound">北向</option>
            <option value="southbound">南向</option><option value="eastbound">東向</option>
            <option value="westbound">西向</option>
          </select>
        </label>
        <label>總車道數
          <input type="number" min={1} max={8} value={form.lanes_total}
            onChange={(e) => set("lanes_total", Number(e.target.value))} />
        </label>
        <label>封閉車道數
          <input type="number" min={0} max={form.lanes_total} value={form.lanes_closed}
            disabled={form.status === "Closed"}
            onChange={(e) => set("lanes_closed", Number(e.target.value))} />
        </label></>}
        <label>時間
          <select value={form.timestamp} onChange={(e) => set("timestamp", e.target.value)}>
            {(timestamps.length ? timestamps : [form.timestamp]).map((timestamp) => (
              <option key={timestamp} value={timestamp}>{timestamp.slice(11)}｜資料時間點</option>
            ))}
          </select>
        </label>
        {!isCrowd && <label>漫遊率
          <select value={form.roaming_override_pct}
            onChange={(e) => set("roaming_override_pct", e.target.value)}>
            <option value="">依實際資料</option>
            {["8", "15", "25", "29", "30", "45"].map((p) => (
              <option key={p} value={p}>{p}%（假設值）</option>
            ))}
          </select>
        </label>}
        {isCrowd && <>
          <label>站點人數
            <input type="number" min={0} max={200000} step={500}
              value={form.crowd_user_count} onChange={(e) => set("crowd_user_count", Number(e.target.value))} />
          </label>
          <label>5 分鐘人流增幅
            <input type="number" min={-100} max={500} step={5}
              value={form.crowd_growth_pct} onChange={(e) => set("crowd_growth_pct", Number(e.target.value))} />
            <small>50 代表五分鐘增加 50%</small>
          </label>
          <label>漫遊使用者比例
            <input type="number" min={0} max={100} step={1}
              value={form.crowd_roaming_pct} onChange={(e) => set("crowd_roaming_pct", Number(e.target.value))} />
          </label>
          <label>平均停留時間
            <input type="number" min={0} max={600} step={5}
              value={form.crowd_stay_time_avg} onChange={(e) => set("crowd_stay_time_avg", Number(e.target.value))} />
            <small>分鐘</small>
          </label>
        </>}
        <label>重新評估間隔
          <select value={form.review_interval_minutes} onChange={(e) => set("review_interval_minutes", Number(e.target.value))}>
            {[5, 10, 15, 30, 60].map((minutes) => <option key={minutes} value={minutes}>{minutes} 分鐘</option>)}
          </select>
          <small>到期由 Coordinator 驗證成效；未達標自動重規劃，事件結束仍需現場確認</small>
        </label>
        <label className="custom-event-confirm">
          <input type="checkbox" checked={form.human_confirmed}
            onChange={(e) => set("human_confirmed", e.target.checked)} />
          已由人員確認事件
        </label>
        <label className="custom-event-description">補充描述
          <textarea rows={2} value={form.description}
            placeholder={isCrowd ? "例如：活動散場後人潮持續湧入捷運入口" : "例如：內側兩車道塌陷，現場已設置封鎖線"}
            onChange={(e) => set("description", e.target.value)} />
        </label>
      </div>
      <div className="custom-impact-preview">
        <div><b>注入前影響預覽</b><span>固定規則｜可重播</span></div>
        {isCrowd ? <ul>
          <li>站點人數：<strong>{Number(form.crowd_user_count).toLocaleString()} 人</strong></li>
          <li>5 分鐘增幅：<strong>{form.crowd_growth_pct}%</strong></li>
          <li>漫遊率：<strong>{form.crowd_roaming_pct}%</strong></li>
          <li>規則判定：<strong>{form.affected_segment === "BS_MRT_BL17"
            && (form.crowd_user_count > 25_000 || form.crowd_growth_pct > 30)
            ? "將觸發捷運分流"
            : form.crowd_growth_pct >= 50
              ? "將觸發單站人潮分流"
              : "持續監測（尚未達門檻）"}</strong></li>
        </ul> : <ul>
          <li>初始道路容量：<strong>{capacityPct}%</strong></li>
          <li>初始速度影響：<strong>{form.status === "Closed" ? "一般通行歸零" : `約下降 ${previewSpeedLoss}%`}</strong></li>
          <li>初始飽和度：<strong>約增加 {previewSaturation}</strong></li>
          <li>應變層級：<strong>{severity.label}</strong></li>
        </ul>}
        <small>{isCrowd
          ? "人潮數值只覆寫本次模擬快照；BL17 依主辦方 SOP 3 判定，其他站點則依競賽需求範例的 5 分鐘增幅 ≥50% 啟動分流。"
          : `依據：狀態係數 ${statusOption[3]} × 類型係數 ${typeOption[2]} × 初始時間係數 0.55；30 分鐘內逐步達完整影響。`}</small>
      </div>
      {form.roaming_override_pct !== "" && (
        <p className="dim small">
          以假設值 {form.roaming_override_pct}% 取代該時間切面的實際漫遊率，用於演示
          SOP 6 門檻（≥ 30% 才須多語）。來源資料不會被修改，事件與通報會標示為假設值。
        </p>
      )}
      <div className="custom-event-actions">
        <button type="button" disabled={busy} onClick={resetForm}>重設參數</button>
        <button className="primary" disabled={busy} onClick={submit}>
          {busy ? "分析中…" : "注入模擬事件"}
        </button>
      </div>
      {error && <div className="warn">{error}</div>}
    </details>
  );
}

function ClosedLoopCoordinatorCard({ loop }: { loop: NonNullable<IncidentState["closed_loop"]> }) {
  const metrics = loop.latest_metrics;
  const statusLabels: Record<string, string> = {
    AWAITING_COMMANDER_APPROVAL: "等待指揮官核准",
    EXECUTING_APPROVED_PLAN: "執行核准方案",
    VERIFYING_RESPONSE: "驗證處置成效",
    EFFECTIVE_MONITORING: "成效達標，持續監測",
    REPLAN_REQUIRED: "未達標，重新規劃",
    REPLAN_AWAITING_APPROVAL: "新方案等待核准",
    FIELD_CONFIRMATION_REQUIRED: "模擬已恢復，等待現場確認",
    RESOLVED: "事件閉環完成",
  };
  return (
    <section className={`closed-loop-card loop-${loop.status.toLowerCase()}`}>
      <div className="cl-head">
        <div><small>閉環 Coordinator</small><b>{statusLabels[loop.status] ?? loop.status}</b></div>
        <span>第 {loop.cycle_count} 輪</span>
      </div>
      <div className="cl-flow" aria-label="閉環控制流程">
        <span>感知</span><i>→</i><span>規劃</span><i>→</i><span>核准</span><i>→</i><span>執行</span><i>→</i><span>驗證</span><i>↻</i>
      </div>
      {metrics && (
        <div className="cl-metrics">
          {metrics.metric_type === "traffic" ? <>
            <div><small>飽和度改善</small><b>{Number(metrics.saturation_reduction ?? 0).toFixed(2)}</b></div>
            <div><small>速度改善</small><b>{Number(metrics.speed_gain_kmh ?? 0).toFixed(1)} km/h</b></div>
          </> : <div><small>人流下降</small><b>{Math.round(Number(metrics.crowd_reduction_ratio ?? 0) * 100)}%</b></div>}
          <div><small>處置進度</small><b>{Math.round(Number(metrics.mitigation_progress ?? 0) * 100)}%</b></div>
        </div>
      )}
      <div className="cl-foot">
        <span>下次檢核 {loop.next_review_at.slice(11, 16)}</span>
        <span>已重規劃 {loop.replan_count} 次</span>
        {loop.pending_human_gate && <strong>需人工閘門</strong>}
      </div>
      <p>Coordinator 自動監測、驗證與重規劃；號誌、分流、派遣及對外通知仍需一次明確核准。</p>
    </section>
  );
}

// ---- AI 摘要 ----

export function AISummarySection({ incident }: { incident: IncidentState }) {
  const [summary, setSummary] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => setSummary((incident as any).ai_summary ?? null), [incident.incident_id]);

  const generate = async () => {
    setBusy(true);
    try {
      setSummary(await api.aiSummary(incident.incident_id));
    } catch { /* ignore */ } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ai-summary">
      <h4>
        AI 交控摘要
        <button className="mini" disabled={busy} onClick={generate}>
          {busy ? "生成中…" : summary ? "重新生成" : "生成"}
        </button>
      </h4>
      {summary && (
        <div className={`ai-box ${summary.llm_generated ? "" : "fallback"}`}>
          <div className="ai-meta">
            {summary.llm_generated
              ? <span className="chip green">LLM 生成（{summary.provider}）</span>
              : <span className="chip amber">確定性模板（LLM 未啟用或被 guardrail 攔截）</span>}
            <span className="chip green">需人工核准</span>
          </div>
          <p>{summary.summary}</p>
          <div>引用條款：{summary.cited_rule_ids.map((r: number) => <RuleBadge key={r} id={r} />)}</div>
          {summary.recommended_actions?.length > 0 && (
            <ul className="actions">
              {summary.recommended_actions.map((a: string, i: number) => <li key={i}>{a}</li>)}
            </ul>
          )}
          {summary.guardrail_rejected && (
            <div className="warn small">⚠ {summary.guardrail_rejected}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ---- 決策鏈 ----

export function TracePanel({ incident }: { incident: IncidentState | null }) {
  // 步驟逐步展開（staggered）＋ 點擊查看該步證據
  const [expanded, setExpanded] = useState<number | null>(null);
  useEffect(() => setExpanded(null), [incident?.incident_id]);
  if (!incident) return (
    <div className="panel trace"><h3>Agent 決策鏈</h3><p className="dim">注入事件後顯示處理流程</p></div>
  );
  const step = expanded != null ? incident.decision_trace[expanded] : null;
  return (
    <div className="panel trace">
      <h3>Agent 決策鏈｜{incident.incident_id}</h3>
      <div className="trace-flow">
        {incident.decision_trace.map((t, i) => (
          <div
            className={`trace-step ${expanded === i ? "expanded" : ""}`}
            key={`${incident.incident_id}-${i}`}
            style={{ animationDelay: `${i * 80}ms` }}
            onClick={() => setExpanded(expanded === i ? null : i)}
          >
            <div className="dot" />
            <div className="step-name">{t.step}</div>
            <div className="step-time">{t.at.slice(11)}</div>
          </div>
        ))}
      </div>
      {step && (
        <div className="trace-detail">
          <div className="td-step">{step.step}｜{step.at.slice(11)}</div>
          <div className="mono small">{JSON.stringify(step.detail, null, 2)}</div>
        </div>
      )}
    </div>
  );
}

// ---- What-if ----

const PRESETS = [
  "如果 17:00 BL17 人數增加到 40000 人會怎樣？",
  "假設 17:00 台北101漫遊率 50%",
  "如果封閉忠孝東路會怎樣？",
];

export function WhatIfPanel() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const ask = async (question: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/what-if/nl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "解析失敗");
      setResult(data);
    } catch (e: any) {
      setError(e.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel whatif">
      <h3>What-if 策略諮詢</h3>
      <div className="presets">
        {PRESETS.map((p) => (
          <button key={p} onClick={() => { setQ(p); ask(p); }}>{p}</button>
        ))}
      </div>
      <div className="ask-row">
        <input
          value={q}
          placeholder="輸入假設問題…"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && q && ask(q)}
        />
        <button disabled={!q || loading} onClick={() => ask(q)}>
          {loading ? "計算中…" : "分析"}
        </button>
      </div>
      {error && <div className="warn">{error}</div>}
      {result && (
        <div className="whatif-result">
          <div className="row">
            <span className="dim">時間切面 {result.as_of}</span>
            <span className="chip green">正式狀態未修改</span>
          </div>
          <div className="compare">
            <div>
              <b>基準</b>：{result.baseline.triggered_rules.length
                ? result.baseline.triggered_rules.map((r: number) => <RuleBadge key={r} id={r} />)
                : "無觸發"}
            </div>
            <div>
              <b>假設後</b>：{result.sandbox.triggered_rules.length
                ? result.sandbox.triggered_rules.map((r: number) => <RuleBadge key={r} id={r} />)
                : "無觸發"}
            </div>
          </div>
          {result.diff.newly_triggered_rules.length > 0 && (
            <div className="new-rules">
              新觸發：{result.diff.newly_triggered_rules.map((r: number) => <RuleBadge key={r} id={r} />)}
            </div>
          )}
          {result.sandbox.triggers?.map((t: any, i: number) => (
            <div
              key={i}
              className={`evidence ${result.diff.newly_triggered_rules.includes(t.rule_id) ? "highlight" : ""}`}
            >
              <RuleBadge id={t.rule_id} /> <b>{t.entity_id}</b>
              <ul className="actions">
                {t.actions.map((a: string, j: number) => <li key={j}>{a}</li>)}
              </ul>
            </div>
          ))}
          {result.sandbox.routing_result?.primary_route && (
            <div className="route primary">
              模擬主疏散：<b>{result.sandbox.routing_result.primary_route.name}</b>
              {result.sandbox.ete_result && `｜ETE ${result.sandbox.ete_result.ete_minutes_display} 分`}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
