from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "raw"

TRAFFIC_CSV = DATA_DIR / "city_traffic_flow.csv"
CROWD_CSV = DATA_DIR / "signaling_crowd_density.csv"
ROAD_NETWORK_JSON = DATA_DIR / "road_network_geometry.json"
SOP_TXT = DATA_DIR / "emergency_traffic_sop.txt"
INCIDENTS_JSON = DATA_DIR / "live_incidents.json"

TIME_FMT = "%Y-%m-%d %H:%M"
