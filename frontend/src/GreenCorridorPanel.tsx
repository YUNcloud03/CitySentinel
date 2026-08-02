import { useEffect, useState } from "react";
import { api, type GreenCorridorResult, type SimView } from "./api";

interface Props {
  view: SimView | null;
  result: GreenCorridorResult | null;
  onResult: (result: GreenCorridorResult | null) => void;
}

interface RoadOption {
  segment_id: string;
  name: string;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

const DEFAULT_ORIGIN = "RD_TPE_015";
const DEFAULT_DESTINATION = "RD_TPE_007";
const DEFAULT_BLOCKED = "RD_TPE_001";

export default function GreenCorridorPanel({ view, result, onResult }: Props) {
  const [network, setNetwork] = useState<RoadOption[]>([]);
  const [origin, setOrigin] = useState(DEFAULT_ORIGIN);
  const [destination, setDestination] = useState(DEFAULT_DESTINATION);
  const [blocked, setBlocked] = useState(DEFAULT_BLOCKED);
  const [vehicle, setVehicle] = useState<"Ambulance" | "FireEngine">("Ambulance");
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState("");
  const [messageLanguage, setMessageLanguage] = useState<"zh" | "en" | "ja" | "ko">("zh");
  const [elapsed, setElapsed] = useState(0);
  const routeSnapshotStale = Boolean(result && view?.sim_time && result.as_of !== view.sim_time);

  useEffect(() => {
    api.roadNetwork().then(setNetwork).catch(() => setError("無法載入道路資料"));
  }, []);

  useEffect(() => {
    if (!result || result.approval_status !== "APPROVED_FOR_SIMULATION" || result.runtime_state.completed) return;
    const timer = window.setInterval(() => {
      // 分頁不可見時暫停推進，切回來從原進度續跑（不跳秒）。
      if (document.hidden) return;
      setElapsed((current) => {
        const next = Math.min(current + 5, result.runtime_state.total_seconds + 1);
        void api.greenCorridorState(result.scenario_id, next)
          .then((runtime_state) => onResult({ ...result, runtime_state }))
          .catch(() => setError("無法更新救護車逐路口進度"));
        return next;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [result?.scenario_id, result?.approval_status, result?.runtime_state.completed]);

  const run = async () => {
    setLoading(true);
    setError("");
    setElapsed(0);
    try {
      const next = await api.greenCorridor({
        at: view?.sim_time ?? "2026-05-20 22:00",
        origin_segment_id: origin,
        destination_segment_id: destination,
        vehicle_type: vehicle,
        blocked_segment_ids: blocked ? [blocked] : [],
      });
      onResult(next);
    } catch (caught: unknown) {
      setError(errorMessage(caught, "救援走廊計算失敗"));
      onResult(null);
    } finally {
      setLoading(false);
    }
  };

  const approve = async () => {
    if (!result) return;
    setApproving(true);
    setError("");
    try {
      setElapsed(0);
      onResult(await api.approveGreenCorridor(result.scenario_id));
    } catch (caught: unknown) {
      setError(errorMessage(caught, "核准失敗"));
    } finally {
      setApproving(false);
    }
  };

  return (
    <div className="green-corridor-panel">
      <section className="gc-card gc-setup-card">
        <div className="gc-head">
          <div><span className="eyebrow">緊急救援優先</span><h3>綠色救援走廊</h3></div>
          <span className="chip green">需人工核准</span>
        </div>
        <p className="gc-intro">依主辦方路網、即時車速與官方號誌點位，計算救援路徑及號誌預控時序。</p>

        <div className="gc-fields">
          <label>救援車輛
            <select value={vehicle} onChange={(event) => setVehicle(event.target.value as "Ambulance" | "FireEngine")}>
              <option value="Ambulance">救護車</option>
              <option value="FireEngine">消防車</option>
            </select>
          </label>
          <label>起點路段
            <select value={origin} onChange={(event) => setOrigin(event.target.value)}>
              {network.map((road) => <option key={road.segment_id} value={road.segment_id}>{road.name}</option>)}
            </select>
          </label>
          <label>目的路段
            <select value={destination} onChange={(event) => setDestination(event.target.value)}>
              {network.map((road) => <option key={road.segment_id} value={road.segment_id}>{road.name}</option>)}
            </select>
          </label>
          <label>前方封閉／事故
            <select value={blocked} onChange={(event) => setBlocked(event.target.value)}>
              <option value="">無封閉路段</option>
              {network.filter((road) => road.segment_id !== origin && road.segment_id !== destination)
                .map((road) => <option key={road.segment_id} value={road.segment_id}>{road.name}</option>)}
            </select>
          </label>
        </div>

        <button className="primary gc-run" onClick={run} disabled={loading || origin === destination}>
          {loading ? "正在協調道路與號誌…" : "建立綠色救援走廊"}
        </button>
        {origin === destination && <p className="warn small">起點與目的路段不可相同。</p>}
        {error && <p className="warn small">{error}</p>}
      </section>

      {result && (
        <div className="gc-result" aria-live="polite">
          <div className={`gc-status ${result.approval_status === "APPROVED_FOR_SIMULATION" ? "approved" : ""}`}>
            <i />{result.approval_status === "APPROVED_FOR_SIMULATION"
              ? `模擬走廊已啟動｜${result.approved_by ?? "指揮官"}核准`
              : "走廊方案已建立｜等待指揮官核准"}
          </div>
          <section className="gc-card gc-summary-card">
            <div className="gc-card-title"><b>救援效益摘要</b><span>路線計算結果</span></div>
            <div className="gc-eta">
              <div><span>原始 ETA</span><b>{result.eta.before_minutes}</b><small>分鐘</small></div>
              <div className="gc-arrow">→</div>
              <div className="improved"><span>走廊 ETA</span><b>{result.eta.after_minutes}</b><small>分鐘</small></div>
              <div className="gc-save">節省 {result.eta.saved_minutes} 分鐘｜改善 {result.eta.improvement_pct}%</div>
            </div>

            <div className="gc-kpis">
              <span><b>{result.route_segment_ids.length}</b> 路段</span>
              <span><b>{result.signal_actions.length}</b> 號誌預控</span>
              <span><b>{result.dispatch_recommendation.requested_units}</b> 警力建議</span>
            </div>

            <div className={`gc-traffic-snapshot ${routeSnapshotStale ? "stale" : ""}`}>
              <span>路線依據：{result.evidence.traffic_snapshot} 車流快照</span>
              <b>{result.evidence.traffic_source === "incident_projection" ? "含事件路況投影" : "主辦方路況"}</b>
              {routeSnapshotStale && <button type="button" onClick={run} disabled={loading}>
                依目前 {view?.sim_time} 路況重規劃
              </button>}
            </div>
          </section>

          {result.approval_status === "APPROVED_FOR_SIMULATION" && <section className="gc-card gc-runtime">
            <div className="gc-card-title"><b>{result.runtime_state.completed ? "救援車已通過走廊" : "執行進度｜逐路口滾動優先"}</b><span>模擬狀態</span></div>
            <span>{result.runtime_state.current_intersection_id
              ? `目前路口 ${result.runtime_state.current_intersection_id}` : "等待下一路口預控"}</span>
            <div className="gc-vehicle-progress" aria-label={`救護車路線進度 ${result.runtime_state.vehicle_progress_pct}%`}>
              <i style={{ width: `${result.runtime_state.vehicle_progress_pct}%` }} />
            </div>
            <small>🚑 進度 {result.runtime_state.vehicle_progress_pct}%｜下一路口 {result.runtime_state.next_intersection_id ?? "目的地"}</small>
            <small>{result.runtime_state.elapsed_seconds}s / {result.runtime_state.total_seconds}s｜同時最多一個路口優先｜非 GPS</small>
          </section>}

          {result.approval_status === "READY_FOR_APPROVAL" ? (
            <button className="gc-approve" onClick={approve} disabled={approving}>
              {approving ? "正在寫入核准紀錄…" : "核准並啟動模擬走廊"}
            </button>
          ) : (
            <div className="gc-approved-proof">✓ 核准紀錄已寫入決策鏈；正式號誌仍未被修改</div>
          )}

          <section className="gc-card gc-route-card">
            <div className="gc-card-title"><b>救援路線明細</b><span>{result.route_details.length} 個路段</span></div>
            <div className="gc-route" aria-label="救援路線">
              {result.route_details.map((road, index) => (
                <div key={road.segment_id}>
                  <i>{index + 1}</i><span><b>{road.name}</b>
                    <small>{road.baseline_speed_kmh} → {road.corridor_speed_kmh} km/h｜飽和 {road.saturation_score.toFixed(2)}｜路況成本 {road.route_cost_seconds} 秒｜{road.signal_count} 號誌</small>
                  </span>
                </div>
              ))}
            </div>
          </section>

          <div className="gc-message">
            <div className="gc-lang" role="group" aria-label="推播語言">
              {(["zh", "en", "ja", "ko"] as const).map((language) => (
                <button key={language} className={messageLanguage === language ? "active" : ""}
                  onClick={() => setMessageLanguage(language)}>{language.toUpperCase()}</button>
              ))}
            </div>
            <p>{result.messages[messageLanguage]}</p>
          </div>

          <details className="gc-proof">
            <summary>檢視計算與限制</summary>
            <p>{result.eta.formula}</p>
            <p>{result.limitations}</p>
            <code>{result.model}</code>
          </details>
        </div>
      )}
    </div>
  );
}
