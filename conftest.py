import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

# 測試一律停用真 LLM：走確定性 fallback，快速、免費、可重現。
# LLM 路徑的行為由 mock structured_completion 的專屬測試覆蓋。
os.environ.setdefault("CITY_LLM_DISABLED", "1")
