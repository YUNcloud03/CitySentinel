// CitySentinel 決賽簡報（6 分鐘版）— 中華電信「城市應變分析 AI Agent」
// 依官方決賽交付規定：簡報須涵蓋 解題方向 / AI 技術應用 / 數據資料應用 / 使用者流程 / AWS 架構圖
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5

const BG = "0E1012", CARD = "15171B", CARD2 = "1C1F24", BORDER = "23262D";
const BLUE = "007AFC", BLUE_DK = "0A3560";
const RED = "E5484D", AMBER = "F5A623", GREEN = "2FBF71";
const WHITE = "FFFFFF", FOG = "A0AABA", SLATE = "566171";
const H = "Microsoft JhengHei", B = "Microsoft JhengHei", M = "Consolas";

const S = () => { const s = pres.addSlide(); s.background = { color: BG }; return s; };
const eyebrow = (s, t, y = 0.4) =>
  s.addText(t, { x: 0.6, y, w: 11, h: 0.24, fontSize: 10.5, bold: true, color: SLATE, charSpacing: 2, fontFace: B, margin: 0 });
const title = (s, t, y = 0.68, size = 30) =>
  s.addText(t, { x: 0.6, y, w: 12.1, h: 0.56, fontSize: size, bold: true, color: WHITE, fontFace: H, margin: 0 });
const sub = (s, t, y) =>
  s.addText(t, { x: 0.6, y, w: 12.1, h: 0.3, fontSize: 13, color: FOG, fontFace: B, margin: 0 });
const card = (s, x, y, w, h, fill = CARD, line = BORDER) =>
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.09, fill: { color: fill }, line: { color: line, width: 1 } });
const txt = (s, t, o) => s.addText(t, Object.assign({ fontFace: B, margin: 0, color: WHITE }, o));
const foot = (s, t) =>
  s.addText(t, { x: 0.6, y: 6.95, w: 12.1, h: 0.26, fontSize: 9.5, color: SLATE, fontFace: B, margin: 0 });
const tag = (s, x, y, t, c) => {
  s.addShape(pres.ShapeType.roundRect, { x, y, w: 1.5, h: 0.28, rectRadius: 0.14, fill: { color: BG }, line: { color: c, width: 1 } });
  s.addText(t, { x, y, w: 1.5, h: 0.28, fontSize: 9.5, bold: true, color: c, align: "center", valign: "middle", fontFace: B, margin: 0 });
};

/* ===== 1. 封面 — 8 秒 ===== */
{
  const s = S();
  [[3.0, "0A2942"], [2.3, "0C3557"], [1.65, "0E4373"], [1.05, "10528F"]].forEach(([r, c]) =>
    s.addShape(pres.ShapeType.ellipse, { x: 10.3 - r, y: 3.8 - r, w: r * 2, h: r * 2, fill: { color: BG }, line: { color: c, width: 1 } }));
  s.addShape(pres.ShapeType.ellipse, { x: 10.18, y: 3.68, w: 0.24, h: 0.24, fill: { color: BLUE }, line: { color: BLUE, width: 1 } });
  txt(s, "臺北 · 信義計畫區", { x: 10.6, y: 3.67, w: 2.4, h: 0.26, fontSize: 10, color: BLUE });

  txt(s, "2026 雲湧智生 · 臺灣生成式 AI 應用黑客松｜中華電信命題：城市應變分析 AI Agent",
    { x: 0.85, y: 0.9, w: 9, h: 0.3, fontSize: 11, bold: true, color: SLATE, charSpacing: 1.5 });
  txt(s, "CitySentinel", { x: 0.85, y: 1.9, w: 9, h: 1.15, fontSize: 62, bold: true, fontFace: H });
  txt(s, "城市應變 AI 智慧指揮中樞", { x: 0.85, y: 3.05, w: 9, h: 0.5, fontSize: 24, color: FOG });
  s.addShape(pres.ShapeType.rect, { x: 0.85, y: 3.95, w: 0.05, h: 1.05, fill: { color: BLUE }, line: { color: BLUE, width: 0 } });
  txt(s, "AI 不下命令，", { x: 1.15, y: 3.95, w: 8, h: 0.5, fontSize: 21, bold: true, color: WHITE });
  txt(s, "AI 讓指揮官在 90 秒內做出敢負責的決定。", { x: 1.15, y: 4.48, w: 8, h: 0.5, fontSize: 21, bold: true, color: BLUE });
  foot(s, "決賽簡報 · 6 分鐘｜交付：提案簡報 · Live Demo 部署網址與錄影 · GitHub 原始碼");
  s.addNotes("【0:00–0:08】自我介紹＋一句主張。不要念封面，只說：我們做的是城市應變 AI 指揮中樞，核心主張是 AI 不下命令，AI 讓指揮官在 90 秒內做出敢負責的決定。");
}

/* ===== 2. 解題方向 — 25 秒（官方必要章節 ①）===== */
{
  const s = S();
  eyebrow(s, "① 解題方向");
  title(s, "問題不在資料不足，在決策沒有依據");
  const gaps = [
    ["資料看得到，但不知道會怎樣", "監控畫面只呈現此刻，沒有事態推演"],
    ["方案下得出，但不知道副作用", "疏導了這條，壅塞轉去哪裡沒人算"],
    ["決定做了，但說不清依據", "事後檢討無法還原當時的判斷鏈"]
  ];
  gaps.forEach(([t, d], i) => {
    const y = 1.62 + i * 0.92;
    card(s, 0.6, y, 6.0, 0.78);
    s.addShape(pres.ShapeType.rect, { x: 0.6, y, w: 0.05, h: 0.78, fill: { color: RED }, line: { width: 0 } });
    txt(s, t, { x: 0.85, y: y + 0.11, w: 5.6, h: 0.28, fontSize: 14, bold: true });
    txt(s, d, { x: 0.85, y: y + 0.42, w: 5.6, h: 0.26, fontSize: 11, color: FOG });
  });

  card(s, 7.0, 1.62, 5.7, 2.68, CARD2, BLUE_DK);
  txt(s, "我們的職責切分", { x: 7.3, y: 1.82, w: 5.1, h: 0.3, fontSize: 15, bold: true, color: BLUE });
  const split = [
    ["確定性引擎", "判定與計算 — 規則、路線、ETE、調度"],
    ["LLM", "只做模糊理解與文字生成，不做判定"],
    ["狀態機", "控制流程，11 步全程留痕"],
    ["指揮官", "保有最終決策權，發布前必經核准"]
  ];
  split.forEach(([k, v], i) => {
    const y = 2.25 + i * 0.5;
    txt(s, k, { x: 7.3, y, w: 1.7, h: 0.28, fontSize: 12.5, bold: true, color: WHITE });
    txt(s, v, { x: 9.05, y, w: 3.5, h: 0.28, fontSize: 11, color: FOG });
  });
  card(s, 0.6, 4.55, 12.1, 0.85, CARD2, BLUE_DK);
  txt(s, "為什麼這樣切", { x: 0.9, y: 4.72, w: 2.2, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  txt(s, "因為要能被稽核。凡是會影響行動的數字，都不能出自機率模型 — 這是整套系統所有設計的唯一理由。",
    { x: 2.9, y: 4.72, w: 9.6, h: 0.5, fontSize: 14, bold: true });
  foot(s, "官方命題：打造具「自動感知」與「互動決策」能力的智慧交通指揮系統");
  s.addNotes("【0:08–0:33】快速念三個斷點，強調三個都不是資料問題是決策問題。右邊職責切分只講一句：確定性引擎判定、LLM 只生文、人保有決策權。最後那句「會影響行動的數字不能出自機率模型」要停頓一下，這是全場的地基。");
}

/* ===== 3. 官方五大模組對照 — 20 秒 ===== */
{
  const s = S();
  eyebrow(s, "命題核心功能模組 × 本系統實作");
  title(s, "官方要求的五個模組，全部落地");
  const rows = [
    ["1", "動態時序監測儀表板", "時間軸逐格重播 · 六條 SOP 規則自動判定 · 命中即彈窗，門檻由程式算、摘要由 LLM 生"],
    ["2", "突發事件注入與處置", "事件注入介面 · 端到端 60 秒內完成路網重規劃 · 重規劃為程式運算、導引文字由 LLM 生"],
    ["3", "對話式策略諮詢顧問", "Tool-Calling Agent 七個唯讀工具 · What-if 沙盒 · SOP 邏輯驗證由 LLM 判斷"],
    ["4", "AI 決策推理與解釋鏈", "分級判定附數據佐證 · 排除替代道路附理由代碼 · ETE 公式攤開，LLM 僅解釋結果"],
    ["5", "多語化全通路通報", "漫遊比率 ≥ 30% 自動偵測 · 中英日韓四語告警 · 民眾端依裝置語言自動切換"]
  ];
  rows.forEach(([n, mod, impl], i) => {
    const y = 1.6 + i * 0.98;
    card(s, 0.6, y, 12.1, 0.84);
    s.addShape(pres.ShapeType.roundRect, { x: 0.82, y: y + 0.26, w: 0.32, h: 0.32, rectRadius: 0.08, fill: { color: BLUE }, line: { width: 0 } });
    txt(s, n, { x: 0.82, y: y + 0.26, w: 0.32, h: 0.32, fontSize: 12, bold: true, align: "center", valign: "middle" });
    txt(s, mod, { x: 1.32, y: y + 0.14, w: 3.1, h: 0.3, fontSize: 14, bold: true });
    txt(s, impl, { x: 1.32, y: y + 0.46, w: 9.3, h: 0.3, fontSize: 11, color: FOG });
    tag(s, 10.95, y + 0.28, "已完成", GREEN);
  });
  foot(s, "五個模組皆有自動化測試覆蓋：後端 137 項、前端 10 項，全數通過");
  s.addNotes("【0:33–0:53】這頁是給評審對表的。不要逐條念，說：官方要的五個模組我們全部做完，而且每一個都有測試守著。手指快速掃過五列，停在右邊的「已完成」標籤。");
}

/* ===== 4. Demo ①：動態時序監測 — 40 秒 ===== */
{
  const s = S();
  eyebrow(s, "Live Demo ① · 核心模組 1");
  title(s, "時間軸一拉，系統自己就叫了");
  sub(s, "門檻判定由程式運算，摘要由 LLM 生成，整個過程無需人工介入", 1.3);

  card(s, 0.6, 1.85, 5.9, 2.5);
  txt(s, "程式負責的部分", { x: 0.9, y: 2.05, w: 5.3, h: 0.3, fontSize: 14, bold: true, color: BLUE });
  const prog = [
    "飽和度 ≥ 0.85 → B 級壅塞；≥ 0.95 → A 級壅塞",
    "捷運出站 5 分鐘增幅 ≥ 30% 且人數 ≥ 25,000",
    "大巨蛋人數 ≥ 30,000；散場判定 5 分鐘 ≤ −20%",
    "漫遊比率 ≥ 30% 觸發多語通報",
    "六條規則在每一格快照上重新判定"
  ];
  prog.forEach((t, i) => txt(s, "· " + t, { x: 0.9, y: 2.45 + i * 0.34, w: 5.3, h: 0.3, fontSize: 11, color: FOG }));

  card(s, 6.8, 1.85, 5.9, 2.5);
  txt(s, "LLM 負責的部分", { x: 7.1, y: 2.05, w: 5.3, h: 0.3, fontSize: 14, bold: true, color: AMBER });
  txt(s, "把已經算出來的判定結果，寫成指揮官讀得懂的一段預警摘要。", { x: 7.1, y: 2.45, w: 5.3, h: 0.5, fontSize: 11, color: FOG });
  card(s, 7.1, 3.0, 5.3, 1.15, BG, BORDER);
  txt(s, "「信義路二段飽和度 0.91，已達 B 級壅塞門檻，預估 20 分鐘內延伸至南京東路。建議提前啟動替代道路引導。」",
    { x: 7.3, y: 3.15, w: 4.9, h: 0.9, fontSize: 11, color: WHITE, italic: true });

  card(s, 0.6, 4.6, 12.1, 0.85, CARD2, BLUE_DK);
  txt(s, "現場操作", { x: 0.9, y: 4.78, w: 1.6, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  txt(s, "拉時間軸 → 飽和度爬過 0.85 → 警報自動彈出 → 點開看到判定依據與原始數據列，全程沒有人按任何按鈕。",
    { x: 2.5, y: 4.78, w: 10, h: 0.5, fontSize: 13.5 });
  foot(s, "對應評分：技術可行性 35%（分級判定是否符合 SOP 條件）");
  s.addNotes("【0:53–1:33】切到監控頁實機操作。邊拉時間軸邊說：門檻是程式算的、摘要是 LLM 寫的。彈窗跳出來後點開一次判定依據，讓評審看到原始數據列。這裡不要講太多，讓畫面說話。");
}

/* ===== 5. Demo ②：事件注入 → 路網重規劃 — 55 秒（錢在這）===== */
{
  const s = S();
  eyebrow(s, "Live Demo ② · 核心模組 2 · 全場核心");
  title(s, "注入事故 60 秒內，重規劃完成");
  sub(s, "路網重規劃為程式運算，導引文字由 LLM 生成 — 而且我們多做了一件事：事態會隨時間惡化", 1.3);

  const steps = [
    ["T+0", "事件注入", "信義路二段路面塌陷 · Critical · 引用 SOP 第 2 條"],
    ["T+0", "候選篩選", "排除容量 < 1000 vph 與非直接相鄰路段，附理由代碼"],
    ["T+0", "路線產出", "上游最低飽和度者為主要路線，其餘為次要"],
    ["T+30", "事態惡化", "改道負載實際加到替代道路，路線自己換了一條"]
  ];
  steps.forEach(([t, k, v], i) => {
    const y = 1.9 + i * 0.72;
    card(s, 0.6, y, 7.5, 0.62);
    txt(s, t, { x: 0.8, y: y + 0.17, w: 0.75, h: 0.28, fontSize: 11, bold: true, color: BLUE, fontFace: M });
    txt(s, k, { x: 1.6, y: y + 0.16, w: 1.55, h: 0.3, fontSize: 12.5, bold: true });
    txt(s, v, { x: 3.2, y: y + 0.17, w: 4.75, h: 0.28, fontSize: 10.5, color: FOG });
  });

  card(s, 8.4, 1.9, 4.3, 2.06, CARD2, BLUE_DK);
  txt(s, "超出命題要求的部分", { x: 8.65, y: 2.06, w: 3.8, h: 0.28, fontSize: 12.5, bold: true, color: BLUE });
  ["事件影響隨時間爬升（30 分鐘 0.55→1.0）", "改道車流真的壓上替代道路", "在壓力測試後的路網上重算路線"]
    .forEach((t, i) => txt(s, "· " + t, { x: 8.65, y: 2.45 + i * 0.42, w: 3.8, h: 0.4, fontSize: 10.5, color: FOG }));

  card(s, 8.4, 4.1, 4.3, 1.28, CARD, AMBER);
  txt(s, "決策沙盒會說實話", { x: 8.65, y: 4.26, w: 3.8, h: 0.28, fontSize: 12.5, bold: true, color: AMBER });
  txt(s, "「需調整：目標路段改善，但壅塞可能轉移到其他道路。」", { x: 8.65, y: 4.6, w: 3.8, h: 0.62, fontSize: 11.5, color: WHITE, bold: true });

  card(s, 0.6, 4.78, 7.5, 0.6, CARD2, BLUE_DK);
  txt(s, "端到端延遲實測 · 事件注入 → 畫面更新完成", { x: 0.85, y: 4.94, w: 4.6, h: 0.3, fontSize: 11.5, color: FOG });
  txt(s, "遠低於 60 秒上限", { x: 5.6, y: 4.9, w: 2.3, h: 0.36, fontSize: 15, bold: true, color: GREEN });
  foot(s, "對應評分：技術可行性 35%（SOP 引用正確 · 替代路徑避開事故路段與容量有限路段）");
  s.addNotes("【1:33–2:28】全場最重要的 55 秒。先注入事故，看 60 秒內路線出來；接著拉時間軸到 T+30，讓評審看到替代道路被改道車流染紅、建議路線自己改變。最後開決策沙盒，刻意跑出「壅塞轉移」那句判定 — 停頓，說：市府最怕只報喜的系統，我們的系統會主動承認自己方案的副作用。");
}

/* ===== 6. 解釋鏈 — 35 秒 ===== */
{
  const s = S();
  eyebrow(s, "核心模組 4 · AI 決策推理與解釋鏈");
  title(s, "每個數字旁邊，都附著它的公式");
  card(s, 0.6, 1.5, 6.0, 1.75);
  txt(s, "為什麼判 A 級", { x: 0.85, y: 1.68, w: 5.5, h: 0.3, fontSize: 13.5, bold: true, color: BLUE });
  txt(s, "飽和度 0.96 ≥ 0.95 → SOP 第 1 條 A 級", { x: 0.85, y: 2.05, w: 5.5, h: 0.28, fontSize: 12.5, bold: true, color: WHITE });
  txt(s, "佐證資料列：RD_TPE_002 · 18:30 · 車速 8.4 km/h · 車流 2,140", { x: 0.85, y: 2.42, w: 5.5, h: 0.28, fontSize: 10.5, color: FOG });
  txt(s, "規則歸因分三類：事件造成 / 背景既有 / 計算用", { x: 0.85, y: 2.75, w: 5.5, h: 0.28, fontSize: 10.5, color: FOG });

  card(s, 6.8, 1.5, 5.9, 1.75);
  txt(s, "為什麼排除那條替代道路", { x: 7.05, y: 1.68, w: 5.4, h: 0.3, fontSize: 13.5, bold: true, color: BLUE });
  [["CAPACITY_BELOW_1000", "承載量低於 1000 vph"],
   ["NOT_DIRECT_INTERSECTION", "非事故路口直接相鄰"],
   ["UNKNOWN_SEGMENT", "路網中查無此路段"]].forEach(([c, d], i) => {
    txt(s, c, { x: 7.05, y: 2.05 + i * 0.36, w: 2.9, h: 0.28, fontSize: 10, fontFace: M, color: AMBER });
    txt(s, d, { x: 10.0, y: 2.05 + i * 0.36, w: 2.5, h: 0.28, fontSize: 10, color: FOG });
  });

  card(s, 0.6, 3.5, 12.1, 1.9, CARD2, BLUE_DK);
  txt(s, "ETE 預估交通恢復時間 — 公式全部攤開，LLM 只負責把它讀成人話", { x: 0.9, y: 3.7, w: 11.5, h: 0.3, fontSize: 13.5, bold: true, color: BLUE });
  txt(s, "基礎清除時間(Critical) 60 分　＋　壅塞懲罰 max(0, (平均飽和度 − 0.5) × 60)", { x: 0.9, y: 4.12, w: 11.5, h: 0.32, fontSize: 14, color: WHITE });
  s.addText([
    { text: "= 60 + max(0, (0.998 − 0.5) × 60)  =  90 ", options: { fontFace: M, bold: true } },
    { text: "分鐘", options: { fontFace: B, bold: true } }
  ], { x: 0.9, y: 4.55, w: 6.5, h: 0.4, fontSize: 17, color: GREEN, margin: 0 });
  txt(s, "所有引擎常數可經 /api/provenance 查詢，連同資料集 SHA256 一併公開", { x: 7.6, y: 4.62, w: 4.9, h: 0.3, fontSize: 10.5, color: FOG });
  foot(s, "對應評分：技術可行性 35%｜白盒承諾：判定、排除、計算三者全部可追溯");
  s.addNotes("【2:28–3:03】三塊各講一句：為什麼判 A 級（附原始資料列）、為什麼排除那條路（附理由代碼）、ETE 怎麼算出 90 分鐘。重點台詞：LLM 在這一頁只做一件事，把公式讀成人話，它碰不到任何一個數字。");
}

/* ===== 7. Demo ③：對話式顧問 — 45 秒 ===== */
{
  const s = S();
  eyebrow(s, "Live Demo ③ · 核心模組 3");
  title(s, "請評審現場出題");
  sub(s, "Agent 自主決定要查哪些工具，答案裡的 SOP 條號來自呼叫軌跡，不是它自己說的", 1.3);

  card(s, 0.6, 1.85, 6.2, 3.0);
  txt(s, "示範提問", { x: 0.85, y: 2.03, w: 5.7, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  card(s, 0.85, 2.4, 5.7, 0.62, BG, BLUE_DK);
  txt(s, "「若 BL17 人數增至 40,000 人，該啟動什麼？」", { x: 1.05, y: 2.55, w: 5.3, h: 0.32, fontSize: 12, bold: true });
  txt(s, "工具呼叫軌跡（畫面上會逐步展開）", { x: 0.85, y: 3.15, w: 5.7, h: 0.28, fontSize: 11, color: FOG });
  [["get_crowd", " → 讀取 BL17 當前人流"],
   ["run_what_if", " → 沙盒代入 40,000 人"],
   ["get_sop", " → 檢索命中的 SOP 條款"]].forEach(([tool, desc], i) =>
    s.addText([
      { text: "· ", options: { fontFace: B } },
      { text: tool, options: { fontFace: M, bold: true } },
      { text: desc, options: { fontFace: B } }
    ], { x: 0.85, y: 3.5 + i * 0.35, w: 5.7, h: 0.3, fontSize: 10.5, color: AMBER, margin: 0 }));
  txt(s, "回答：命中 SOP 第 3 條 → 啟動過站不停與接駁分流", { x: 0.85, y: 4.55, w: 5.7, h: 0.28, fontSize: 11.5, bold: true, color: GREEN });

  card(s, 7.1, 1.85, 5.6, 1.42, CARD2, BLUE_DK);
  txt(s, "為什麼這是真的 Agent", { x: 7.35, y: 2.02, w: 5.1, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  txt(s, "七個唯讀工具 · 迴圈上限五輪 · 由 LLM 自主決定呼叫順序，引用條號從軌跡推導而非採信自述",
    { x: 7.35, y: 2.4, w: 5.1, h: 0.7, fontSize: 11, color: FOG });

  card(s, 7.1, 3.45, 5.6, 1.4, CARD, RED);
  txt(s, "越權在物理上不可能", { x: 7.35, y: 3.62, w: 5.1, h: 0.3, fontSize: 13, bold: true, color: RED });
  txt(s, "工具清單裡不存在「發布」「派遣」「核准」— 這是物理邊界，不是靠提示詞約束。",
    { x: 7.35, y: 4.0, w: 5.1, h: 0.7, fontSize: 11, color: FOG });

  card(s, 0.6, 5.05, 12.1, 0.72, CARD2, BLUE_DK);
  txt(s, "智慧指揮官特質", { x: 0.9, y: 5.2, w: 2.3, h: 0.3, fontSize: 12.5, bold: true, color: BLUE });
  txt(s, "不是等你問才答 — 資料一觸及門檻，系統主動彈出預警；顧問對話是補充，不是入口。", { x: 3.2, y: 5.2, w: 9.3, h: 0.4, fontSize: 12.5 });
  foot(s, "對應評分：主題切合度 35%（互動問答能否正確解讀提問並精準引用 SOP 條款）");
  s.addNotes("【3:03–3:48】真的邀請評審出題，這是 35% 主題切合度的直球。若現場網路不穩，改用預設題目並說明：LLM 不可用時會自動退回確定性回答，Demo 不會死 — 這本身也是賣點。強調引用條號來自工具軌跡。");
}

/* ===== 8. 多語通報 — 25 秒 ===== */
{
  const s = S();
  eyebrow(s, "核心模組 5 · 多語化全通路通報");
  title(s, "漫遊比率一超標，四語告警同時就緒");
  card(s, 0.6, 1.6, 3.6, 1.5);
  txt(s, "自動偵測", { x: 0.85, y: 1.78, w: 3.1, h: 0.28, fontSize: 12.5, bold: true, color: BLUE });
  txt(s, "漫遊用戶數 ÷ 該站點總容量 ≥ 30%", { x: 0.85, y: 2.14, w: 3.1, h: 0.5, fontSize: 11, color: FOG });
  txt(s, "由程式判定，非 LLM", { x: 0.85, y: 2.7, w: 3.1, h: 0.28, fontSize: 10.5, color: SLATE });

  ["中文", "English", "日本語", "한국어"].forEach((l, i) => {
    const x = 4.5 + i * 2.1;
    card(s, x, 1.6, 1.9, 1.5, CARD2, BLUE_DK);
    txt(s, l, { x, y: 1.85, w: 1.9, h: 0.3, fontSize: 14, bold: true, align: "center" });
    txt(s, "LLM 生成", { x, y: 2.25, w: 1.9, h: 0.26, fontSize: 10, color: FOG, align: "center" });
    txt(s, "數字不變性檢查", { x, y: 2.55, w: 1.9, h: 0.26, fontSize: 9.5, color: GREEN, align: "center" });
  });

  card(s, 0.6, 3.35, 6.0, 1.9);
  txt(s, "民眾端：像地震告警一樣自動跳出", { x: 0.85, y: 3.55, w: 5.5, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  txt(s, "依手機系統語言自動切換對應語言，不需要民眾自己選；疏散範圍內的門號才會收到。",
    { x: 0.85, y: 3.92, w: 5.5, h: 0.7, fontSize: 11, color: FOG });
  txt(s, "外籍旅客與觀光客不會因為看不懂而錯過疏散指示。", { x: 0.85, y: 4.68, w: 5.5, h: 0.35, fontSize: 11.5, bold: true, color: WHITE });

  card(s, 6.9, 3.35, 5.8, 1.9, CARD2, BLUE_DK);
  txt(s, "發布必經人工核准", { x: 7.15, y: 3.55, w: 5.3, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  txt(s, "草稿 → 待審 → 核准 → 派送 → 送達確認 / 失敗 → 重試", { x: 7.15, y: 3.92, w: 5.3, h: 0.32, fontSize: 11.5, color: WHITE });
  txt(s, "LLM 可以草擬告警，但沒有任何路徑可以把它自己發出去。派送失敗會自動重試，並在畫面上留下送達狀態。",
    { x: 7.15, y: 4.35, w: 5.3, h: 0.75, fontSize: 11, color: FOG });
  foot(s, "對應評分：商業應用性 10%（多國語言 · 訊息完整 · 可讀性）＋ 加分 5%（中英以外語言）");
  s.addNotes("【3:48–4:13】快速帶過。重點兩句：一是四語由 LLM 生成但有數字不變性檢查，二是民眾端依裝置語言自動切換。最後強調發布必經核准。");
}

/* ===== 9. AI 技術應用 — 25 秒（官方必要章節 ②）===== */
{
  const s = S();
  eyebrow(s, "② AI 技術應用");
  title(s, "讓 LLM 只做它不會出錯的事");
  const cols = [
    ["交給 LLM", GREEN, ["模糊語意理解（自然語言 What-if）", "預警摘要與導引文字生成", "多語告警翻譯", "解釋已算出的判定與公式"]],
    ["絕不交給 LLM", RED, ["SOP 分級與門檻判定", "替代路線選擇與排除", "ETE 數值計算", "資源調度與發布動作"]]
  ];
  cols.forEach(([t, c, items], i) => {
    const x = 0.6 + i * 6.25;
    card(s, x, 1.55, 5.85, 2.5, CARD, i === 0 ? BORDER : RED);
    txt(s, t, { x: x + 0.25, y: 1.73, w: 5.3, h: 0.3, fontSize: 14, bold: true, color: c });
    items.forEach((it, j) => txt(s, "· " + it, { x: x + 0.25, y: 2.15 + j * 0.42, w: 5.3, h: 0.35, fontSize: 11.5, color: FOG }));
  });

  card(s, 0.6, 4.3, 12.1, 1.95, CARD2, BLUE_DK);
  txt(s, "三道防幻覺護欄", { x: 0.9, y: 4.48, w: 3, h: 0.3, fontSize: 13.5, bold: true, color: BLUE });
  const guards = [
    ["必含字串檢查", "生成文字若未原樣包含路名、ETE 數字、時間戳，直接退回確定性樣板"],
    ["Schema 驗證", "後端結構化輸出經 JSON Schema 驗證，前端再經 Zod 驗證才進入 UI"],
    ["工具允許清單", "Agent 只有唯讀工具，寫入類工具在程式中根本不存在"]
  ];
  guards.forEach(([k, v], i) => {
    const y = 4.88 + i * 0.42;
    txt(s, k, { x: 0.9, y, w: 2.2, h: 0.3, fontSize: 11.5, bold: true, color: WHITE });
    txt(s, v, { x: 3.2, y, w: 9.3, h: 0.3, fontSize: 11, color: FOG });
  });
  foot(s, "模型可替換：Amazon Bedrock（Claude）為主 · 相容 API 為備援 · 兩者皆不可用時退回確定性樣板，Demo 不中斷");
  s.addNotes("【4:13–4:38】左右兩欄對比念得快一點，重點是右邊那欄「絕不交給 LLM」。三道護欄只講第一道：如果 LLM 改了數字，我們的程式會抓到並退回樣板。");
}

/* ===== 10. 數據資料應用 — 20 秒（官方必要章節 ③）===== */
{
  const s = S();
  eyebrow(s, "③ 數據資料應用");
  title(s, "五份官方資料，全部用上且公開雜湊");
  const ds = [
    ["city_traffic_flow.csv", "核心路段即時車速、車數、飽和度 → 壅塞分級與 ETE"],
    ["signaling_crowd_density.csv", "電信用戶數與漫遊比率 → 人流異常與多語通報觸發"],
    ["road_network_geometry.json", "路段連結、承載容量、替代路線 → 路網重規劃"],
    ["emergency_traffic_sop.txt", "官方交通應變指引 → 六條規則引擎與條款引用"],
    ["live_incidents.json", "Demo 當晚突發災情 → 事件注入與處置流程"]
  ];
  ds.forEach(([f, u], i) => {
    const y = 1.5 + i * 0.66;
    card(s, 0.6, y, 7.9, 0.56);
    txt(s, f, { x: 0.82, y: y + 0.15, w: 3.1, h: 0.28, fontSize: 10.5, fontFace: M, color: BLUE });
    txt(s, u, { x: 4.0, y: y + 0.15, w: 4.35, h: 0.28, fontSize: 10.5, color: FOG });
  });

  card(s, 8.8, 1.5, 3.9, 1.85, CARD2, BLUE_DK);
  txt(s, "資料清理", { x: 9.05, y: 1.67, w: 3.4, h: 0.3, fontSize: 12.5, bold: true, color: BLUE });
  ["漫遊比率「40%」字串 → 數值", "utf-8-sig 編碼與時間格式統一", "路網換版即重跑驗證並公開 SHA256"]
    .forEach((t, i) => txt(s, "· " + t, { x: 9.05, y: 2.05 + i * 0.4, w: 3.4, h: 0.38, fontSize: 10, color: FOG }));

  card(s, 8.8, 3.55, 3.9, 1.25, CARD);
  txt(s, "自行補充的官方圖資", { x: 9.05, y: 3.72, w: 3.4, h: 0.3, fontSize: 12.5, bold: true, color: BLUE });
  txt(s, "臺北市 GIS：號誌 47 處 · 人行道 19,643 筆 · 資訊可變標誌 178 面 · 醫院點位",
    { x: 9.05, y: 4.08, w: 3.4, h: 0.62, fontSize: 10, color: FOG });

  card(s, 0.6, 5.0, 7.9, 0.72, CARD2, BLUE_DK);
  txt(s, "8/2 主辦方更新路網檔，我們當天換版並重跑全套比對：15 個路段、3 筆事件，決策輸出零變動。",
    { x: 0.85, y: 5.18, w: 7.4, h: 0.4, fontSize: 12, bold: true });
  foot(s, "資料集 SHA256 與所有引擎常數可經 /api/provenance 端點即時查詢");
  s.addNotes("【4:38–4:58】念得快。重點只有一句：五份資料全部用上，而且我們把清理過程和資料的缺陷都公開了，包括一處命名不一致。誠實本身就是分數。");
}

/* ===== 11. 使用者流程 — 18 秒（官方必要章節 ④）===== */
{
  const s = S();
  eyebrow(s, "④ 使用者流程");
  title(s, "指揮官的 90 秒");
  const flow = [
    ["感知", "系統主動彈出\n預警"],
    ["判定", "分級 + 信心分數\n附數據佐證"],
    ["方案", "路線 · ETE\n調度建議"],
    ["比較", "沙盒推演\n含副作用"],
    ["核准", "指揮官按下\n確認"],
    ["通報", "四語告警\n派送與確認"],
    ["稽核", "決策軌跡\n可重播"]
  ];
  flow.forEach(([k, v], i) => {
    const x = 0.6 + i * 1.76;
    const human = i === 4;
    card(s, x, 1.9, 1.6, 1.65, human ? CARD2 : CARD, human ? BLUE : BORDER);
    txt(s, k, { x, y: 2.12, w: 1.6, h: 0.3, fontSize: 15, bold: true, align: "center", color: human ? BLUE : WHITE });
    txt(s, v, { x: x + 0.1, y: 2.52, w: 1.4, h: 0.8, fontSize: 10, color: FOG, align: "center" });
    if (i < 6) txt(s, "→", { x: x + 1.6, y: 2.5, w: 0.16, h: 0.3, fontSize: 14, color: SLATE, align: "center" });
  });
  card(s, 0.6, 4.0, 12.1, 0.9, CARD2, BLUE_DK);
  txt(s, "唯一的人工閘門", { x: 0.9, y: 4.2, w: 2.4, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  txt(s, "前四步系統全自動完成並把依據攤在桌上；第五步一定要人按。之後兩步再度自動化，但全程留痕。",
    { x: 3.3, y: 4.2, w: 9.2, h: 0.5, fontSize: 13.5 });
  card(s, 0.6, 5.1, 12.1, 0.75, CARD);
  txt(s, "六個操作頁面：總覽（3D 地球）· 指揮艙 · 監控 · 可驗證性 · 顧問對話 · 民眾手機模擬",
    { x: 0.9, y: 5.3, w: 11.6, h: 0.35, fontSize: 12, color: FOG });
  foot(s, "對應評分：完成度 20%（功能完整 · 使用體驗良好流暢）＋ 加分 5%（外觀直觀性與設計性）");
  s.addNotes("【4:58–5:16】手指沿著七個步驟劃過去，只停在第五格「核准」，說：這是唯一需要人的地方，而我們刻意讓它非人不可。");
}

/* ===== 12. AWS 架構圖 — 28 秒（官方必要章節 ⑤）===== */
{
  const s = S();
  eyebrow(s, "⑤ AWS 架構圖");
  title(s, "上雲路徑：同一組容器，換一個家");
  const bands = [
    ["接入層", ["Kinesis Data Streams\n車流／信令串流接入", "Amazon S3\n官方資料集與快照\n（版本 + SHA256）", "AWS IoT Core\n號誌與 CMS 設備介接"]],
    ["決策層", ["ECS Fargate + ALB\nFastAPI 確定性引擎", "Amazon Bedrock\nClaude — 僅生成文字", "DynamoDB\n事件狀態 · 決策軌跡\nElastiCache 時間軸快取"]],
    ["交付層", ["CloudFront + S3\nReact 指揮儀表板", "Amazon SNS / Pinpoint\n多語告警派送", "CloudWatch + OpenSearch\n六類日誌與稽核查詢"]]
  ];
  bands.forEach(([name, items], i) => {
    const y = 1.5 + i * 1.42;
    card(s, 0.6, y, 12.1, 1.24);
    txt(s, name, { x: 0.85, y: y + 0.42, w: 1.15, h: 0.3, fontSize: 13, bold: true, color: BLUE });
    items.forEach((it, j) => {
      const x = 2.15 + j * 3.55;
      card(s, x, y + 0.16, 3.35, 0.92, CARD2, BORDER);
      txt(s, it, { x: x + 0.15, y: y + 0.26, w: 3.05, h: 0.75, fontSize: 10, color: FOG });
    });
  });
  card(s, 0.6, 5.78, 12.1, 0.85, CARD2, BLUE_DK);
  txt(s, "IAM 落實邊界", { x: 0.9, y: 5.96, w: 2.3, h: 0.3, fontSize: 12.5, bold: true, color: BLUE });
  txt(s, "Bedrock 執行角色不具備 SNS 發布與設備控制權限 — 程式裡「工具不存在」的邊界，上雲後由 IAM policy 再鎖一次。",
    { x: 3.2, y: 5.96, w: 9.3, h: 0.5, fontSize: 12.5 });
  foot(s, "現況：同一組容器已在本機以 Docker 化前後端運行並通過全部測試；上表為對應的 AWS 部署規劃");
  s.addNotes("【5:16–5:44】老實講：這是部署規劃，目前跑在本機同一組容器。重點講兩個 AWS 原生的好處 — Bedrock 直接換掉外部 LLM，以及 IAM 把我們程式裡的邊界再鎖一次。不要逐格念服務名。");
}

/* ===== 13. 收尾 — 12 秒 ===== */
{
  const s = S();
  eyebrow(s, "完成度與交付");
  title(s, "三份交付，現在就可以驗");
  const items = [
    ["GitHub 原始碼", "完整專案 · 後端 137 項 + 前端 10 項測試全數通過", GREEN],
    ["Live Demo 部署網址", "六個頁面 · 44 個 API 端點 · 可現場操作與提問", GREEN],
    ["錄製影片連結", "完整流程演示，含事件注入與方案比較", GREEN]
  ];
  items.forEach(([k, v, c], i) => {
    const y = 1.6 + i * 1.0;
    card(s, 0.6, y, 12.1, 0.85);
    s.addShape(pres.ShapeType.rect, { x: 0.6, y, w: 0.05, h: 0.85, fill: { color: c }, line: { width: 0 } });
    txt(s, k, { x: 0.9, y: y + 0.15, w: 3.6, h: 0.3, fontSize: 14, bold: true });
    txt(s, v, { x: 4.6, y: y + 0.17, w: 7.9, h: 0.3, fontSize: 11.5, color: FOG });
  });
  card(s, 0.6, 4.75, 12.1, 1.5, CARD2, BLUE_DK);
  txt(s, "我們沒有把限制藏起來", { x: 0.9, y: 4.95, w: 5, h: 0.3, fontSize: 13, bold: true, color: BLUE });
  txt(s, "目前是確定性推演，不是校準過的微觀交通模型。校準需要貴方的歷史事件資料 — 介面已經留好，這是階段二的工作。",
    { x: 0.9, y: 5.32, w: 11.6, h: 0.5, fontSize: 12.5, color: FOG });
  txt(s, "AI 不下命令，AI 讓指揮官在 90 秒內做出敢負責的決定。",
    { x: 0.9, y: 5.78, w: 11.6, h: 0.4, fontSize: 16, bold: true, color: WHITE });
  foot(s, "CitySentinel · 城市應變 AI 智慧指揮中樞");
  s.addNotes("【5:44–6:00】不要念交付清單，說：三份東西現在就可以驗。然後把界線那段講完 — 主動承認限制，並把它轉成階段二的合作理由。最後一句金句收尾，停頓，結束。");
}

pres.writeFile({ fileName: "CitySentinel_決賽簡報_6分鐘.pptx" })
  .then(f => console.log("OK ->", f));
