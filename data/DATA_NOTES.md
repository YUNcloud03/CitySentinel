# 資料版本紀錄

## Authoritative source

`data/raw/` 內全部檔案複製自主辦方官方資料夾：
`Downloads\(中華電信) 命題文件集 - 2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽\中華電信資料集\`

系統一律只讀取 `data/raw/`，禁止讀取 Downloads 內的散落副本。

## road_network_geometry.json 版本差異

主辦方檔案提供的是 15 個路段 ID、道路名稱、相交道路與容量等拓樸屬性，
本身不含座標。地圖線位因此由臺北市官方道路 GIS 重建，而非宣稱為主辦方提供的
中心線。`RD_TPE_012` 在主辦方資料中名稱為「敦化南路二段」，但相交道路寫成
「仁愛路四段、信義路五段」；該區間依官方路名其實屬敦化南路一段。地圖採官方
實際分段：一段補至信義路官方號誌點，二段則由信義路向南完整呈現；競賽交通值
仍保留原本的 `RD_TPE_006`／`RD_TPE_012` ID。

### 版本更新：2026-08-02 主辦方釋出新版路網

主辦方於 2026-08-02 更新 `road_network_geometry.json`。新版與前一版的**唯一**差異
是 3 條路段的 `intersections` 排列順序（順序代表上游→下游，會參與上下游判定）；
路段數、`capacity_vph`、`alternatives`、`nearby_stations` 全部未變。

| 路段 | 前一版 | 新版（現行採用） |
|---|---|---|
| RD_TPE_001 忠孝東路四段 | 光復南路→延吉街→基隆路一段 | 延吉街→光復南路→基隆路一段 |
| RD_TPE_011 松壽路 | 基隆路一段→松智路→市府路 | 基隆路一段→市府路→松智路 |
| RD_TPE_013 信義路五段 | 基隆路一段→松智路→市府路 | 基隆路一段→市府路→松智路 |

**換版影響實測（換檔後逐項驗證，結論：決策輸出零變動）**

- 對全部 15 個路段執行 `routing_engine.plan_evacuation`，比對事故路口定位、主要
  路線、次要路線三項輸出 —— 15/15 完全一致。
- 對 `live_incidents.json` 的 3 筆事件（帶 `location` 文字，會與 intersections
  逐項比對）重跑 —— 輸出一致；核心 Demo 事件 `TPE_2026_ACC_001`（RD_TPE_002
  光復南路）的 intersections 本就兩版相同。
- 後端測試 187 項：僅 1 項因釘住舊 SHA256 而失敗，已更新為新值；其餘全過。

原因是這 3 條路段的重排並未改變「事故路口位於序列何處」的相對關係，因此上游
候選集合不變。此結論為換版當下的實測記錄，若日後資料再更新須重跑同一組比對。

SHA256（現行採用版）：
`741D253538AAF2BB25C60DEC9D4A8E8DEFECC27112FA09C7A9F1512ADB286B18`

SHA256（前一版，僅供追溯）：
`05FE3CAF3834819E5C12018953502B582ECE6178639635FA600DE8D935054758`

## 清洗規則

- `signaling_crowd_density.csv` 的 `Roaming_User_Pct` 為帶 `%` 字串（如 `"40%"`），
  載入時清洗為 float（40.0），見 `backend/app/data_loader.py:_parse_pct`。
- 所有時間欄位統一以 `YYYY-MM-DD HH:MM` 解析為 datetime。

## 地圖交通設施圖層

- `frontend/src/data/roads.json`：主辦方的 15 個 `RD_TPE_xxx` 路段識別與交通數據，
  搭配臺北市政府工務局新建工程處「臺北市寬度超過8公尺道路GIS圖資」重建線位。
  線上的節點使用官方道路區塊標示點，路口端點再以官方號誌座標校正；可使用
  `scripts/import_road_geometry.py` 從 `data/raw/taipei_roads_over_8m.zip` 重新產生。
- `frontend/public/data/crosswalks.geojson`：臺北市交通管制工程處行人穿越線
  Shapefile 的六個圖層合併結果，共 19,643 筆 Polygon。匯入時由 TWD97 / TM2
  zone 121（EPSG:3826）轉成 WGS84（EPSG:4326），只保留顯示所需欄位。
- `frontend/public/data/cms.geojson`：資訊可變標誌 CMS 官方靜態 XML 快照，共
  178 筆 Point；來源 URL 與更新時間保存在 GeoJSON `metadata`。
- 兩份檔案可使用 `scripts/import_map_assets.py` 重新產生；Shapefile 的 `.shp`、
  `.shx`、`.dbf`、`.prj`、`.cpg` 必須成組保存。
- `frontend/public/data/signals.geojson`：從臺北市政府交通局 2025-06-09 更新的
  2,372 筆路口時制號誌中，以道路名稱及距官方校正路段 75 公尺內為條件篩出 47 筆
  官方點位。設備編號、路口名稱、群組與時制報表網址均保留，可使用
  `scripts/import_signal_assets.py` 重新產生。
- 號誌 CSV 是靜態設備與時制資料，不是即時燈相介面；前端紅黃綠狀態及倒數仍屬
  決策沙盒模擬，並與「官方點位」分開標示。
