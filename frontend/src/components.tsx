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
  3: "捷運分流",
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

export function AlertFeed({ alerts }: { alerts: Alert[] }) {
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
            <span className="alert-entity">{a.entity_id}</span>
            <div className="alert-actions">{a.actions.join("；")}</div>
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
}: {
  incident: IncidentState;
  onRefresh: () => void;
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
            配置：
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
          {a.status !== "rejected" && (
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

export function DecisionStages({ incident }: { incident: IncidentState | null }) {
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => setOpen(null), [incident?.incident_id]);
  if (!incident) return <p className="dim">注入事件後顯示決策依據與執行進度。</p>;

  const trace = incident.decision_trace;
  const done = new Set(trace.map((t) => t.step));
  const failed = incident.workflow_status === "failed";

  return (
    <div className="stages">
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
              <b>{t.step}</b> <span className="dim">{t.at.slice(11)}</span>
              <div className="mono small">{JSON.stringify(t.detail, null, 1)}</div>
            </div>
          ))}
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

export function IncidentDetail({ incident, onRefresh }: { incident: IncidentState; onRefresh: () => void }) {
  const routing = incident.routing_result;
  const ete = incident.ete_result;
  const noti = incident.notifications;
  const attr = incident.rule_attribution;
  return (
    <div className="incident-detail">
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

      <DispatchSection incident={incident} onRefresh={onRefresh} />

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

const SEGMENT_OPTIONS = [
  ["RD_TPE_001", "忠孝東路四段"], ["RD_TPE_002", "光復南路"], ["RD_TPE_003", "基隆路一段"],
  ["RD_TPE_004", "市民大道四段"], ["RD_TPE_005", "仁愛路四段"], ["RD_TPE_006", "敦化南路一段"],
  ["RD_TPE_007", "松高路"], ["RD_TPE_008", "延吉街"], ["RD_TPE_009", "基隆路地下道"],
  ["RD_TPE_010", "市府路"], ["RD_TPE_011", "松壽路"], ["RD_TPE_012", "敦化南路二段"],
  ["RD_TPE_013", "信義路五段"], ["RD_TPE_014", "松智路"], ["RD_TPE_015", "復興南路一段"],
];

export function CustomEventForm({ onInjected }: { onInjected: (state: IncidentState) => void }) {
  const [form, setForm] = useState({
    type: "Road_Collapse",
    affected_segment: "RD_TPE_003",
    status: "Closed",
    severity: "High",
    timestamp: "2026-05-20 22:00",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const segName = SEGMENT_OPTIONS.find(([id]) => id === form.affected_segment)?.[1] ?? "";
      const state = await api.customIncident({
        ...form,
        location: segName,
        description: `自訂模擬事件：${segName} ${form.type}`,
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
      <div className="form-grid">
        <label>路段
          <select value={form.affected_segment} onChange={(e) => set("affected_segment", e.target.value)}>
            {SEGMENT_OPTIONS.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </label>
        <label>類型
          <select value={form.type} onChange={(e) => set("type", e.target.value)}>
            <option value="Road_Collapse">路面塌陷</option>
            <option value="Traffic_Accident">交通事故</option>
            <option value="Power_Failure">號誌故障</option>
            <option value="Flooding">道路積水</option>
          </select>
        </label>
        <label>狀態
          <select value={form.status} onChange={(e) => set("status", e.target.value)}>
            <option>Closed</option><option>Blocked</option>
            <option>Restricted</option><option>Caution</option>
          </select>
        </label>
        <label>嚴重度
          <select value={form.severity} onChange={(e) => set("severity", e.target.value)}>
            <option>Critical</option><option>High</option>
            <option>Medium</option><option>Low</option>
          </select>
        </label>
        <label>時間
          <select value={form.timestamp} onChange={(e) => set("timestamp", e.target.value)}>
            {["17:00", "19:00", "21:00", "21:30", "22:00", "22:15", "22:30"].map((t) => (
              <option key={t} value={`2026-05-20 ${t}`}>{t}</option>
            ))}
          </select>
        </label>
      </div>
      <button className="primary" disabled={busy} onClick={submit}>
        {busy ? "分析中…" : "注入模擬事件"}
      </button>
      {error && <div className="warn">{error}</div>}
    </details>
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
