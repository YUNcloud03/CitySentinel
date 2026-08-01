import { useEffect, useMemo, useState } from "react";
import { api, type DecisionAction, type DecisionResult, type SimView } from "./api";

type PlanName = "方案 A" | "方案 B";

interface Props {
  selectedSegmentId: string | null;
  view: SimView | null;
  onPreview: (result: DecisionResult | null) => void;
}

const ACTIONS = [
  { type: "extend_green", label: "延長綠燈", detail: "提高路口放行效率" },
  { type: "open_lane", label: "開放調撥車道", detail: "短時增加通行容量" },
  { type: "police_control", label: "警力手動疏導", detail: "減少路口衝突與延滯" },
] as const;

function Metric({ label, before, after, unit = "" }: { label: string; before: number; after: number; unit?: string }) {
  const good = label.includes("車速") ? after >= before : after <= before;
  return (
    <div className="sim-metric">
      <span>{label}</span>
      <b>{after}{unit}</b>
      <small className={good ? "good" : "bad"}>{after > before ? "+" : ""}{(after - before).toFixed(1)}{unit}</small>
    </div>
  );
}

export default function DecisionSandbox({ selectedSegmentId, view, onPreview }: Props) {
  const [network, setNetwork] = useState<any[]>([]);
  const [plan, setPlan] = useState<PlanName>("方案 A");
  const [enabled, setEnabled] = useState<string[]>(["extend_green"]);
  const [divert, setDivert] = useState(false);
  const [target, setTarget] = useState("");
  const [disruption, setDisruption] = useState("none");
  const [customLoad, setCustomLoad] = useState(25);
  const [results, setResults] = useState<Partial<Record<PlanName, DecisionResult>>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { api.roadNetwork().then(setNetwork).catch(() => {}); }, []);
  const segment = useMemo(() => network.find((r) => r.segment_id === selectedSegmentId), [network, selectedSegmentId]);
  const alternatives = useMemo(
    () => (segment?.alternatives ?? []).map((id: string) => network.find((r) => r.segment_id === id)).filter(Boolean),
    [network, segment]
  );
  useEffect(() => { setTarget(alternatives[0]?.segment_id ?? ""); }, [selectedSegmentId, alternatives.length]);

  const toggle = (type: string) => setEnabled((old) => old.includes(type) ? old.filter((x) => x !== type) : [...old, type]);
  const run = async () => {
    if (!selectedSegmentId) return;
    setLoading(true); setError("");
    const actions: DecisionAction[] = enabled.map((type) => ({ type: type as DecisionAction["type"], segment_id: selectedSegmentId }));
    if (divert && target) actions.push({ type: "divert", segment_id: selectedSegmentId, target_segment_id: target, share: .3 });
    try {
      const result = await api.decisionSandbox({
        name: plan,
        at: view?.sim_time ?? "2026-05-20 22:00",
        focus_segment_id: selectedSegmentId,
        actions,
        disruption,
        disruption_segment_id: selectedSegmentId,
        disruption_load: disruption === "custom_load" ? customLoad : undefined,
      });
      setResults((old) => ({ ...old, [plan]: result }));
      onPreview(result);
    } catch (e: any) { setError(e.message ?? "推演失敗"); }
    finally { setLoading(false); }
  };

  if (!selectedSegmentId) return (
    <div className="sandbox-empty">
      <span className="sandbox-cursor">⌖</span>
      <b>先在地圖點選一條道路</b>
      <p>選取壅塞路段後，可控制號誌、調撥車道、設定分流，並比較方案 A/B。</p>
    </div>
  );

  const result = results[plan];
  const a = results["方案 A"], b = results["方案 B"];
  return (
    <div className="decision-sandbox">
      <div className="sandbox-head">
        <div><span className="eyebrow">人工決策沙盒</span><h3>{segment?.name ?? selectedSegmentId}</h3></div>
        <span className="chip green">正式狀態不受影響</span>
      </div>

      <div className="plan-switch">
        {(["方案 A", "方案 B"] as PlanName[]).map((name) => (
          <button key={name} className={plan === name ? "active" : ""} onClick={() => { setPlan(name); onPreview(results[name] ?? null); }}>
            {name}{results[name] ? " ✓" : ""}
          </button>
        ))}
      </div>

      <label className="sandbox-label">1. 選擇處置措施</label>
      <div className="action-grid">
        {ACTIONS.map((action) => (
          <button key={action.type} className={enabled.includes(action.type) ? "selected" : ""} onClick={() => toggle(action.type)}>
            <b>{action.label}</b><small>{action.detail}</small>
          </button>
        ))}
        <button className={divert ? "selected" : ""} onClick={() => setDivert(!divert)}>
          <b>引流其他道路</b><small>把 30% 車流移至替代路段</small>
        </button>
      </div>
      {divert && <label className="field-row">引流至
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          {alternatives.map((r: any) => <option key={r.segment_id} value={r.segment_id}>{r.name}</option>)}
        </select>
      </label>}

      <label className="sandbox-label">2. 加入其他突發情況</label>
      <select className="sandbox-select" value={disruption} onChange={(e) => setDisruption(e.target.value)}>
        <option value="none">無額外事件</option><option value="rain">強降雨（全區降速）</option>
        <option value="secondary_accident">次生事故（目標路段）</option><option value="pedestrian_surge">散場人潮湧入</option>
        <option value="custom_load">自訂額外車流</option>
      </select>
      {disruption === "custom_load" && <label className="load-input">額外負荷
        <input type="range" min="0" max="80" value={customLoad} onChange={(e) => setCustomLoad(Number(e.target.value))} />
        <b>+{customLoad}%</b>
      </label>}

      <button className="primary run-sim" disabled={loading || (!enabled.length && !divert)} onClick={run}>
        {loading ? "正在推演 20 分鐘後狀況…" : `執行 ${plan}`}
      </button>
      {error && <p className="warn">{error}</p>}

      {result && <div className="sim-result">
        <div className="result-verdict">{result.verdict}</div>
        <div className="metric-grid">
          <Metric label="路段飽和度" before={result.baseline_metrics.focus_saturation} after={result.projected_metrics.focus_saturation} />
          <Metric label="平均車速" before={result.baseline_metrics.focus_speed} after={result.projected_metrics.focus_speed} unit=" km/h" />
          <Metric label="疏解時間" before={result.baseline_metrics.clearance_minutes} after={result.projected_metrics.clearance_minutes} unit=" 分" />
          <Metric label="危急路段" before={result.baseline_metrics.critical_segments} after={result.projected_metrics.critical_segments} />
        </div>
        <div className="sim-series" aria-label="二十分鐘飽和度趨勢">
          {result.series.map((p) => <i key={p.minute} title={`${p.minute} 分鐘：${p.focus_saturation}`} style={{ height: `${Math.max(12, p.focus_saturation * 70)}px` }}><span>{p.minute}</span></i>)}
        </div>
        {result.signal_plan && <div className="signal-plan-proof">
          <b>下一輪智慧號誌｜{result.signal_plan.cycle_seconds} 秒</b>
          {result.signal_plan.approaches.map((approach) => (
            <div key={approach.segment_id}>
              <span>{approach.name}</span><strong>{approach.next_green_seconds}s</strong>
              <small>需求 {approach.demand_score.toFixed(2)}｜安全下限 {approach.safety_minimum_green_seconds}s</small>
            </div>
          ))}
          <p>{result.signal_plan.formula}</p>
        </div>}
        <div className="sim-proof">規則式交通模型 v1｜未使用 LLM｜每項措施與假設皆可追溯</div>
      </div>}

      {a && b && <div className="ab-compare">
        <b>方案比較</b>
        <div><span>目標飽和度</span><strong>A {a.projected_metrics.focus_saturation}</strong><strong>B {b.projected_metrics.focus_saturation}</strong></div>
        <div><span>疏解時間</span><strong>A {a.projected_metrics.clearance_minutes} 分</strong><strong>B {b.projected_metrics.clearance_minutes} 分</strong></div>
      </div>}
    </div>
  );
}
