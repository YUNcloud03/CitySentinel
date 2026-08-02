// 交控中心建議書：把事件處理結果排版為可交付的正式文件。
// 內容全部來自後端 /recommendation（僅重組引擎輸出，不重新判定），
// 此處只負責排版與列印樣式，不做任何數值推導。
import { useEffect, useRef, useState } from "react";
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

// ---- 匯出 ----

/** 下載檔的內嵌樣式：不依賴 app 的 CSS 變數，單一檔案即可正確呈現。 */
const EXPORT_CSS = `
body { font-family: "Microsoft JhengHei", "PingFang TC", sans-serif;
  max-width: 860px; margin: 24px auto; padding: 0 20px; color: #111; line-height: 1.6; }
h2 { font-size: 20px; margin: 0 0 4px; }
h3 { font-size: 15px; margin: 22px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #ccc; }
h4 { font-size: 13px; margin: 12px 0 4px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; }
th, td { padding: 5px 8px; border-top: 1px solid #ddd; text-align: left;
  font-size: 13px; vertical-align: top; }
thead th { border-top: none; border-bottom: 1px solid #999; color: #555; font-size: 12px; }
.rec-kv th { width: 96px; color: #555; }
.chip { display: inline-block; padding: 1px 7px; margin: 1px 3px 1px 0;
  border: 1px solid #999; border-radius: 10px; font-size: 11.5px; }
.rec-num { display: inline-block; width: 19px; height: 19px; line-height: 19px;
  border-radius: 50%; background: #ddd; text-align: center; font-size: 12px; margin-right: 6px; }
.dim, .small { color: #555; font-size: 12px; }
.rec-route.primary { padding: 6px 9px; background: #f2f5f8; border-radius: 5px; }
.warn, .rec-assumption { padding: 7px 9px; background: #fff6e5;
  border-left: 3px solid #d9a400; margin: 10px 0; font-size: 12.5px; }
.rec-footer { margin-top: 20px; padding-top: 8px; border-top: 1px solid #ccc; }
.rec-print, .rec-export { display: none; }
@page { margin: 14mm; }
`;

function triggerDownload(content: string, filename: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // 釋放 object URL，避免分頁存活期間累積佔用記憶體
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** 把畫面上的建議書輸出為單一自含 HTML——不引用外部樣式，可直接寄送或存檔。 */
function exportHtml(rec: any) {
  const node = document.querySelector(".rec-doc");
  if (!node) return;
  const title = `交控中心建議書 ${rec.identification.event_id}`;
  const html =
    `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<title>${title}</title><style>${EXPORT_CSS}</style></head>` +
    `<body>${node.innerHTML}</body></html>`;
  triggerDownload(html, `${title}.html`, "text/html");
}

/** 原始 JSON：供評審核對數值來源，或後續系統介接。 */
function exportJson(rec: any) {
  triggerDownload(
    JSON.stringify(rec, null, 2),
    `交控中心建議書 ${rec.identification.event_id}.json`,
    "application/json",
  );
}

/** 純文字摘要：便於貼入郵件或即時通訊，不含樣式。 */
function exportText(rec: any) {
  const id = rec.identification, g = rec.grading, r = rec.routing;
  const L: string[] = [
    `交控中心建議書｜${id.event_id}`,
    `地點：${id.location ?? "—"}｜評估時間：${id.assessed_at}`,
    "",
    "【1】事件辨識",
    `  類型：${id.type}／${id.status}／${id.severity}`,
    `  描述：${id.description ?? "—"}`,
    `  觸發條款：${id.triggered_rule_labels.join("、") || "無"}`,
    "",
    "【2】交通分級判定",
    ...(g.graded_segments.length
      ? g.graded_segments.map((s: any) =>
          `  ${s.name ?? s.segment_id}：${s.congestion_level} 級（${s.basis}）`)
      : ["  無達 B 級以上之管制路段"]),
    ...(g.ete_minutes != null ? [`  ETE：${g.ete_minutes} 分鐘（${g.ete_formula}）`] : []),
    "",
    "【3】替代路徑建議",
    ...(r.primary_route
      ? [
          `  主疏散：${r.primary_route.name}（容量 ${r.primary_route.capacity_vph} vph）`,
          ...(r.secondary_routes.length
            ? [`  次要替代：${r.secondary_routes.map((x: any) => x.name).join("、")}`] : []),
          "  排除理由：",
          ...r.excluded_routes.map((e: any) =>
            `    - ${e.name ?? e.segment_id}｜${e.reason_code}｜${e.detail}`),
        ]
      : ["  本事件未觸發替代路徑規劃"]),
    "",
    "【4】號誌調整建議",
    ...(rec.signal_plan.items.length
      ? rec.signal_plan.items.map((s: any) =>
          `  - ${s.action}${s.detail ? `（${s.detail}）` : ""}`)
      : ["  無號誌配時調整建議"]),
    `  ${rec.signal_plan.note}`,
    "",
    "【5】跨系統聯動",
    `  ${rec.interagency.trigger_reason}`,
    ...(rec.interagency.requests.length
      ? rec.interagency.requests.map((q: any) =>
          `  - ${q.agency}：${q.request}` +
          (q.requested_count != null
            ? `（核配 ${q.fulfilled_count}/${q.requested_count}${q.gap > 0 ? `，缺 ${q.gap}` : ""}）`
            : ""))
      : ["  無跨系統請求"]),
  ];
  if (rec.assumptions?.length) {
    L.push("", "【模擬假設值】", ...rec.assumptions.map((a: any) => `  ${a.note}`));
  }
  L.push("", rec.note);
  triggerDownload(L.join("\n"), `交控中心建議書 ${id.event_id}.txt`, "text/plain");
}

export default function RecommendationView({ incident }: { incident: IncidentState | null }) {
  const [rec, setRec] = useState<any>(null);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // 點選單外或按 Esc 即關閉——選單為浮層，不關會擋住文件內容
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

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
          <div className="rec-export" ref={menuRef}>
            <button className="primary" aria-haspopup="menu" aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}>
              匯出 ▾
            </button>
            {menuOpen && (
              <div className="rec-menu" role="menu">
                {([
                  ["列印 / 存成 PDF", "透過瀏覽器列印，保留完整排版", () => window.print()],
                  ["下載 HTML", "單一自含檔案，可直接寄送或存檔", () => exportHtml(rec)],
                  ["下載純文字", "無樣式摘要，便於貼入郵件或通訊軟體", () => exportText(rec)],
                  ["下載 JSON", "原始資料，供核對數值來源或系統介接", () => exportJson(rec)],
                ] as [string, string, () => void][]).map(([label, hint, fn]) => (
                  <button key={label} role="menuitem"
                    onClick={() => { setMenuOpen(false); fn(); }}>
                    <b>{label}</b>
                    <span className="dim small">{hint}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
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
          <p className="interagency-disclaimer">
            <b>{inter.external_system_connected ? "外部系統已連線" : "模擬聯動 Adapter"}</b>
            {inter.execution_disclaimer}
          </p>
          {inter.requests.length === 0 ? (
            <Empty>無跨系統請求。</Empty>
          ) : (
            <table className="rec-table">
              <thead><tr><th>受理單位</th><th>請求事項</th><th>狀態</th><th>依據</th></tr></thead>
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
                    <td><span className={`coord-status status-${String(r.status_code ?? "").toLowerCase()}`}>{r.status}</span></td>
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
