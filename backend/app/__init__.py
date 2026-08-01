"""CitySentinel backend package。

匯入時載入專案根目錄的 .env——API 與測試都經由 app.* 進入，在此載入可確保
金鑰在 llm.client 偵測 provider 之前就已就位（否則 .env 等於沒作用）。
已存在的環境變數優先（override=False），CI／容器可直接以真實環境覆寫。
"""
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # 未安裝時靜默略過：改用真實環境變數即可
    pass
else:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
