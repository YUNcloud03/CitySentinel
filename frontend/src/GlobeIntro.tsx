// 系統總覽 landing：純 Canvas 2D 線框地球（零依賴，取代 three.js 三件套）
// + motionsites 式字元進場與分段淡入。台北座標以 Signal Blue 脈動點標示。
import { useEffect, useRef, useState } from "react";

const BLUE = "0, 122, 252";
const TAIPEI = { lat: 25.03, lon: 121.56 };

function project(lat: number, lon: number, rotY: number, r: number) {
  const phi = (lat * Math.PI) / 180;
  const theta = (lon * Math.PI) / 180 + rotY;
  const x = r * Math.cos(phi) * Math.sin(theta);
  const y = -r * Math.sin(phi);
  const z = r * Math.cos(phi) * Math.cos(theta);
  return { x, y, z };
}

function GlobeCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let rot = 0;

    // 均勻散佈的球面點（Fibonacci sphere）
    const dots: { lat: number; lon: number }[] = [];
    const N = 420;
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2;
      const lat = (Math.asin(y) * 180) / Math.PI;
      const lon = ((i * 137.508) % 360) - 180;
      dots.push({ lat, lon });
    }

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2;
      const R = Math.min(w, h) * 0.36;
      rot += 0.0016;

      // 經線
      for (let lon = -180; lon < 180; lon += 30) {
        ctx.beginPath();
        let started = false;
        for (let lat = -90; lat <= 90; lat += 4) {
          const p = project(lat, lon, rot, R);
          if (p.z < 0) { started = false; continue; }
          if (!started) { ctx.moveTo(cx + p.x, cy + p.y); started = true; }
          else ctx.lineTo(cx + p.x, cy + p.y);
        }
        ctx.strokeStyle = `rgba(${BLUE}, 0.10)`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      // 緯線
      for (let lat = -60; lat <= 60; lat += 30) {
        ctx.beginPath();
        let started = false;
        for (let lon = -180; lon <= 180; lon += 4) {
          const p = project(lat, lon, rot, R);
          if (p.z < 0) { started = false; continue; }
          if (!started) { ctx.moveTo(cx + p.x, cy + p.y); started = true; }
          else ctx.lineTo(cx + p.x, cy + p.y);
        }
        ctx.strokeStyle = `rgba(${BLUE}, 0.10)`;
        ctx.stroke();
      }
      // 球面點
      for (const d of dots) {
        const p = project(d.lat, d.lon, rot, R);
        if (p.z < 0) continue;
        const depth = p.z / R; // 0..1，越前越亮
        ctx.beginPath();
        ctx.arc(cx + p.x, cy + p.y, 1.1, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(160, 170, 186, ${0.08 + depth * 0.22})`;
        ctx.fill();
      }
      // 台北訊號點（脈動）
      const tp = project(TAIPEI.lat, TAIPEI.lon, rot, R);
      if (tp.z > 0) {
        const t = (performance.now() % 1800) / 1800;
        ctx.beginPath();
        ctx.arc(cx + tp.x, cy + tp.y, 3 + t * 14, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${BLUE}, ${0.55 * (1 - t)})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(cx + tp.x, cy + tp.y, 3.2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${BLUE}, 0.95)`;
        ctx.fill();
        ctx.font = "600 11px 'DM Sans', 'Noto Sans TC', sans-serif";
        ctx.fillStyle = `rgba(${BLUE}, 0.9)`;
        ctx.fillText("TAIPEI · 信義計畫區", cx + tp.x + 12, cy + tp.y + 4);
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={ref} className="globe-canvas" style={{ width: "100%", height: "100%" }} />;
}

function AnimatedTitle({ lines }: { lines: string[] }) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setOn(true), 200);
    return () => clearTimeout(t);
  }, []);
  let idx = 0;
  return (
    <h1 className="overview-title">
      {lines.map((line, li) => (
        <span key={li} style={{ display: "block" }}>
          {[...line].map((ch, ci) => {
            const delay = idx++ * 30;
            return (
              <span key={ci} className={`char ${on ? "in" : ""}`}
                style={{ transitionDelay: `${delay}ms` }}>
                {ch === " " ? " " : ch}
              </span>
            );
          })}
        </span>
      ))}
    </h1>
  );
}

export default function GlobeIntro({ onEnter }: { onEnter: (page: "command" | "citizen") => void }) {
  return (
    <main className="overview-page">
      <GlobeCanvas />
      <div className="overview-content">
        <div className="overview-eyebrow fade-in" style={{ animationDelay: "100ms" }}>
          <span className="live-dot" /> CITY SENTINEL · AI COMMAND
        </div>
        <AnimatedTitle lines={["城市應變", "AI 智慧指揮中樞"]} />
        <p className="overview-sub fade-in" style={{ animationDelay: "800ms" }}>
          融合車流、電信人流與官方 SOP——自動感知異常、即時重規劃路網、
          可質疑的調度決策、多語疏散通報。確定性引擎判定，LLM 解釋與對話。
        </p>
        <div className="overview-ctas fade-in" style={{ animationDelay: "1200ms" }}>
          <button className="primary" onClick={() => onEnter("command")}>進入指揮中心 →</button>
          <button className="ghost-pill" onClick={() => onEnter("citizen")}>民眾端模擬</button>
        </div>
        <div className="overview-stats fade-in" style={{ animationDelay: "1400ms" }}>
          <div className="stat"><b>15</b><span>核心路段</span></div>
          <div className="stat"><b>9</b><span>基地台場站</span></div>
          <div className="stat"><b>7</b><span>SOP 條款</span></div>
          <div className="stat"><b>4</b><span>通報語言</span></div>
          <div className="stat"><b>&lt;60s</b><span>應變分析</span></div>
        </div>
      </div>
    </main>
  );
}
