// 交控中心建議書：把事件處理結果排版為可交付的正式文件。
// 內容全部來自後端 /recommendation（僅重組引擎輸出，不重新判定），
// 此處只負責排版與列印樣式，不做任何數值推導。
import { useEffect, useState } from "react";
import { api, type IncidentState } from "./api";

function Section({ n, title, children }: {
  n: number; title: string; children: React.ReactNode;
}) {
  return (
    <section className="rec-section">
      <h3><span className="rec-num">{n}</span>{title}</h3>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="dim small rec-empty">{children}</p>;
}

export default function RecommendationView({ incident }: { incident: IncidentState | null }) {
  const [rec, setRec] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!incident) { setRec(null); return; }
    setError("");
    api.recommendation(incident.incident_id)
      .then(setRec)
      .catch((e) => setError(e.message));
  }, [incident?.incident_id]);

  if (!incident) {
    return (
      <main className="rec-view">
        <div className="panel">
          <h3>交控中心建議書</h3>
          <p className="dim">尚未處理任何事件——請先於「指揮中心」注入事件，本頁將產出建議書。</p>
        </div>
      </main>
    );
  }
  if (error) return <main className="rec-view"><div className="panel warn">{error}</div></main>;
  if (!rec) return <main className="rec-view"><div className="panel dim">產生中…</div></main>;

  const id = rec.identification;
  const grading = rec.grading;
  const routing = rec.routing;
  const signal = rec.signal_plan;
  const inter = rec.interagency;

  return (
    <main className="rec-view">
      <div className="panel rec-doc">
        <div className="rec-header">
          <div>
            <h2>交控中心建議書</h2>
            <div className="dim small">
              {id.event_id}｜{id.location ?? "—"}｜評估時間 {id.assessed_at}
            </div>
          </div>
          <button className="primary rec-print" onClick={() => window.print()}>
            列印 / 存成 PDF
          </button>
        </div>

        {rec.assumptions?.length > 0 && (
          <div className="warn small rec-assumption">
            ⚠ 本建議書含模擬假設值：
            {rec.assumptions.map((a: any) => a.note).join("；")}
          </div>
        )}

        <Section n={1} title="事件辨識">
          <table className="rec-kv">
            <tbody>
              <tr><th>事件編號</th><td>{id.event_id}</td></tr>
              <tr><th>事件類型</th><td>{id.type}｜{id.status}｜{id.severity}</td></tr>
              <tr><th>發生地點</th><td>{id.location ?? "—"}</td></tr>
              <tr><th>發生時間</th><td>{id.occurred_at ?? "—"}</td></tr>
              <tr><th>事件描述</th><td>{id.description ?? "—"}</td></tr>
              <tr>
                <th>觸發條款</th>
                <td>
                  {id.triggered_rule_labels.length === 0
                    ? "無"
                    : id.triggered_rule_labels.map((l: string) => (
                        <span className="chip" key={l}>{l}</span>
                      ))}
                </td>
              </tr>
              <tr>
                <th>條款歸因</th>
                <td className="small dim">
                  事件直接觸發：{id.caused_by_incident.join("、") || "無"}；
                  環境既有：{id.context_rules.join("、") || "無"}
                </td>
              </tr>
            </tbody>
          </table>
        </Section>

        <Section n={2} title="交通分級判定">
          {grading.graded_segments.length === 0 ? (
            <Empty>本時間切面無達 B 級以上之管制路段。</Empty>
          ) : (
            <table className="rec-table">
              <thead>
                <tr><th>路段</th><th>分級</th><th>飽和度</th><th>判定依據</th></tr>
              </thead>
              <tbody>
                {grading.graded_segments.map((g: any) => (
                  <tr key={g.segment_id}>
                    <td>{g.name ?? g.segment_id}</td>
                    <td><span className={`chip ${g.congestion_level === "A" ? "red" : "amber"}`}>
                      {g.congestion_level} 級
                    </span></td>
                    <td>{g.saturation_score}</td>
                    <td className="small">{g.basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="small dim">
            門檻：A 級 ≥ {grading.thresholds.level_a}，B 級 ≥ {grading.thresholds.level_b}。
            {grading.ete_minutes != null && (
              <> 預估清空時間（ETE）{grading.ete_minutes} 分鐘：{grading.ete_formula}</>
            )}
          </p>
        </Section>

        <Section n={3} title="替代路徑建議">
          {!routing.primary_route ? (
            <Empty>本事件未觸發替代路徑規劃（非路段類事件）。</Empty>
          ) : (
            <>
              <div className="rec-route primary">
                <b>主疏散路徑</b>：{routing.primary_route.name}
                <span className="dim small">
                  （容量 {routing.primary_route.capacity_vph} vph／
                  飽和度 {routing.primary_route.saturation_score}）
                </span>
              </div>
              {routing.secondary_routes.length > 0 && (
                <div className="rec-route">
                  <b>次要替代</b>：
                  {routing.secondary_routes.map((r: any) => (
                    <span key={r.segment_id}>
                      {r.name}（容量 {r.capacity_vph} vph）
                    </span>
                  ))}
                </div>
              )}
              <h4 className="small">排除其他候選之理由</h4>
              <table className="rec-table">
                <thead><tr><th>路段</th><th>代碼</th><th>理由</th></tr></thead>
                <tbody>
                  {routing.excluded_routes.map((e: any) => (
                    <tr key={e.segment_id}>
                      <td>{e.name ?? e.segment_id}</td>
                      <td className="mono small">{e.reason_code}</td>
                      <td className="small">{e.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Section>

        <Section n={4} title="號誌調整建議">
          {signal.items.length === 0 ? (
            <Empty>本事件無號誌配時調整建議。</Empty>
          ) : (
            <ul className="rec-list">
              {signal.items.map((s: any, i: number) => (
                <li key={i}>
                  {s.action}
                  {s.detail && <span className="dim small">（{s.detail}）</span>}
                  <span className="chip small">{s.rule_label}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="small dim">{signal.note}</p>
        </Section>

        <Section n={5} title="跨系統聯動">
          <p className="small dim">{inter.trigger_reason}</p>
          {inter.requests.length === 0 ? (
            <Empty>無跨系統請求。</Empty>
          ) : (
            <table className="rec-table">
              <thead><tr><th>受理單位</th><th>請求事項</th><th>依據</th></tr></thead>
              <tbody>
                {inter.requests.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.agency}</td>
                    <td>
                      {r.request}
                      {r.requested_count != null && (
                        <span className="dim small">
                          （核配 {r.fulfilled_count}/{r.requested_count}
                          {r.gap > 0 && <b className="warn-text">，缺 {r.gap}</b>}）
                        </span>
                      )}
                    </td>
                    <td className="small">{r.rule_label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {inter.resource_gaps?.length > 0 && (
            <p className="warn small">
              資源缺口需指揮官裁示抽調：
              {inter.resource_gaps.map((g: any) =>
                `${g.resource_type ?? ""} 缺 ${g.gap ?? ""}`).join("、")}
            </p>
          )}
        </Section>

        <p className="dim small rec-footer">{rec.note}</p>
      </div>
    </main>
  );
}
