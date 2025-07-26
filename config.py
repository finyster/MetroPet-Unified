import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

# --- 資料庫 (快取) 檔案路徑 ---
STATION_DATA_PATH = os.path.join(DATA_DIR, 'mrt_station_info.json')
FARE_DATA_PATH = os.path.join(DATA_DIR, 'mrt_fare_info.json')
TRANSFER_DATA_PATH = os.path.join(DATA_DIR, 'mrt_transfer_info.json')
EXIT_DATA_PATH = os.path.join(DATA_DIR, 'mrt_station_exits.json')
FACILITIES_DATA_PATH = os.path.join(DATA_DIR, 'mrt_station_facilities.json')
LINE_DATA_PATH = os.path.join(DATA_DIR, 'mrt_lines_info.json') # 新增：路線資料路徑

# 【新】讀取北捷 API 帳密 (如果未來需要，目前未使用)
METRO_API_USERNAME = os.getenv("METRO_API_USERNAME")
METRO_API_PASSWORD = os.getenv("METRO_API_PASSWORD")

if not GROQ_API_KEY: print("警告：缺少 GROQ_API_KEY。")
if not TDX_CLIENT_ID or not TDX_CLIENT_SECRET: print("警告：缺少 TDX API 金鑰。")