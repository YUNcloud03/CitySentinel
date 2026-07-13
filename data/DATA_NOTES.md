# 資料版本紀錄

## Authoritative source

`data/raw/` 內全部檔案複製自主辦方官方資料夾：
`Downloads\(中華電信) 命題文件集 - 2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽\中華電信資料集\`

系統一律只讀取 `data/raw/`，禁止讀取 Downloads 內的散落副本。

## road_network_geometry.json 版本差異

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
