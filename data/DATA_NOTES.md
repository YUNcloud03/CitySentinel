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

Downloads 根目錄另有一份 `road_network_geometry.json` 散檔，與官方資料夾版在
3 條路段的 `intersections` 順序不同（順序代表上游→下游，會影響上下游判定）：

| 路段 | 散檔版 | 官方資料夾版（採用） |
|---|---|---|
| RD_TPE_001 忠孝東路四段 | 延吉街→光復南路→基隆路一段 | 光復南路→延吉街→基隆路一段 |
| RD_TPE_011 松壽路 | 基隆路一段→市府路→松智路 | 基隆路一段→松智路→市府路 |
| RD_TPE_013 信義路五段 | 基隆路一段→市府路→松智路 | 基隆路一段→松智路→市府路 |

採用官方資料夾版為唯一來源。核心 Demo 事件 `TPE_2026_ACC_001`（RD_TPE_002
光復南路）的 intersections 兩版一致，主場景判定不受此差異影響。

SHA256（採用版）：
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
