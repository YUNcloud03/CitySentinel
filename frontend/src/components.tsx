import { useEffect, useState } from "react";
import { api, type Alert, type CrowdRow, type IncidentState, type Resource, type SimView, type TrafficRow } from "./api";

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
  const nA = rows.filter((r) => r.congestion_level === "A").length;
  const nB = rows.filter((r) => r.congestion_level === "B").length;
  const alertLevel = nA > 0 ? "紅色警戒" : nB > 0 ? "黃色警戒" : "正常";
  const alertCls = nA > 0 ? "red" : nB > 0 ? "amber" : "green";
  const ete = incident?.ete_result;
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
        <div className="card-value">{ete ? `${ete.ete_minutes_display} 分` : "—"}</div>
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
  if (!alerts.length) return null;
  return (
    <div className="panel alert-feed">
      <h3>自動預警</h3>
      {alerts.map((a, i) => (
        <div className="alert-item" key={i}>
          <RuleBadge id={a.rule_id} />
          <span className="alert-entity">{a.entity_id}</span>
          <div className="alert-actions">{a.actions.join("；")}</div>
        </div>
      ))}
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
    op: "accept" | "reject" | "adjust",
    extra: { count?: number; reason?: string } = {}
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

function IncidentDetail({ incident, onRefresh }: { incident: IncidentState; onRefresh: () => void }) {
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
          <h4>通報內容</h4>
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

// ---- 決策鏈 ----

export function TracePanel({ incident }: { incident: IncidentState | null }) {
  if (!incident) return (
    <div className="panel trace"><h3>Agent 決策鏈</h3><p className="dim">注入事件後顯示處理流程</p></div>
  );
  return (
    <div className="panel trace">
      <h3>Agent 決策鏈｜{incident.incident_id}</h3>
      <div className="trace-flow">
        {incident.decision_trace.map((t, i) => (
          <div className="trace-step" key={i} title={JSON.stringify(t.detail)}>
            <div className="dot" />
            <div className="step-name">{t.step}</div>
            <div className="step-time">{t.at.slice(11)}</div>
          </div>
        ))}
      </div>
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
