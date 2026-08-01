// CitySentinel 提案簡報 — 中華電信城市應變分析 AI Agent
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5

// ---- 設計 token（沿用產品本身的控制室配色）----
const BG = "0E1012";
const CARD = "15171B";
const CARD2 = "1C1F24";
const BORDER = "23262D";
const BLUE = "007AFC";
const BLUE_DK = "0A3560";
const RED = "E5484D";
const AMBER = "F5A623";
const GREEN = "2FBF71";
const WHITE = "FFFFFF";
const FOG = "A0AABA";
const SLATE = "566171";
const H = "Microsoft JhengHei"; // 標題（含中文）
const B = "Microsoft JhengHei"; // 內文（含中文）
const M = "Consolas";          // 純 ASCII 數據／代碼／公式

const S = () => {
  const s = pres.addSlide();
  s.background = { color: BG };
  return s;
};
const eyebrow = (s, t, y = 0.4) =>
  s.addText(t, { x: 0.6, y, w: 11, h: 0.24, fontSize: 10.5, bold: true,
    color: SLATE, charSpacing: 2, fontFace: B, margin: 0 });
const title = (s, t, y = 0.68, size = 33) =>
  s.addText(t, { x: 0.6, y, w: 12.1, h: 0.62, fontSize: size, bold: true,
    color: WHITE, fontFace: H, margin: 0 });
const sub = (s, t, y) =>
  s.addText(t, { x: 0.6, y, w: 12.1, h: 0.3, fontSize: 13.5, color: FOG,
    fontFace: B, margin: 0 });
const card = (s, x, y, w, h, fill = CARD, line = BORDER) =>
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.09,
    fill: { color: fill }, line: { color: line, width: 1 } });
const foot = (s, t) =>
  s.addText(t, { x: 0.6, y: 6.92, w: 12.1, h: 0.28, fontSize: 10,
    color: SLATE, fontFace: B, margin: 0 });

/* ========== 1. 封面 ========== */
{
  const s = S();
  // 右側雷達環（呼應產品的地球視覺）
  [[3.05, "0A2942"], [2.35, "0C3557"], [1.7, "0E4373"], [1.1, "10528F"]].forEach(([r, c]) => {
    s.addShape(pres.ShapeType.ellipse, { x: 10.15 - r, y: 3.75 - r, w: r * 2, h: r * 2,
      fill: { color: BG }, line: { color: c, width: 1 } });
  });
  s.addShape(pres.ShapeType.ellipse, { x: 10.03, y: 3.63, w: 0.24, h: 0.24,
    fill: { color: BLUE }, line: { color: BLUE, width: 1 } });
  s.addText("臺北 · 信義計畫區", { x: 10.45, y: 3.62, w: 2.4, h: 0.26, fontSize: 10,
    color: BLUE, fontFace: B, margin: 0 });

  s.addText("2026 雲湧智生 · 臺灣生成式 AI 應用黑客松｜中華電信命題：城市應變分析 AI Agent",
    { x: 0.85, y: 0.85, w: 9, h: 0.3, fontSize: 11, bold: true, color: SLATE,
      charSpacing: 1.5, fontFace: B, margin: 0 });

  s.addText("CitySentinel", { x: 0.85, y: 2.15, w: 8.6, h: 1.05, fontSize: 60,
    bold: true, color: WHITE, fontFace: H, margin: 0 });
  s.addText("城市應變 AI 智慧指揮中樞", { x: 0.85, y: 3.2, w: 8.6, h: 0.55,
    fontSize: 25, color: FOG, fontFace: B, margin: 0 });

  s.addShape(pres.ShapeType.roundRect, { x: 0.85, y: 4.05, w: 7.9, h: 0.52,
    rectRadius: 0.1, fill: { color: "0A1F33" }, line: { color: BLUE_DK, width: 1 } });
  s.addText("確定性引擎判定　·　LLM 解釋與對話　·　每個決策都能被質疑",
    { x: 1.05, y: 4.05, w: 7.5, h: 0.52, fontSize: 12.5, color: BLUE,
      fontFace: B, valign: "middle", margin: 0 });

  const stats = [["5/5", "官方模組全交付"], ["105", "自動化測試"], ["4", "通報語言"], ["< 15s", "端到端應變"]];
  stats.forEach(([n, l], i) => {
    const x = 0.85 + i * 2.05;
    s.addText(n, { x, y: 5.35, w: 1.9, h: 0.5, fontSize: 27, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(l, { x, y: 5.87, w: 1.9, h: 0.28, fontSize: 10.5, color: SLATE,
      fontFace: B, margin: 0 });
  });
  s.addNotes("開場：我們不是做一個會聊天的交通機器人，而是一套可以被稽核的城市指揮系統。今天要證明三件事：判定準確、決策可驗證、指揮官保有最終權力。");
}

/* ========== 2. 執行摘要 ========== */
{
  const s = S();
  eyebrow(s, "EXECUTIVE SUMMARY");
  title(s, "一頁看懂：我們交付了什麼");
  sub(s, "五大必要模組全數落地，並在三個評審最常追問的面向上建立了難以複製的優勢。", 1.35);

  const kpi = [["5 / 5", "官方模組", "全數可現場操作", BLUE],
               ["105", "自動化測試", "SOP 邊界全覆蓋", GREEN],
               ["7,100+", "程式行數", "前後端完整交付", WHITE]];
  kpi.forEach(([n, l, d, c], i) => {
    const x = 0.6 + i * 4.07;
    card(s, x, 1.85, 3.85, 1.35);
    s.addText(n, { x: x + 0.28, y: 2.0, w: 3.3, h: 0.6, fontSize: 34, bold: true,
      color: c, fontFace: H, margin: 0 });
    s.addText(l, { x: x + 0.28, y: 2.58, w: 3.3, h: 0.26, fontSize: 12.5, bold: true,
      color: WHITE, fontFace: B, margin: 0 });
    s.addText(d, { x: x + 0.28, y: 2.84, w: 3.3, h: 0.26, fontSize: 10.5, color: SLATE,
      fontFace: B, margin: 0 });
  });

  const diff = [
    ["01", "判定與生成徹底分離", "SOP 門檻、替代路徑、ETE 由程式運算；LLM 只負責解釋與多語文字。即使 LLM 全數失效，決策核心照常輸出完整處置。", BLUE],
    ["02", "每個決策都可被質疑", "決策鏈、排除理由、資料 SHA256、引擎門檻常數全部開放查詢；指揮官可接受、調整或拒絕任一調度，覆寫全程留痕。", AMBER],
    ["03", "閉環延伸到市民手機", "通報須人工核准才能發布，送達／失敗／重試全程可見；簡訊通道未送達前，民眾端不會顯示警報。", GREEN]];
  diff.forEach(([n, t, d, c], i) => {
    const y = 3.45 + i * 1.15;
    card(s, 0.6, y, 12.1, 1.02);
    s.addShape(pres.ShapeType.ellipse, { x: 0.85, y: y + 0.26, w: 0.5, h: 0.5,
      fill: { color: CARD2 }, line: { color: c, width: 1 } });
    s.addText(n, { x: 0.85, y: y + 0.26, w: 0.5, h: 0.5, fontSize: 12.5, bold: true,
      color: c, fontFace: M, align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: 1.55, y: y + 0.15, w: 4.0, h: 0.32, fontSize: 15, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: 5.5, y: y + 0.14, w: 6.95, h: 0.75, fontSize: 11.5, color: FOG,
      fontFace: B, lineSpacing: 16, margin: 0 });
  });
  s.addNotes("這頁是全場唯一必須記住的一頁。三個差異化直接對應評審最愛問的三個問題：AI 會不會亂講？我憑什麼相信它？出事了誰負責？");
}

/* ========== 3. 解題方向 ========== */
{
  const s = S();
  eyebrow(s, "解題方向 · PROBLEM FRAMING");
  title(s, "城市應變的難題，不是「不會講話」");
  sub(s, "而是「講了不能信、信了不能查、查了不能改」。我們的設計從這三個缺口出發。", 1.35);

  s.addText("現場痛點", { x: 0.6, y: 1.95, w: 5.8, h: 0.3, fontSize: 13, bold: true,
    color: RED, fontFace: B, charSpacing: 1, margin: 0 });
  const pain = [
    ["判定不可信", "純 LLM 產生的分級與路徑無法重現，同一情境兩次答案可能不同，不敢作為調度依據。"],
    ["責任不可追", "只給一句建議，沒有輸入資料、觸發條款與排除理由，事後無法回答「為什麼這樣判」。"],
    ["處置不可控", "系統直接發布或直接派遣，指揮官被架空；資源衝突時只能先搶先贏。"]];
  pain.forEach(([t, d], i) => {
    const y = 2.35 + i * 1.42;
    card(s, 0.6, y, 5.8, 1.28, "1A1315", "3D2226");
    s.addText(t, { x: 0.9, y: y + 0.16, w: 5.2, h: 0.3, fontSize: 15, bold: true,
      color: RED, fontFace: H, margin: 0 });
    s.addText(d, { x: 0.9, y: y + 0.5, w: 5.2, h: 0.7, fontSize: 11.5, color: FOG,
      fontFace: B, lineSpacing: 16, margin: 0 });
  });

  s.addText("我們的主張", { x: 6.9, y: 1.95, w: 5.8, h: 0.3, fontSize: 13, bold: true,
    color: BLUE, fontFace: B, charSpacing: 1, margin: 0 });
  const sol = [
    ["程式判定、LLM 解釋", "SOP 門檻、路徑篩選、ETE 全部由確定性引擎計算，結果可重算、可寫測試、可被評審手動驗算。"],
    ["決策鏈即證據鏈", "每一步保留輸入快照、觸發條款、候選與排除理由、公式明細；資料來源附 SHA256。"],
    ["人保有最終指揮權", "調度可接受／調整／拒絕，通報須核准才發布；高優先事件抽調資源亦需人工核准，雙邊留痕。"]];
  sol.forEach(([t, d], i) => {
    const y = 2.35 + i * 1.42;
    card(s, 6.9, y, 5.8, 1.28, "0C1A28", "12385C");
    s.addText(t, { x: 7.2, y: y + 0.16, w: 5.2, h: 0.3, fontSize: 15, bold: true,
      color: BLUE, fontFace: H, margin: 0 });
    s.addText(d, { x: 7.2, y: y + 0.5, w: 5.2, h: 0.7, fontSize: 11.5, color: FOG,
      fontFace: B, lineSpacing: 16, margin: 0 });
  });
  s.addNotes("痛點對主張，一一對應。這頁確立我們不是在做功能堆疊，而是在解決可信度問題。");
}

/* ========== 4. 核心架構 ========== */
{
  const s = S();
  eyebrow(s, "核心架構 · ARCHITECTURE THESIS");
  title(s, "決策層與諮詢層，雙軌分離");
  sub(s, "這是整套系統的設計靈魂：讓 AI 發揮語言能力，但不讓它碰判定與執行。", 1.35);

  // 決策層
  card(s, 0.6, 1.95, 12.1, 1.85, "0C1A28", "12385C");
  s.addText("決策層　確定性引擎", { x: 0.95, y: 2.1, w: 5, h: 0.34, fontSize: 16,
    bold: true, color: BLUE, fontFace: H, margin: 0 });
  s.addText("LLM 不可觸碰　·　可重算　·　有測試覆蓋", { x: 0.95, y: 2.44, w: 6, h: 0.26,
    fontSize: 11, color: SLATE, fontFace: B, margin: 0 });
  const eng = [["Rule Engine", "SOP 1–6 門檻判定"], ["Routing Engine", "SOP 2 疏散路徑篩選"],
               ["ETE Calculator", "SOP 7 恢復時間公式"], ["Dispatch Engine", "資源調度與缺口回報"]];
  eng.forEach(([t, d], i) => {
    const x = 0.95 + i * 2.92;
    card(s, x, 2.82, 2.72, 0.85, CARD2, "1B3A57");
    s.addText(t, { x: x + 0.18, y: 2.92, w: 2.4, h: 0.28, fontSize: 12, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: x + 0.18, y: 3.2, w: 2.4, h: 0.38, fontSize: 10, color: FOG,
      fontFace: B, margin: 0 });
  });

  // 邊界
  s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 3.98, w: 12.1, h: 0.46,
    rectRadius: 0.08, fill: { color: "1A1206" }, line: { color: "4A3A14", width: 1 } });
  s.addText("安全邊界：LLM 的工具清單只有唯讀查詢與 Sandbox 模擬 — 發布通報、調度資源、核准動作的工具「不存在」",
    { x: 0.85, y: 3.98, w: 11.6, h: 0.46, fontSize: 11.5, color: AMBER, fontFace: B,
      valign: "middle", margin: 0 });

  // 諮詢層
  card(s, 0.6, 4.62, 12.1, 1.85);
  s.addText("諮詢層　LLM Agent", { x: 0.95, y: 4.77, w: 5, h: 0.34, fontSize: 16,
    bold: true, color: WHITE, fontFace: H, margin: 0 });
  s.addText("自主選擇工具　·　唯讀權限　·　失敗自動降級模板", { x: 0.95, y: 5.11, w: 6.5, h: 0.26,
    fontSize: 11, color: SLATE, fontFace: B, margin: 0 });
  const llm = [["預警摘要", "情勢分析自動生成"], ["導引與多語", "CMS 與中英日韓告警"],
               ["顧問 Agent", "自主查證後回答"], ["決策摘要", "總司令一句話判定"]];
  llm.forEach(([t, d], i) => {
    const x = 0.95 + i * 2.92;
    card(s, x, 5.49, 2.72, 0.85, CARD2);
    s.addText(t, { x: x + 0.18, y: 5.59, w: 2.4, h: 0.28, fontSize: 12, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: x + 0.18, y: 5.87, w: 2.4, h: 0.38, fontSize: 10, color: FOG,
      fontFace: B, margin: 0 });
  });
  foot(s, "設計原則：LLM 負責模糊理解與文字生成，程式負責確定性判定與計算，狀態機負責流程控制。");
  s.addNotes("如果評審只問一個問題「你們的 AI 會不會亂決策」，答案就在這一頁：它沒有那個權限，工具清單裡根本沒有執行類工具。");
}

/* ========== 5. 五大模組對照 ========== */
{
  const s = S();
  eyebrow(s, "需求對照 · REQUIREMENT MAPPING");
  title(s, "官方五大必要模組：逐項對照交付");
  sub(s, "每一列都可在現場 Demo 直接操作驗證，非簡報文字宣稱。", 1.35);

  const rows = [
    ["01", "動態時序監測儀表板", "門檻由程式判定、摘要由 LLM 生成，無需人工介入", "時序播放自動觸發預警彈窗，AI 情勢摘要自動載入"],
    ["02", "突發事件注入與處置", "60 秒內完成路網重規劃，避開容量不足路段", "實測端到端 < 15 秒；容量 <1000、非直接相交一律排除"],
    ["03", "對話式策略諮詢", "依假設條件檢索 SOP 並回答應觸發條款", "Tool-Calling Agent 自主查證，Sandbox 驗證不動正式狀態"],
    ["04", "決策推理與解釋鏈", "展示判定依據、排除理由與 ETE 公式", "五階段決策鏈可展開；排除理由代碼化；公式全文可重算"],
    ["05", "多語化全通路通報", "漫遊率 ≥30% 自動產出多語告警供一鍵發布", "中英日韓 LLM 在地化生成，須人工核准才發布並追蹤送達"]];
  rows.forEach(([n, t, req, our], i) => {
    const y = 1.85 + i * 0.96;
    card(s, 0.6, y, 12.1, 0.86);
    s.addText(n, { x: 0.82, y: y + 0.28, w: 0.5, h: 0.3, fontSize: 13, bold: true,
      color: BLUE, fontFace: M, margin: 0 });
    s.addText(t, { x: 1.4, y: y + 0.27, w: 2.65, h: 0.32, fontSize: 13, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(req, { x: 4.2, y: y + 0.14, w: 4.0, h: 0.62, fontSize: 10.5, color: SLATE,
      fontFace: B, lineSpacing: 14, margin: 0 });
    s.addShape(pres.ShapeType.ellipse, { x: 8.35, y: y + 0.31, w: 0.26, h: 0.26,
      fill: { color: "0B2A18" }, line: { color: GREEN, width: 1 } });
    s.addText("✓", { x: 8.35, y: y + 0.31, w: 0.26, h: 0.26, fontSize: 11, bold: true,
      color: GREEN, fontFace: B, align: "center", valign: "middle", margin: 0 });
    s.addText(our, { x: 8.78, y: y + 0.14, w: 3.72, h: 0.62, fontSize: 10.5, color: FOG,
      fontFace: B, lineSpacing: 14, margin: 0 });
  });
  foot(s, "左：官方命題文件原文要求　　　右：本系統實作狀態（含實測數據）");
  s.addNotes("這頁讓評審打勾用。每一項都能當場叫出畫面驗證。");
}

/* ========== 6. 決策邏輯準確性（實例）========== */
{
  const s = S();
  eyebrow(s, "技術可行性 · 決策邏輯準確性（評分佔比 35%）");
  title(s, "以官方事件實算：每一步都能被驗算");
  sub(s, "事件 TPE_2026_ACC_001　光復南路路面塌陷　Closed／Critical　2026-05-20 22:10", 1.35);

  // 步驟流程
  const steps = [
    ["1", "取候選", "由事故路段 alternatives\n取 4 條，單向不反推"],
    ["2", "篩容量", "capacity_vph ≥ 1000\n延吉街 600 → 排除"],
    ["3", "驗相交", "須出現在 intersections\n敦化南路一段 → 排除"],
    ["4", "判上下游", "依 flow_direction 排序\n仁愛路四段在下游"],
    ["5", "選最低飽和", "上游候選比飽和度\n市民大道四段 0.78"]];
  steps.forEach(([n, t, d], i) => {
    const x = 0.6 + i * 2.45;
    card(s, x, 1.9, 2.25, 1.5);
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.18, y: 2.05, w: 0.34, h: 0.34,
      fill: { color: "0A2942" }, line: { color: BLUE, width: 1 } });
    s.addText(n, { x: x + 0.18, y: 2.05, w: 0.34, h: 0.34, fontSize: 11, bold: true,
      color: BLUE, fontFace: M, align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: x + 0.6, y: 2.06, w: 1.5, h: 0.3, fontSize: 12.5, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: x + 0.18, y: 2.5, w: 1.9, h: 0.78, fontSize: 10, color: FOG,
      fontFace: B, lineSpacing: 13, margin: 0 });
    if (i < 4) s.addText("→", { x: x + 2.22, y: 2.45, w: 0.3, h: 0.4, fontSize: 15,
      color: SLATE, fontFace: B, align: "center", margin: 0 });
  });

  // 結果
  card(s, 0.6, 3.62, 5.95, 1.5, "0C1A28", "12385C");
  s.addText("處置結果", { x: 0.9, y: 3.76, w: 3, h: 0.28, fontSize: 12, bold: true,
    color: BLUE, fontFace: B, charSpacing: 1, margin: 0 });
  s.addText([
    { text: "主疏散　", options: { color: SLATE } },
    { text: "市民大道四段", options: { color: WHITE, bold: true } },
    { text: "　（上游 · 容量 2500 · 飽和 0.78）\n", options: { color: FOG } },
    { text: "次要　　", options: { color: SLATE } },
    { text: "仁愛路四段", options: { color: WHITE } },
    { text: "　（位於事故點下游，僅列次要）\n", options: { color: FOG } },
    { text: "排除　　", options: { color: SLATE } },
    { text: "延吉街", options: { color: RED } },
    { text: "　CAPACITY_BELOW_1000\n", options: { color: FOG } },
    { text: "　　　　", options: { color: SLATE } },
    { text: "敦化南路一段", options: { color: RED } },
    { text: "　NOT_DIRECT_INTERSECTION", options: { color: FOG } }],
    { x: 0.9, y: 4.08, w: 5.4, h: 0.95, fontSize: 10.5, fontFace: B, lineSpacing: 17, margin: 0 });

  card(s, 6.75, 3.62, 5.95, 1.5, "0C1A28", "12385C");
  s.addText("ETE 計算（SOP 第 7 條）", { x: 7.05, y: 3.76, w: 4, h: 0.28, fontSize: 12,
    bold: true, color: BLUE, fontFace: B, charSpacing: 1, margin: 0 });
  s.addText("ETE = base_clearance + max(0, (avg_sat - 0.5) * 60)\n    = 60 + max(0, (1.00 - 0.5) * 60)",
    { x: 7.05, y: 4.12, w: 5.4, h: 0.6, fontSize: 11, color: FOG, fontFace: M,
      lineSpacing: 17, margin: 0 });
  s.addText("= 90 分鐘", { x: 7.05, y: 4.72, w: 5.4, h: 0.34, fontSize: 16, bold: true,
    color: GREEN, fontFace: H, margin: 0 });

  // CMS
  card(s, 0.6, 5.32, 12.1, 1.32);
  s.addText("同一份結果，直接產出對外文字與可信度佐證", { x: 0.9, y: 5.45, w: 6, h: 0.28,
    fontSize: 12, bold: true, color: WHITE, fontFace: H, margin: 0 });
  s.addText("CMS　「光復南路封閉，請改道 市民大道四段，預計延誤 90 分鐘」", { x: 0.9, y: 5.78,
    w: 7.2, h: 0.3, fontSize: 11, color: FOG, fontFace: B, margin: 0 });
  s.addText("事件可信度　95%（高）　官方來源＋車速降至 2 km/h＋車道 Accident_Impact＋周邊人流異常",
    { x: 0.9, y: 6.08, w: 11.5, h: 0.3, fontSize: 11, color: FOG, fontFace: B, margin: 0 });
  s.addNotes("這是全場最關鍵的一頁。評審可以拿命題資料自己算一次，數字必須一模一樣。排除理由是代碼化的，不是文字描述。");
}

/* ========== 7. AI 技術應用（一）Guardrail ========== */
{
  const s = S();
  eyebrow(s, "AI 技術應用 · GENERATIVE AI");
  title(s, "LLM 生文，程式驗數");
  sub(s, "官方明列三處須由 LLM 生成。我們全部接上真實模型，並用「必含 token 驗證」守住每一個數字。", 1.35);

  const gen = [["預警摘要", "門檻由程式判定後，LLM 生成情勢分析並自動彈出", "官方模組 1"],
               ["導引文字", "CMS 電子看板改道指示由 LLM 撰寫", "官方模組 2"],
               ["多語告警", "中英日韓在地化生成，非逐字翻譯", "官方模組 5"]];
  gen.forEach(([t, d, tag], i) => {
    const x = 0.6 + i * 4.07;
    card(s, x, 1.88, 3.85, 1.28);
    s.addText(tag, { x: x + 0.28, y: 2.0, w: 3.3, h: 0.24, fontSize: 9.5, bold: true,
      color: BLUE, fontFace: B, margin: 0 });
    s.addText(t, { x: x + 0.28, y: 2.26, w: 3.3, h: 0.3, fontSize: 15, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: x + 0.28, y: 2.58, w: 3.3, h: 0.52, fontSize: 11, color: FOG,
      fontFace: B, lineSpacing: 15, margin: 0 });
  });

  s.addText("Guardrail：文字可以創作，數字不容竄改", { x: 0.6, y: 3.4, w: 8, h: 0.34,
    fontSize: 16, bold: true, color: WHITE, fontFace: H, margin: 0 });

  card(s, 0.6, 3.85, 5.95, 1.42, "1A1315", "3D2226");
  s.addText("LLM 若改寫關鍵數值", { x: 0.9, y: 3.98, w: 5.2, h: 0.28, fontSize: 12,
    bold: true, color: RED, fontFace: B, margin: 0 });
  s.addText("「…請改道市民大道四段，預計延誤約一個半小時」", { x: 0.9, y: 4.3, w: 5.4, h: 0.3,
    fontSize: 11, color: FOG, fontFace: B, margin: 0 });
  s.addText("必含字串 [\"90\"] 未出現 → 整段棄用", { x: 0.9, y: 4.66, w: 5.4, h: 0.3,
    fontSize: 11, color: RED, fontFace: B, margin: 0 });
  s.addText("→ 自動退回確定性模板，UI 標示攔截原因", { x: 0.9, y: 4.94, w: 5.4, h: 0.3,
    fontSize: 10.5, color: SLATE, fontFace: B, margin: 0 });

  card(s, 6.75, 3.85, 5.95, 1.42, "0C1A28", "12385C");
  s.addText("四語數字不變性檢查", { x: 7.05, y: 3.98, w: 5.2, h: 0.28, fontSize: 12,
    bold: true, color: BLUE, fontFace: B, margin: 0 });
  s.addText("時間戳、路名、ETE 分鐘數必須原封不動出現在每一語言版本；\n任一語言缺任一項 → 四語整包退回模板。",
    { x: 7.05, y: 4.3, w: 5.4, h: 0.6, fontSize: 11, color: FOG, fontFace: B,
      lineSpacing: 16, margin: 0 });
  s.addText("生成來源（LLM／模板）全程標示於 UI 與決策鏈", { x: 7.05, y: 4.94, w: 5.4, h: 0.3,
    fontSize: 10.5, color: SLATE, fontFace: B, margin: 0 });

  card(s, 0.6, 5.45, 12.1, 1.1, CARD2);
  s.addText("模型可替換 · 失敗不中斷", { x: 0.9, y: 5.57, w: 4, h: 0.28, fontSize: 12.5,
    bold: true, color: WHITE, fontFace: H, margin: 0 });
  s.addText("同時支援 Amazon Bedrock（Claude）與 OpenAI，依環境變數自動切換；LLM 逾時或被 Guardrail 攔截時一律降級為確定性模板，事件流程永不失敗。每次呼叫的用途、模型、延遲、成敗全部寫入系統紀錄供稽核。",
    { x: 0.9, y: 5.86, w: 11.5, h: 0.55, fontSize: 11, color: FOG, fontFace: B,
      lineSpacing: 16, margin: 0 });
  s.addNotes("這頁回答「你怎麼確定 LLM 不會唬爛數字」。答案是：我們不相信它，我們檢查它。而且攔截紀錄本身就是展示素材。");
}

/* ========== 8. AI 技術應用（二）Agent ========== */
{
  const s = S();
  eyebrow(s, "AI 技術應用 · AGENTIC AI");
  title(s, "諮詢層是真正的 Tool-Calling Agent");
  sub(s, "LLM 自主決定呼叫哪些工具、帶什麼參數、何時停止——而它能碰到的工具，全部是唯讀。", 1.35);

  const tools = [["get_sop", "查條款原文"], ["get_incident", "查事件決策"], ["run_what_if", "Sandbox 模擬"],
                 ["get_traffic", "查車流快照"], ["get_crowd", "查人流快照"], ["get_resources", "查資源庫存"],
                 ["get_confidence", "查可信度"]];
  s.addText("工具允許清單（唯讀 / Sandbox）", { x: 0.6, y: 1.9, w: 6, h: 0.28, fontSize: 12,
    bold: true, color: SLATE, fontFace: B, charSpacing: 1, margin: 0 });
  tools.forEach(([t, d], i) => {
    const x = 0.6 + (i % 4) * 3.07;
    const y = 2.25 + Math.floor(i / 4) * 0.78;
    card(s, x, y, 2.85, 0.65, CARD2);
    s.addText(t, { x: x + 0.2, y: y + 0.08, w: 2.5, h: 0.26, fontSize: 11, bold: true,
      color: BLUE, fontFace: M, margin: 0 });
    s.addText(d, { x: x + 0.2, y: y + 0.34, w: 2.5, h: 0.24, fontSize: 10, color: FOG,
      fontFace: B, margin: 0 });
  });
  card(s, 9.85, 3.03, 2.85, 0.65, "1A1315", "3D2226");
  s.addText("發布 / 調度 / 核准", { x: 10.05, y: 3.11, w: 2.5, h: 0.26, fontSize: 11,
    bold: true, color: RED, fontFace: B, margin: 0 });
  s.addText("工具不存在 — 物理性邊界", { x: 10.05, y: 3.37, w: 2.5, h: 0.24, fontSize: 10,
    color: RED, fontFace: B, margin: 0 });

  s.addText("實測軌跡：評審提問「如果 BL17 人數增加到 40000 人會怎樣？」", { x: 0.6, y: 4.02,
    w: 9, h: 0.3, fontSize: 13.5, bold: true, color: WHITE, fontFace: H, margin: 0 });
  card(s, 0.6, 4.4, 12.1, 1.55, "0C1A28", "12385C");
  s.addText([
    { text: "Agent 自主呼叫　run_what_if(", options: { color: BLUE } },
    { text: "{at:\"2026-05-20 22:00\", crowd_overrides:{BS_MRT_BL17:{user_count:40000}}}", options: { color: FOG } },
    { text: ")\n", options: { color: BLUE } },
    { text: "→ 基準 [1,3,4,6] → 假設後 [1,3,4,6]　Sandbox 執行，正式狀態未修改\n\n", options: { color: SLATE } },
    { text: "回答　", options: { color: SLATE } },
    { text: "依 SOP 3 建議北捷過站不停、通知公車處調度接駁專車、引導群眾步行至 BS_MRT_BL18；該條款於基準狀態已觸發並持續適用。",
      options: { color: WHITE } }],
    { x: 0.9, y: 4.55, w: 11.5, h: 1.3, fontSize: 11, fontFace: B, lineSpacing: 17, margin: 0 });

  card(s, 0.6, 6.1, 12.1, 0.62, CARD2);
  s.addText("安全設計：迴圈上限 5 輪　·　引用條款由工具軌跡推導（不信任 LLM 自報）　·　每一步呼叫寫入稽核紀錄　·　工具軌跡即時顯示於對話介面",
    { x: 0.9, y: 6.1, w: 11.5, h: 0.62, fontSize: 11, color: FOG, fontFace: B,
      valign: "middle", margin: 0 });
  s.addNotes("如果被問「這到底算不算 Agent」——工具軌跡是即時顯示在畫面上的，可以當場請評審出題看它自己選工具。");
}

/* ========== 9. 白盒可驗證 ========== */
{
  const s = S();
  eyebrow(s, "可驗證性 · WHITE-BOX BY DESIGN");
  title(s, "每個數字，都能被追問到底");
  sub(s, "不是「相信 AI」，而是「查核 AI」。三層證據任評審抽驗。", 1.35);

  const ev = [
    ["決策依據與執行進度", "五階段可展開", ["事件驗證　來源數、可信度", "影響評估　觸發條款、ETE 明細",
      "方案規劃　候選、排除理由、SOP 原文", "資源與核准　派遣、人工覆寫紀錄", "通知與追蹤　多語內容、送達率"], BLUE],
    ["資料佐證", "來源可重算", ["road_network SHA256 05FE3CAF…", "五份官方資料筆數全公開",
      "引擎門檻常數全部開放查詢", "B/A 級 0.85 / 0.95", "容量門檻 1000 vph"], GREEN],
    ["事件可信度", "多源交叉驗證", ["官方事件來源　+0.50", "車速崩跌 2 km/h　+0.20",
      "車道狀態相符　+0.15", "周邊人流異常　+0.10", "→ 95%（高）附完整證據句"], AMBER]];
  ev.forEach(([t, tag, items, c], i) => {
    const x = 0.6 + i * 4.07;
    card(s, x, 1.9, 3.85, 4.35);
    s.addText(tag, { x: x + 0.28, y: 2.05, w: 3.3, h: 0.24, fontSize: 9.5, bold: true,
      color: c, fontFace: B, charSpacing: 1, margin: 0 });
    s.addText(t, { x: x + 0.28, y: 2.3, w: 3.3, h: 0.34, fontSize: 15, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    items.forEach((it, j) => {
      s.addShape(pres.ShapeType.ellipse, { x: x + 0.3, y: 2.9 + j * 0.66, w: 0.12, h: 0.12,
        fill: { color: c }, line: { color: c, width: 1 } });
      s.addText(it, { x: x + 0.52, y: 2.78 + j * 0.66, w: 3.05, h: 0.55, fontSize: 10.5,
        color: FOG, fontFace: B, lineSpacing: 14, margin: 0 });
    });
  });
  card(s, 0.6, 6.42, 12.1, 0.55, CARD2);
  s.addText("人工覆寫全程留痕：指揮官調整或拒絕任一調度時，系統保留原始 AI 建議、操作者、理由與時間，兩份數字並存於稽核紀錄。",
    { x: 0.9, y: 6.42, w: 11.5, h: 0.55, fontSize: 11, color: FOG, fontFace: B,
      valign: "middle", margin: 0 });
  s.addNotes("這頁是給稽核與法遵看的。公部門標案最在意的就是「事後說得清楚」。");
}

/* ========== 10. 數據資料應用 ========== */
{
  const s = S();
  eyebrow(s, "數據資料應用 · DATA UTILISATION");
  title(s, "五份官方資料，全部進入決策路徑");
  sub(s, "沒有一份是裝飾用的展示資料——每一份都直接影響判定結果。", 1.35);

  const data = [
    ["city_traffic_flow.csv", "112 筆", "分級判定 · 路徑排序 · ETE 懲罰項"],
    ["signaling_crowd_density.csv", "36 筆", "捷運分流 · 散場偵測 · 多語觸發"],
    ["road_network_geometry.json", "15 路段", "候選來源 · 容量篩選 · 上下游判定"],
    ["emergency_traffic_sop.txt", "7 條規則", "門檻定義 · 條款檢索 · 引用驗證"],
    ["live_incidents.json", "3 事件", "事件注入 · 可信度基準"]];
  data.forEach(([f, n, u], i) => {
    const x = 0.6 + i * 2.45;
    card(s, x, 1.9, 2.25, 1.62);
    s.addText(n, { x: x + 0.2, y: 2.02, w: 1.9, h: 0.34, fontSize: 17, bold: true,
      color: BLUE, fontFace: H, margin: 0 });
    s.addText(f, { x: x + 0.2, y: 2.4, w: 1.95, h: 0.5, fontSize: 8.5, color: WHITE,
      fontFace: M, lineSpacing: 11, margin: 0 });
    s.addText(u, { x: x + 0.2, y: 2.92, w: 1.9, h: 0.52, fontSize: 9.5, color: FOG,
      fontFace: B, lineSpacing: 12, margin: 0 });
  });

  s.addText("資料治理：先解決品質問題，才談 AI", { x: 0.6, y: 3.72, w: 8, h: 0.34,
    fontSize: 16, bold: true, color: WHITE, fontFace: H, margin: 0 });

  const gov = [
    ["版本權威性", "命題資料夾內有兩份路網檔，三條路段的 intersections 順序不同。因順序代表上游至下游、直接影響疏散判定，我們指定官方資料夾版為唯一來源並以 SHA256 標記，系統禁止讀取其他副本。", RED],
    ["欄位清洗", "漫遊率為帶百分號字串（\"40%\"），載入時清洗為數值；時間統一解析為 datetime；CSV 以 utf-8-sig 讀取避免 BOM 汙染首欄。", BLUE],
    ["時間切面", "所有判定以「某時刻的最新快照」為準，車流與人流各自取該時點前最後一筆，確保跨資料源的時間一致性。", GREEN]];
  gov.forEach(([t, d, c], i) => {
    const y = 4.18 + i * 0.86;
    card(s, 0.6, y, 12.1, 0.76);
    s.addText(t, { x: 0.9, y: y + 0.05, w: 2.1, h: 0.66, fontSize: 12.5, bold: true,
      color: c, fontFace: H, valign: "middle", margin: 0 });
    s.addText(d, { x: 3.0, y: y + 0.06, w: 9.45, h: 0.64, fontSize: 10.5, color: FOG,
      fontFace: B, lineSpacing: 14, valign: "middle", margin: 0 });
  });
  s.addNotes("版本權威性這點特別重要——它證明我們真的讀懂了資料，而不是隨便挑一份用。這是資料工程的基本功。");
}

/* ========== 11. 使用者流程 ========== */
{
  const s = S();
  eyebrow(s, "使用者流程 · OPERATIONAL WORKFLOW");
  title(s, "從偵測異常，到市民手機收到指示");
  sub(s, "指揮官在每一刻都清楚：現在發生什麼、哪裡受影響、系統為何這樣建議、我要做什麼決定。", 1.35);

  const flow = [["01", "自動監測", "沿時間軸讀取車流與人流，程式判定 SOP 門檻"],
                ["02", "事件建立", "計算多源可信度與影響範圍，進入事件佇列"],
                ["03", "地圖聚焦", "事故點擴散 pulse，受影響路段即時變色"],
                ["04", "方案生成", "路徑重規劃、ETE、資源需求一次算完"],
                ["05", "人工核准", "接受／調整／拒絕，可抽調低優先事件資源"],
                ["06", "通報發布", "四語內容核准後發送，追蹤送達與重試"],
                ["07", "民眾接收", "簡訊送達後手機跳出疏散指示"]];
  flow.forEach(([n, t, d], i) => {
    const x = 0.6 + i * 1.755;
    card(s, x, 2.0, 1.62, 2.3);
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.15, y: 2.16, w: 0.42, h: 0.42,
      fill: { color: "0A2942" }, line: { color: BLUE, width: 1 } });
    s.addText(n, { x: x + 0.15, y: 2.16, w: 0.42, h: 0.42, fontSize: 11, bold: true,
      color: BLUE, fontFace: M, align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: x + 0.15, y: 2.68, w: 1.35, h: 0.3, fontSize: 12.5, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: x + 0.15, y: 3.02, w: 1.35, h: 1.15, fontSize: 9.5, color: FOG,
      fontFace: B, lineSpacing: 12.5, margin: 0 });
    if (i < 6) s.addText("›", { x: x + 1.6, y: 2.9, w: 0.2, h: 0.3, fontSize: 16,
      color: SLATE, fontFace: B, align: "center", margin: 0 });
  });

  card(s, 0.6, 4.5, 5.95, 2.05, "0C1A28", "12385C");
  s.addText("Coordinator 決策摘要", { x: 0.9, y: 4.63, w: 5, h: 0.28, fontSize: 12,
    bold: true, color: BLUE, fontFace: B, charSpacing: 1, margin: 0 });
  s.addText("系統為每個事件生成一句可讀的總司令判定，四段結構固定：",
    { x: 0.9, y: 4.94, w: 5.4, h: 0.28, fontSize: 10.5, color: SLATE, fontFace: B, margin: 0 });
  s.addText([
    { text: "判定　", options: { color: SLATE } }, { text: "事故可信度 95%，光復南路全線封閉\n", options: { color: WHITE } },
    { text: "行動　", options: { color: SLATE } }, { text: "改道市民大道四段，派遣警力 4 名\n", options: { color: WHITE } },
    { text: "升級　", options: { color: SLATE } }, { text: "主疏散飽和度達 0.85 時啟動長綠燈並併行大眾運輸\n", options: { color: WHITE } },
    { text: "依據　", options: { color: SLATE } }, { text: "SOP 2、SOP 7，ETE 90 分鐘", options: { color: WHITE } }],
    { x: 0.9, y: 5.24, w: 5.4, h: 1.2, fontSize: 10.5, fontFace: B, lineSpacing: 16, margin: 0 });

  card(s, 6.75, 4.5, 5.95, 2.05);
  s.addText("分級告警：搶注意力，不搶操作權", { x: 7.05, y: 4.63, w: 5, h: 0.28, fontSize: 12,
    bold: true, color: WHITE, fontFace: H, margin: 0 });
  const al = [["一般監測異常", "地圖 pulse + 告警摘要列，不遮擋", GREEN],
              ["需處置新事件", "右側事件快報卡滑出 + 自動聚焦", AMBER],
              ["資源缺口等重大風險", "中央 modal，說明理由並要求決策", RED]];
  al.forEach(([t, d, c], i) => {
    const y = 5.0 + i * 0.5;
    s.addShape(pres.ShapeType.ellipse, { x: 7.05, y: y + 0.09, w: 0.14, h: 0.14,
      fill: { color: c }, line: { color: c, width: 1 } });
    s.addText(t, { x: 7.3, y, w: 2.2, h: 0.32, fontSize: 11, bold: true, color: WHITE,
      fontFace: B, margin: 0 });
    s.addText(d, { x: 9.5, y, w: 3.0, h: 0.32, fontSize: 10, color: FOG, fontFace: B, margin: 0 });
  });
  s.addText("阻塞式 modal 僅保留給真正需要立即人工決策的情況。", { x: 7.05, y: 6.55,
    w: 5.4, h: 0.26, fontSize: 10, color: SLATE, fontFace: B, margin: 0 });
  s.addNotes("使用者流程是官方指定必備章節。重點是「人一直在迴圈裡」。");
}

/* ========== 12. Dashboard 設計 ========== */
{
  const s = S();
  eyebrow(s, "DASHBOARD 設計 · 加分項目");
  title(s, "指揮駕駛艙：一張常駐地圖，四個工作層級");
  sub(s, "指揮中心固定不捲動、地圖永遠在視線內；完整資料與稽核紀錄分流到專屬頁面，不干擾即時處置。", 1.35);

  const pages = [
    ["總覽", "系統入口", "線框地球標示戰場座標，統計資料一眼掌握規模"],
    ["指揮中心", "現在要處理什麼", "常駐地圖 · 城市狀態列 · 右側情境抽屜（事件／決策／通知／證據）· 底部時間條"],
    ["監測中心", "哪裡正在變差", "全路段與場站表格、飽和度趨勢圖、預警流、資源庫存"],
    ["紀錄與驗證", "決策依據是什麼", "統一系統紀錄、事件可信度、資料佐證與引擎常數"],
    ["顧問對話", "我可以問什麼", "Tool-Calling Agent 對話，工具軌跡即時顯示"],
    ["民眾端", "市民收到什麼", "PWS 細胞廣播手機模擬，四語疏散指示"]];
  pages.forEach(([t, q, d], i) => {
    const x = 0.6 + (i % 3) * 4.07;
    const y = 1.95 + Math.floor(i / 3) * 1.75;
    card(s, x, y, 3.85, 1.58, i === 1 ? "0C1A28" : CARD, i === 1 ? "12385C" : BORDER);
    s.addText(q, { x: x + 0.28, y: y + 0.14, w: 3.3, h: 0.24, fontSize: 9.5, bold: true,
      color: i === 1 ? BLUE : SLATE, fontFace: B, charSpacing: 1, margin: 0 });
    s.addText(t, { x: x + 0.28, y: y + 0.4, w: 3.3, h: 0.34, fontSize: 16, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: x + 0.28, y: y + 0.78, w: 3.35, h: 0.72, fontSize: 10.5, color: FOG,
      fontFace: B, lineSpacing: 14, margin: 0 });
  });

  card(s, 0.6, 5.5, 12.1, 1.1, CARD2);
  s.addText("視覺語言", { x: 0.9, y: 5.62, w: 2, h: 0.28, fontSize: 12.5, bold: true,
    color: WHITE, fontFace: H, margin: 0 });
  s.addText("近黑四層表面搭配單一操作藍（#007AFC），讓地圖成為畫面唯一光源；語意色刻意保留——紅為緊急、橘為注意、綠為已處置——因為災害指揮系統必須讓使用者一眼辨識嚴重程度。動效服務於理解：事件擴散 pulse、路段顏色平滑過渡、未讀預警低頻呼吸而非閃爍。",
    { x: 2.9, y: 5.6, w: 9.55, h: 0.9, fontSize: 11, color: FOG, fontFace: B,
      lineSpacing: 16, margin: 0 });
  s.addNotes("這頁順便回答「為什麼不用單一色系」——因為安全系統的可讀性優先於美學純度。這是專業判斷，不是妥協。");
}

/* ========== 13. 資源調度 ========== */
{
  const s = S();
  eyebrow(s, "指揮能力 · RESOURCE ORCHESTRATION");
  title(s, "會搶佔、會回填、可以被拒絕");
  sub(s, "真實指揮中心的資源永遠不夠。系統的價值不在假裝資源充足，而在把衝突攤開讓人決策。", 1.35);

  const cap = [["優先權感知", "每筆調度帶事件嚴重度優先級", "Critical › High › Medium › Low"],
               ["缺口誠實回報", "資源不足時絕不標示任務完成", "回報缺口數量並要求人工升級"],
               ["抽調需人工核准", "僅允許高優先抽調低優先", "來源與目標雙邊寫入稽核"],
               ["釋出自動回填", "拒絕或降級釋出的資源", "依優先權回填其他事件缺口"]];
  cap.forEach(([t, d, e], i) => {
    const x = 0.6 + i * 3.07;
    card(s, x, 1.9, 2.85, 1.5);
    s.addText(t, { x: x + 0.22, y: 2.04, w: 2.45, h: 0.3, fontSize: 13, bold: true,
      color: WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: x + 0.22, y: 2.38, w: 2.45, h: 0.5, fontSize: 10, color: FOG,
      fontFace: B, lineSpacing: 13, margin: 0 });
    s.addText(e, { x: x + 0.22, y: 2.94, w: 2.45, h: 0.36, fontSize: 9, color: BLUE,
      fontFace: B, lineSpacing: 11, margin: 0 });
  });

  s.addText("實測情境：三起事件併發，警力總量 12 人", { x: 0.6, y: 3.62, w: 8, h: 0.34,
    fontSize: 16, bold: true, color: WHITE, fontFace: H, margin: 0 });

  const sc = [["松高路號誌故障", "Medium", "3 路口 × 2 人 = 6", GREEN],
              ["光復南路塌陷", "Critical", "封鎖 2 + 淨空 2 = 4", RED],
              ["基隆路一段事故", "Critical", "需 4 人，僅餘 2 → 缺口 2", RED]];
  sc.forEach(([t, sev, n, c], i) => {
    const y = 4.08 + i * 0.72;
    card(s, 0.6, y, 5.95, 0.62);
    s.addText(t, { x: 0.85, y, w: 2.4, h: 0.62, fontSize: 11.5, bold: true, color: WHITE,
      fontFace: B, valign: "middle", margin: 0 });
    s.addShape(pres.ShapeType.roundRect, { x: 3.3, y: y + 0.18, w: 0.95, h: 0.26,
      rectRadius: 0.04, fill: { color: CARD2 }, line: { color: c, width: 1 } });
    s.addText(sev, { x: 3.3, y: y + 0.18, w: 0.95, h: 0.26, fontSize: 9, color: c,
      fontFace: M, align: "center", valign: "middle", margin: 0 });
    s.addText(n, { x: 4.4, y, w: 2.0, h: 0.62, fontSize: 10.5, color: FOG, fontFace: B,
      valign: "middle", margin: 0 });
  });

  card(s, 6.75, 4.08, 5.95, 1.98, "0C1A28", "12385C");
  s.addText("系統提案，指揮官決策", { x: 7.05, y: 4.22, w: 5, h: 0.28, fontSize: 12.5,
    bold: true, color: BLUE, fontFace: H, margin: 0 });
  s.addText([
    { text: "系統偵測缺口後主動提出：\n", options: { color: FOG } },
    { text: "「可抽調建議：自 TPE_2026_EVT_003（Medium）\n抽調 2 單位，需指揮官核准」\n\n", options: { color: WHITE } },
    { text: "核准後 → 目標事件補滿、來源事件標記遭抽調並回報新缺口、\n庫存守恆可驗算、雙邊稽核入鏈。", options: { color: FOG } }],
    { x: 7.05, y: 4.55, w: 5.4, h: 1.4, fontSize: 10.5, fontFace: B, lineSpacing: 15.5, margin: 0 });
  s.addNotes("這頁展示的是「指揮官感」。系統不會假裝資源夠，也不會自作主張搶資源——它把選擇權交給人，但把選項算好。");
}

/* ========== 14. 多語與民眾端 ========== */
{
  const s = S();
  eyebrow(s, "商業應用性 · 國際化與人性化（含日韓加分）");
  title(s, "從指揮中心，一路閉環到市民手機");
  sub(s, "通報不只是「生成文字」，而是一條有核准、有送達、有重試的完整生命週期。", 1.35);

  const langs = [["繁體中文", "光復南路封閉，請改道 市民大道四段，預計延誤 90 分鐘。"],
                 ["English", "Guangfu S. Rd. is closed. Please detour via Civic Blvd. Sec. 4. Expected delay: 90 minutes."],
                 ["日本語", "光復南路は通行止めです。市民大道四段へ迂回してください。予想遅延：約 90 分。"],
                 ["한국어", "광복남로가 통제 중입니다. 시민대로 4단으로 우회하시기 바랍니다. 예상 지연: 약 90분."]];
  langs.forEach(([l, t], i) => {
    const y = 1.92 + i * 0.83;
    card(s, 0.6, y, 8.0, 0.72);
    s.addText(l, { x: 0.85, y, w: 1.5, h: 0.72, fontSize: 11.5, bold: true, color: BLUE,
      fontFace: B, valign: "middle", margin: 0 });
    s.addText(t, { x: 2.4, y: y + 0.04, w: 6.0, h: 0.64, fontSize: 10, color: FOG,
      fontFace: B, lineSpacing: 13, valign: "middle", margin: 0 });
  });
  s.addText("四語皆由 LLM 在地化生成（非逐字翻譯），並經數字不變性檢查：時間戳與延誤分鐘數必須原樣出現在每一語言。",
    { x: 0.6, y: 5.3, w: 8.0, h: 0.5, fontSize: 10.5, color: SLATE, fontFace: B,
      lineSpacing: 14, margin: 0 });

  // 手機
  s.addShape(pres.ShapeType.roundRect, { x: 9.05, y: 1.92, w: 2.15, h: 4.35,
    rectRadius: 0.22, fill: { color: "000000" }, line: { color: "333943", width: 2 } });
  s.addShape(pres.ShapeType.roundRect, { x: 9.2, y: 2.3, w: 1.85, h: 1.65,
    rectRadius: 0.1, fill: { color: "18181B" }, line: { color: RED, width: 2 } });
  s.addText("⚠ 緊急警報", { x: 9.3, y: 2.4, w: 1.65, h: 0.26, fontSize: 9.5, bold: true,
    color: RED, fontFace: B, margin: 0 });
  s.addText("光復南路封閉，請改道市民大道四段，預計延誤 90 分鐘。", { x: 9.3, y: 2.72,
    w: 1.65, h: 0.85, fontSize: 8, color: "F1F5F9", fontFace: B, lineSpacing: 11, margin: 0 });
  s.addText("我知道了", { x: 9.3, y: 3.62, w: 1.65, h: 0.24, fontSize: 8, color: WHITE,
    fontFace: B, align: "center", margin: 0 });
  s.addText("細胞廣播簡訊\n四語可切換檢視", { x: 9.2, y: 4.15, w: 1.85, h: 0.5, fontSize: 9,
    color: SLATE, fontFace: B, align: "center", lineSpacing: 12, margin: 0 });

  card(s, 11.45, 1.92, 1.25, 4.35, CARD2);
  s.addText("生命週期", { x: 11.55, y: 2.05, w: 1.05, h: 0.24, fontSize: 9, bold: true,
    color: SLATE, fontFace: B, margin: 0 });
  ["草稿生成", "待人工核准", "已核准", "發送中", "部分送達", "重試", "全數確認"].forEach((t, i) => {
    const y = 2.42 + i * 0.52;
    const c = i === 1 ? AMBER : i === 4 ? RED : i === 6 ? GREEN : SLATE;
    s.addShape(pres.ShapeType.ellipse, { x: 11.58, y: y + 0.06, w: 0.11, h: 0.11,
      fill: { color: c }, line: { color: c, width: 1 } });
    s.addText(t, { x: 11.75, y, w: 0.9, h: 0.24, fontSize: 8.5, color: i === 1 ? WHITE : FOG,
      fontFace: B, margin: 0 });
  });

  card(s, 0.6, 5.92, 8.0, 0.72, CARD2);
  s.addText("關鍵設計：LLM 不能直接發布。通報生成後進入「待核准」，指揮官核准才會發送；失敗通道可單獨重試，送達率即時顯示。",
    { x: 0.85, y: 5.92, w: 7.6, h: 0.72, fontSize: 10.5, color: FOG, fontFace: B,
      valign: "middle", lineSpacing: 14, margin: 0 });
  s.addNotes("民眾端是全場最有畫面的部分。Demo 時把手機模擬開在第二視窗，核准通報的瞬間切過去看警報跳出來。");
}

/* ========== 15. AWS 架構 ========== */
{
  const s = S();
  eyebrow(s, "部署架構 · AWS REFERENCE ARCHITECTURE");
  title(s, "AWS 部署架構");
  sub(s, "以託管服務為主，降低維運負擔；AI 推論走 Amazon Bedrock，資料與稽核紀錄留在客戶帳戶內。", 1.35);

  const layer = (x, y, w, h, t, c) => {
    card(s, x, y, w, h, CARD, c === BLUE ? "12385C" : BORDER);
    s.addText(t, { x: x + 0.18, y: y + 0.1, w: w - 0.3, h: 0.24, fontSize: 9.5, bold: true,
      color: c, fontFace: B, charSpacing: 1, margin: 0 });
  };
  const svc = (x, y, w, name, desc) => {
    card(s, x, y, w, 0.62, CARD2);
    s.addText(name, { x: x + 0.15, y: y + 0.07, w: w - 0.3, h: 0.24, fontSize: 10.5,
      bold: true, color: WHITE, fontFace: B, margin: 0 });
    s.addText(desc, { x: x + 0.15, y: y + 0.31, w: w - 0.3, h: 0.24, fontSize: 8.5,
      color: FOG, fontFace: B, margin: 0 });
  };

  layer(0.6, 1.9, 3.85, 1.85, "前端 · 靜態託管", BLUE);
  svc(0.78, 2.25, 3.5, "Amazon S3", "React 打包產物");
  svc(0.78, 2.98, 3.5, "Amazon CloudFront", "全球快取與 HTTPS");

  layer(4.72, 1.9, 3.85, 1.85, "應用層 · 容器", BLUE);
  svc(4.9, 2.25, 3.5, "AWS App Runner / ECS Fargate", "FastAPI 決策引擎");
  svc(4.9, 2.98, 3.5, "API Gateway (WebSocket)", "Dashboard 即時推送");

  layer(8.85, 1.9, 3.85, 1.85, "AI 推論", BLUE);
  svc(9.03, 2.25, 3.5, "Amazon Bedrock", "Claude 摘要 / 多語 / Agent");
  svc(9.03, 2.98, 3.5, "Guardrail 層（自建）", "必含 token 驗證與降級");

  layer(0.6, 3.92, 6.03, 1.85, "資料與稽核", GREEN);
  svc(0.78, 4.27, 2.75, "Amazon S3", "原始資料集與版本");
  svc(3.7, 4.27, 2.75, "Amazon RDS (PostgreSQL)", "事件狀態 / 決策紀錄");
  svc(0.78, 5.0, 5.67, "AWS Secrets Manager", "模型金鑰與外部憑證集中管理");

  layer(6.85, 3.92, 5.85, 1.85, "排程與觀測", AMBER);
  svc(7.03, 4.27, 2.7, "Amazon EventBridge", "時序播放 / 定時監測");
  svc(9.87, 4.27, 2.7, "Amazon CloudWatch", "延遲 / 錯誤 / 用量");
  svc(7.03, 5.0, 5.54, "AWS WAF + IAM", "存取控制與角色權限分離");

  card(s, 0.6, 5.94, 12.1, 0.78, CARD2);
  s.addText("設計考量", { x: 0.9, y: 5.94, w: 1.5, h: 0.78, fontSize: 11.5, bold: true,
    color: WHITE, fontFace: H, valign: "middle", margin: 0 });
  s.addText("決策引擎為無狀態容器，可水平擴展；LLM 推論與決策運算解耦，模型故障不影響判定輸出；所有稽核資料留存於客戶 VPC 內的 RDS，符合公部門資料落地要求。",
    { x: 2.4, y: 5.94, w: 10.05, h: 0.78, fontSize: 10.5, color: FOG, fontFace: B,
      valign: "middle", lineSpacing: 14, margin: 0 });
  s.addNotes("架構重點：LLM 是可替換元件，不是單點依賴。這對公部門採購很重要——不會被單一模型供應商綁死。");
}

/* ========== 16. 完成度 ========== */
{
  const s = S();
  eyebrow(s, "完成度 · ENGINEERING QUALITY");
  title(s, "可重現、可驗證、可交付");
  sub(s, "不是 Demo 當天能跑就好，而是任何人 clone 下來都能重現同樣的結果。", 1.35);

  const kpi = [["105", "自動化測試", "全數通過 · 2.4 秒"], ["33", "API 端點", "含決策鏈與稽核查詢"],
               ["7,100+", "程式行數", "前端 3,394 / 後端 3,713"], ["< 15s", "端到端延遲", "含兩次 LLM 生成"]];
  kpi.forEach(([n, l, d], i) => {
    const x = 0.6 + i * 3.07;
    card(s, x, 1.9, 2.85, 1.4);
    s.addText(n, { x: x + 0.22, y: 2.03, w: 2.45, h: 0.58, fontSize: 30, bold: true,
      color: BLUE, fontFace: H, margin: 0 });
    s.addText(l, { x: x + 0.22, y: 2.62, w: 2.45, h: 0.26, fontSize: 12, bold: true,
      color: WHITE, fontFace: B, margin: 0 });
    s.addText(d, { x: x + 0.22, y: 2.88, w: 2.45, h: 0.26, fontSize: 9.5, color: SLATE,
      fontFace: B, margin: 0 });
  });

  s.addText("測試覆蓋：官方測試案例逐項落地", { x: 0.6, y: 3.52, w: 8, h: 0.34,
    fontSize: 16, bold: true, color: WHITE, fontFace: H, margin: 0 });

  const t = [["規則引擎", "分級邊界 0.84 / 0.85 / 0.95、BL17 門檻、漫遊 30%、大巨蛋雙條件"],
             ["路徑引擎", "容量 999 排除、非相交排除、下游不得為主疏散、壅塞仍保留並加註"],
             ["ETE 計算", "Critical+0.5=60、High+0.8=58、懲罰不為負、後端保留原值 UI 四捨五入"],
             ["調度彈性", "配置扣量、缺口回報、高搶低限制、雙邊稽核、釋出回填"],
             ["LLM 護欄", "數值竄改攔截、多語缺字攔截、編造 ID 拒絕、強制人工核准"],
             ["端到端場景", "三起官方事件完整流程、What-if Sandbox 不汙染正式狀態"]];
  t.forEach(([n, d], i) => {
    const x = 0.6 + (i % 2) * 6.15;
    const y = 3.98 + Math.floor(i / 2) * 0.78;
    card(s, x, y, 5.95, 0.68);
    s.addText(n, { x: x + 0.22, y, w: 1.3, h: 0.68, fontSize: 11.5, bold: true,
      color: GREEN, fontFace: B, valign: "middle", margin: 0 });
    s.addText(d, { x: x + 1.55, y: y + 0.03, w: 4.25, h: 0.62, fontSize: 9.5, color: FOG,
      fontFace: B, lineSpacing: 12.5, valign: "middle", margin: 0 });
  });
  foot(s, "測試環境強制停用外部 LLM，確保結果確定性；LLM 行為由獨立的 mock 護欄測試覆蓋。");
  s.addNotes("完成度 20% 的評分靠這頁。重點是「可重現」——不是我說它會動，是測試證明它會動。");
}

/* ========== 17. Demo 劇本 ========== */
{
  const s = S();
  eyebrow(s, "現場展示 · DEMO SCRIPT");
  title(s, "90 秒，完整閉環");
  sub(s, "每一段都可由評審當場出題，非預錄流程。", 1.35);

  const demo = [
    ["00:00", "主動監測", "啟動時序播放，系統自動偵測忠孝東路進入 A 級，預警彈窗跳出並附 AI 情勢摘要", BLUE],
    ["00:15", "事件注入", "注入光復南路塌陷，地圖聚焦、事故點擴散、受影響路段轉紅", RED],
    ["00:30", "決策生成", "主疏散路徑、排除理由、ETE 90 分鐘、警力需求一次呈現，可展開查看證據", AMBER],
    ["00:45", "資源衝突", "第三起 Critical 事件出現缺口，系統提出抽調建議，指揮官一鍵核准", AMBER],
    ["01:00", "多語通報", "四語內容生成後待核准，核准並發布；SMS 通道失敗，此時民眾端尚未收到警報", GREEN],
    ["01:15", "民眾接收", "重試失敗通道成功送達，民眾端手機才跳出疏散指示，可切換四語檢視", GREEN],
    ["01:30", "評審提問", "顧問對話現場出題，Agent 自主呼叫工具查證後引用 SOP 條款回答", BLUE]];
  demo.forEach(([t, n, d, c], i) => {
    const y = 1.88 + i * 0.68;
    card(s, 0.6, y, 12.1, 0.6);
    s.addText(t, { x: 0.85, y, w: 0.85, h: 0.62, fontSize: 11, bold: true, color: c,
      fontFace: M, valign: "middle", margin: 0 });
    s.addText(n, { x: 1.85, y, w: 1.9, h: 0.62, fontSize: 12, bold: true, color: WHITE,
      fontFace: H, valign: "middle", margin: 0 });
    s.addText(d, { x: 3.9, y: y + 0.03, w: 8.5, h: 0.56, fontSize: 10.5, color: FOG,
      fontFace: B, valign: "middle", lineSpacing: 13, margin: 0 });
  });
  card(s, 0.6, 6.92, 12.1, 0.0);
  s.addText("全程可暫停、可回放、可由評審指定任一時間點重跑；What-if 問答不影響正式狀態。",
    { x: 0.6, y: 6.88, w: 12.1, h: 0.3, fontSize: 10.5, color: SLATE, fontFace: B, margin: 0 });
  s.addNotes("Demo 節奏控制在 90 秒內，留時間給提問。最後一段刻意留白讓評審出題，展示 Agent 的自主性。");
}

/* ========== 18. 結語 ========== */
{
  const s = S();
  [[3.05, "0A2942"], [2.35, "0C3557"], [1.7, "0E4373"]].forEach(([r, c]) => {
    s.addShape(pres.ShapeType.ellipse, { x: 11.3 - r, y: 3.9 - r, w: r * 2, h: r * 2,
      fill: { color: BG }, line: { color: c, width: 1 } });
  });

  eyebrow(s, "為什麼是我們 · WHY CITYSENTINEL");
  title(s, "把 AI 放在對的位置", 0.68, 36);
  s.addText("讓語言模型做它擅長的事——理解與表達；讓程式做它必須負責的事——判定與計算；\n讓指揮官做只有人能做的事——承擔決策。",
    { x: 0.6, y: 1.45, w: 9.2, h: 0.8, fontSize: 14, color: FOG, fontFace: B,
      lineSpacing: 22, margin: 0 });

  const pil = [["技術可行性", "SOP 判定、路徑篩選、ETE 全部可重算，105 項測試守住每一個邊界條件；資料來源附雜湊值，評審可自行驗算。"],
               ["主題切合度", "系統主動監測並預警，而非被動等待查詢；Tool-Calling Agent 自主查證後引用條款回答，工具軌跡即時可見。"],
               ["落地可行性", "AI 推論可替換、稽核資料留在客戶帳戶、人工核准不可繞過——具備進入公部門正式環境的治理條件。"]];
  pil.forEach(([t, d], i) => {
    const y = 2.55 + i * 1.28;
    card(s, 0.6, y, 8.9, 1.15, i === 0 ? "0C1A28" : CARD, i === 0 ? "12385C" : BORDER);
    s.addText(t, { x: 0.9, y: y + 0.14, w: 2.4, h: 0.3, fontSize: 14.5, bold: true,
      color: i === 0 ? BLUE : WHITE, fontFace: H, margin: 0 });
    s.addText(d, { x: 0.9, y: y + 0.48, w: 8.3, h: 0.6, fontSize: 11, color: FOG,
      fontFace: B, lineSpacing: 15, margin: 0 });
  });

  s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 6.5, w: 8.9, h: 0.56, rectRadius: 0.1,
    fill: { color: "0A1F33" }, line: { color: BLUE_DK, width: 1 } });
  s.addText("下一步：接入即時資料源、擴充至全市路網、加入跨災害調度（積水／地震／停電）",
    { x: 0.85, y: 6.5, w: 8.4, h: 0.56, fontSize: 11, color: BLUE, fontFace: B,
      valign: "middle", margin: 0 });
  s.addNotes("收尾：不要承諾我們做不到的。誠實說明現況與延伸路線，比誇大更能建立信任。");
}

pres.writeFile({ fileName: "C:\\Users\\LIYUN\\Desktop\\hackathon\\docs\\CitySentinel_提案簡報.pptx" })
  .then(f => console.log("OK:", f));
