# CitySentinel 城市應變分析 AI Command Center

2026 雲湧智生黑客松（中華電信命題）——智慧交通指揮中樞。
核心原則：**SOP 判定、替代路徑、ETE、What-if 全部即時計算；LLM 只負責解釋與多語文字。**

> 完整技術規格請見 **[docs/SYSTEM_SPECIFICATION.md](docs/SYSTEM_SPECIFICATION.md)**

---

## 快速開始（組員請看這裡）

### 第一次使用：只要跑一次

**在檔案總管中雙擊 `setup.bat`**（或在終端機執行 `.\setup.bat`）

腳本會自動完成：
1. 偵測可用的 Python（需 3.10+）
2. 建立虛擬環境 `.venv`
3. 安裝後端相依套件
4. 安裝前端相依套件

> 沒有 Python？到 [python.org](https://www.python.org/downloads/) 下載 3.11，安裝時**務必勾選 "Add Python to PATH"**。
> 沒有 Node.js？到 [nodejs.org](https://nodejs.org/) 下載 18 以上版本。

### 每次開發：開兩個視窗

| 動作 | 指令 | 網址 |
|---|---|---|
| 啟動後端 API | 雙擊 `start-backend.bat` | http://localhost:8000 |
| 啟動前端 Dashboard | 雙擊 `start-frontend.bat` | http://localhost:5173 |
| 執行測試 | 雙擊 `run-tests.bat` | — |

打開瀏覽器到 **http://localhost:5173** 即可操作。

### 為什麼要用虛擬環境？

一台電腦常裝有多個 Python 版本，直接打 `python` 可能指到**沒有安裝套件的那一個**，出現 `No module named uvicorn` 這類錯誤。
`.venv` 讓專案有自己獨立的套件環境，腳本一律使用 `.venv` 內的 Python，**不受系統 PATH 影響**，組員之間的環境也完全一致。

### 常見問題

| 症狀 | 原因與解法 |
|---|---|
| `No module named uvicorn` | 沒用 `.venv`。請用 `start-backend.bat` 啟動，不要自己打 `python -m uvicorn` |
| 啟動時顯示 **Port 8000 already in use** | 其他程式佔用了 8000。腳本會列出佔用者 PID，關掉它後重試；或改用其他埠：`start-backend.bat 8010`（同時需修改 `frontend/vite.config.ts` 的 proxy 目標） |
| Dashboard 一片空白／資料都是「—」 | 後端沒啟動，或 8000 被**別的專案**佔用。用 `curl http://localhost:8000/api/health` 確認，回應中要有 `"segments":15` 才是本系統 |
| AI 摘要顯示「模板」而非「LLM 生成」 | 未設定 API 金鑰。複製 `.env.example` 為 `.env` 並填入金鑰。**沒有金鑰系統仍可完整運作**，只是文字改由確定性模板產生 |
| 修改程式後畫面沒變 | 後端有 `--reload` 會自動重啟；前端 Vite 有熱更新。若仍無效，重新整理瀏覽器或重啟腳本 |

### 環境變數（選用）

複製 `.env.example` 為 `.env` 後填入金鑰即可啟用 LLM 功能：

```
ANTHROPIC_API_KEY=...     # 優先使用
OPENAI_API_KEY=...        # 次選
```

⚠️ `.env` 已列入 `.gitignore`，**切勿將真實金鑰提交至版控**。

---

## 開發進度

### Phase 1 競賽核心（已完成）

- ✅ 資料層：官方五份資料載入與清洗（`Roaming_User_Pct` % 字串轉數值）
- ✅ Rule Engine：SOP 1–6 確定性判定（含證據數值輸出）
- ✅ Routing Engine：SOP 2 候選篩選（容量 ≥1000、直接相交、上下游判定、排除理由）
- ✅ ETE Calculator：SOP 7 公式（後端保留原值、UI 四捨五入）
- ✅ 閉環 Coordinator：事件狀態機 + KPI 回看 + 未達標自動重規劃 + 現場確認結案，含 decision trace
- ✅ What-if Sandbox：覆寫假設、不動正式狀態
- ✅ 時序播放器：沿資料時間軸推進、自動觸發預警
- ✅ 通報模板：CMS + 中/英/日/韓（LLM fallback 保證）
- ✅ 測試：後端 190 項、前端 11 項全數通過（含閉環狀態、事件生命週期、地理計算與端到端場景）

## Phase 2 進度

- ✅ React + TypeScript + MapLibre Dashboard（`frontend/`）：狀態卡、路段地圖
  （飽和度上色、主/次疏散、封閉路段圖層）、車流/人流清單、自動預警、
  事件注入面板、決策鏈時間軸、What-if 對話
- ✅ What-if 自然語言解析（確定性 regex 版，`/api/what-if/nl`；之後可換 LLM 共用同一 sandbox）

## Phase 3 進度（依評審優化建議）

- ✅ **Resource Registry 與資源調度**：警力/接駁/號誌/北捷資源庫存，依 SOP 與嚴重度
  產生調度需求並扣減可用量；資源不足回報缺口與人工升級，不標示為已完成
- ✅ **規則歸因**：`triggered_rules` 拆成 `caused_by_incident` / `context_rules` /
  `calculation_rules`，避免「路面塌陷觸發大巨蛋散場」這類誤導；調度只看事件造成的規則
- ✅ **可 Challenge 決策**：每個調度動作附證據包（rule_id、snapshot、challenge 問題），
  管理者可接受/拒絕/調整，覆寫寫入決策鏈稽核並保留原始 Agent 建議
- ✅ **ETE 來源明確化**：回應含 `saturation_source_segments` 供評審重算

## Phase 4 進度（推播閉環 + 事件模擬器 + 真 LLM）

- ✅ **推播送達狀態機**：DRAFTED→待核准→核准→發布→送達確認/失敗→重試；
  模擬 Adapter 回傳送達狀態；未核准不得發布（生成 ≠ 送達）
- ✅ **自訂事件模擬器**：Pydantic schema 驗證（路段存在性、enum、時間格式）、
  simulation_run_id 紀錄、走同一套 Coordinator
- ✅ **LLM 層（真接入）**：provider 自動偵測（ANTHROPIC_API_KEY→Claude claude-opus-4-8
  優先，OPENAI_API_KEY 次之，皆無則確定性模板）；AI 交控摘要 + What-if NL 第二層解析；
  Guardrails：structured output schema 驗證、cited_rule_ids 必須是已觸發條款子集、
  編造的站點/路段 ID 一律拒絕、requires_human_approval 強制為 true、
  LLM 失敗一律 fallback 不中斷主流程、LLM 不可直接呼叫發布 API
## Phase 6 進度（五頁資訊架構 + 民眾端 + 緊急彈窗）

- ✅ **五頁 Dashboard**：指揮中心（維持原樣）｜監測中心｜紀錄與驗證｜顧問對話｜民眾端
- ✅ **信心分數**：多源事件可信度（官方來源+車速異常+車道狀態+周邊人流），
  確定性可解釋、附證據清單；僅供參考不參與 SOP 判定
- ✅ **可驗證性資料**：GET /api/provenance（來源檔 SHA256、筆數、全部引擎門檻常數）
- ✅ **顧問對話**：三層路由（What-if regex→LLM 解析 / SOP 條款查詢 / LLM 問答＋guardrail）
- ✅ **緊急彈窗**：A 級壅塞、SOP 3/4 觸發時全域 message box，同實體同規則去重
- ✅ **民眾端手機模擬**：PWS 細胞廣播疏散警報；四語內容可切換檢視（中/英/日/韓）；
  依通報目標區域過濾（範圍外收不到）；僅「簡訊通道實際送達」後才顯示警報——
  CMS（路側看板）送達不代表民眾收到，簡訊失敗時手機不跳警報，重試成功才出現
## Phase 7 進度（官方「由 LLM 生成」三缺口閉合）

- ✅ **預警彈窗摘要由 LLM 生成**（官方模組 1）：彈窗自動載入 AI 情勢分析，門檻判定仍由程式運算
- ✅ **導引文字由 LLM 生成**（官方模組 2）：CMS 文字 LLM 撰寫，經「必含 token」驗證
- ✅ **多語告警文字由 LLM 生成**（官方模組 5）：四語在地化生成（非逐字翻譯）
- ✅ **guardrail 原則：LLM 生文、程式驗數**——路名、ETE 數字、時間戳必須原封不動
  出現在每一語言，缺一即整包退回確定性模板；生成來源（llm:provider / template）
  全程標注於 UI 與決策鏈
- ✅ **LLM 呼叫留痕**：用途/模型/延遲/成敗記入系統紀錄（LLM 分類），補稽核鏈
## Phase 8 進度（顧問對話升級 tool-calling agent）

- ✅ **真正的 LLM agent（諮詢層）**：LLM 在迴圈中自主決定呼叫哪些工具、參數、
  何時停止——`get_sop / get_incident / run_what_if / get_traffic / get_crowd /
  get_resources / get_confidence` 七個工具
- ✅ **物理性安全邊界**：工具允許清單只有唯讀查詢與 What-if sandbox，
  發布/調度/核准的工具不存在；迴圈上限 5 輪；引用條款由工具軌跡推導，
  不信任 LLM 自報
- ✅ **工具軌跡全程可視**：對話中顯示 agent 每一步呼叫（工具、參數、結果摘要），
  每步 LLM 呼叫留痕系統紀錄
- ✅ 雙 provider（Anthropic tool use / OpenAI function calling）；LLM 不可用時
  退回確定性路由
- 架構定位：**決策層＝確定性引擎（LLM 不可觸碰）；諮詢層＝LLM agent（唯讀）**
## Phase 9 進度（調度彈性：優先權 + 搶佔 + 回填）

- ✅ **優先權感知**：每筆調度帶事件嚴重度優先級（Critical>High>Medium>Low）
- ✅ **抽調建議（搶佔）**：資源缺口時自動掃描「較低優先事件」占用的同類資源，
  提出可抽調來源——僅建議，指揮官一鍵核准後執行；嚴格「高搶低」，同級禁止
- ✅ **雙邊稽核**：抽調在來源事件記 DISPATCH_PREEMPTED、目標事件記
  HUMAN_OVERRIDE(op=preempt)，庫存守恆可驗證
- ✅ **釋出回填（再規劃）**：拒絕/調降/重新研判降級釋出的資源，自動依優先權
  回填其他事件缺口（RESOURCE_REBALANCED 入決策鏈，回填後仍待人工核准）
- ✅ 預設警力庫存調為 12（8+4），三起事件併發即可 Demo 資源競爭
## Phase 10 進度（視覺改版：控制室設計系統 + 動效 + 總覽頁）

- ✅ **Mapbox 控制室設計系統**（DESIGN.md）：Void Black 四層表面（#0e1012→#23262d）、
  #007afc Signal Blue 唯一操作色、pill 按鈕/16px 卡片/4px 徽章半徑系統、
  DM Sans + Noto Sans TC、全大寫寬字距眉標、玻璃擬態 sticky header
- ✅ **語意色刻意保留**：紅=緊急/橘=注意/綠=已處置/紫=漫遊——災害系統的
  嚴重度辨識優先於單色美學
- ✅ **系統總覽 landing**：純 Canvas 2D 線框地球（零依賴，非 three.js），
  台北訊號點脈動標記；字元逐一進場標題 + 分段淡入 CTA（motionsites 式）
- ✅ **互動動效**：地圖事件擴散 pulse、路段顏色平滑過渡（700ms）、
  警報右側滑入＋未讀低頻呼吸光、決策鏈逐步展開＋點擊查看證據、
  通報中英日韓切換預覽＋送達率動畫條、狀態卡數字平滑計數、hover 微抬升
- 誠實未做：H3 格網（無資料層，以路段線平滑變色替代）、拖曳資源到地圖
## Phase 11 進度（指揮中心駕駛艙改版，依 UI/UX 規格核心包）

- ✅ **固定工作台 App Shell**：指揮中心整頁不捲動，一張常駐地圖為主視覺，
  只有面板內部捲動（規格 §3/§9）
- ✅ **城市狀態列**：城市警戒/異常路段/進行中事件/ETE/可用警力/通知——僅可決策摘要
- ✅ **右側 Tab 情境抽屜**：事件/決策/通知/證據 分離，新事件自動切到「決策」
- ✅ **Coordinator 一句話決策**（判定/行動/升級條件/依據）——後端確定性稽核產物
- ✅ **五階段決策鏈**（事件驗證→影響評估→方案規劃→資源與核准→通知與追蹤），
  取代工程式 log，可點擊展開內部步驟與證據
- ✅ **分級告警**（規格 §11）：Alert Rail 摘要列（🔴高風險/🟡注意/🔵資訊）不阻塞、
  高風險事件右側滑出快報卡、中央 modal 只留「資源缺口」這類真正需人工決策的情境
- ✅ **底部時間條**：拖曳 seek 車流/地圖快照、事件 marker（誠實：完整狀態回放已descope）
- ✅ **底部抽屜**：預警/決策鏈/What-if 預設收合，點擊拉出，地圖恢復完整高度
- 尚未做：WebSocket 推送（目前輪詢）、H3 影響走廊、完整狀態回放、AWS 部署

## 快速開始

```powershell
# 後端
cd backend
pip install -r requirements.txt
python -m uvicorn app.api.main:app --port 8000

# 前端（另開視窗）
cd frontend
npm install
npm run dev   # http://localhost:5173，/api 自動 proxy 到 8000
```

跑測試（於專案根目錄）：

```powershell
python -m pytest tests -q
```

## 主要 API

| 端點 | 說明 |
|---|---|
| `POST /api/simulation/start` | 啟動時序播放（`speed`、`start_timestamp`） |
| `POST /api/simulation/tick` | 推進一個資料時間點，回傳快照與觸發預警 |
| `POST /api/simulation/pause` / `seek` | 暫停／跳轉 |
| `POST /api/simulation/reset` | 清除本輪事件、調度、通報與救援走廊，回到 21:00 官方資料基準 |
| `POST /api/incidents/inject` | 注入事件（`event_id` 來自 live_incidents.json） |
| `GET /api/incidents/{id}` | 事件完整狀態 |
| `GET /api/incidents/{id}/decision-trace` | 決策鏈（規則、路徑、排除理由、ETE、SOP 原文） |
| `GET /api/incidents/{id}/notifications` | CMS 與多語通報 |
| `POST /api/what-if` | Sandbox 假設分析（結構化 overrides） |
| `POST /api/green-corridor/simulate` | 依路網、車速、官方道路與號誌計算救援綠廊提案 |
| `POST /api/green-corridor/{id}/approve` | 人工核准並啟動模擬號誌優先（不修改正式號誌） |
| `GET /api/green-corridor/runs` | 救援走廊方案與核准紀錄 |
| `GET /api/road-network` / `sop` / `health` | 基礎資料 |

## 已驗證的 Demo 場景

| 場景 | 結果 |
|---|---|
| 主動監測 | 21:00 忠孝東路 B 級、21:30 A 級自動預警 |
| 光復南路塌陷 (ACC_001) | 主疏散＝市民大道四段；延吉街（容量 600）、敦化南路一段（不相交）被排除；仁愛路四段列下游次要；ETE = 90 分 |
| BL17 人群推擠 (EVT_002) | 觸發 SOP 3（31,000 > 25,000）：過站不停／接駁／步行至 BL18；ETE = 70 分 |
| 松高路號誌故障 (EVT_003) | 觸發 SOP 5：人工指揮、每路口 2 警力；ETE = 41 分 |
| 多語通報 | 台北101 漫遊 45% 觸發 SOP 6，中英日韓同步產出 |
| What-if | BL17 覆寫 40,000 人 → sandbox 觸發 SOP 3，正式狀態不變 |
| 救護車綠色走廊 | 避開忠孝東路事故，6 路段、25 個官方號誌；ETA 20 → 10 分，核准前不啟動號誌優先 |
| 決策前後驗證 | ACC_001 注入後處置結果鎖定；人工接受並播放後，速度 1 → 7.3 km/h、ETE 105 → 90 分 |
| 重新開始 | 回到 21:00、事件清空、警力恢復 12/12、情境驗證視圖移除 |

## 專案結構

```
backend/app/
├─ config.py             # 路徑與常數
├─ data_loader.py        # 載入清洗 + 時間切面快照
├─ notifications.py      # CMS 與多語模板（LLM fallback）
├─ engines/
│  ├─ rule_engine.py     # SOP 1–6
│  ├─ routing_engine.py  # SOP 2 疏散路徑
│  └─ ete_calculator.py  # SOP 7
├─ retrievers/sop_retriever.py  # 依 rule_id 精準取 SOP 原文
├─ coordinator/
│  ├─ coordinator.py     # 事件工作流狀態機 + decision trace
│  ├─ green_corridor.py  # 救援路徑、號誌預控、ETA 與四語推播
│  └─ whatif.py          # Sandbox 假設分析
├─ simulation/player.py  # 時序播放器
└─ api/main.py           # FastAPI 端點
data/raw/                # 官方資料（authoritative，見 data/DATA_NOTES.md）
tests/                   # 171 項後端單元＋整合測試（另有前端 10 項 Vitest）
```
