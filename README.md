# 城市應變分析 AI Command Center

2026 雲湧智生黑客松（中華電信命題）——智慧交通指揮中樞。
核心原則：**SOP 判定、替代路徑、ETE、What-if 全部即時計算；LLM 只負責解釋與多語文字。**

## 目前進度：Phase 1 競賽核心（已完成）

- ✅ 資料層：官方五份資料載入與清洗（`Roaming_User_Pct` % 字串轉數值）
- ✅ Rule Engine：SOP 1–6 確定性判定（含證據數值輸出）
- ✅ Routing Engine：SOP 2 候選篩選（容量 ≥1000、直接相交、上下游判定、排除理由）
- ✅ ETE Calculator：SOP 7 公式（後端保留原值、UI 四捨五入）
- ✅ Coordinator：事件狀態機 NEW→…→COMPLETED，含 decision trace
- ✅ What-if Sandbox：覆寫假設、不動正式狀態
- ✅ 時序播放器：沿資料時間軸推進、自動觸發預警
- ✅ 通報模板：CMS + 中/英/日/韓（LLM fallback 保證）
- ✅ 測試：30 項全數通過（技術文件 19.1–19.3 + 端到端 Demo 場景）

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
- 尚未做：WebSocket 推送（目前輪詢）、H3 區域風險層、LLM 解釋潤飾、推播送達狀態機、AWS 部署

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
| `POST /api/incidents/inject` | 注入事件（`event_id` 來自 live_incidents.json） |
| `GET /api/incidents/{id}` | 事件完整狀態 |
| `GET /api/incidents/{id}/decision-trace` | 決策鏈（規則、路徑、排除理由、ETE、SOP 原文） |
| `GET /api/incidents/{id}/notifications` | CMS 與多語通報 |
| `POST /api/what-if` | Sandbox 假設分析（結構化 overrides） |
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
│  └─ whatif.py          # Sandbox 假設分析
├─ simulation/player.py  # 時序播放器
└─ api/main.py           # FastAPI 端點
data/raw/                # 官方資料（authoritative，見 data/DATA_NOTES.md）
tests/                   # 30 項單元＋整合測試
```
