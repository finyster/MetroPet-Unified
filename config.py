# config.py

import os
from dotenv import load_dotenv

# 從 .env 檔案載入環境變數
load_dotenv()

# --- API Keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY") # 主要使用的金鑰
# 從環境變數中取得 Gemini API 金鑰 (已統一)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 從環境變數中取得 TDX API 的 Client ID 和 Secret (已統一)
TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

# --- Data Paths ---
# 定義資料檔案的路徑 (未來會用到)
STATION_DATA_PATH = "data/mrt_station_info.json" # 新增：存放站名與ID對照表
CROWD_FLOW_CSV_PATH = "data/metro_crowd_flow.csv"
INTENT_MODEL_PATH = "models/fasttext_intent.bin"
CROWD_MODEL_PATH = "models/xgboost_crowd_model.json"

# --- TDX API Endpoints ---
# 統一定義 TDX API 的相關 URL
TDX_AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
TDX_API_BASE_URL = "https://tdx.transportdata.tw/api/basic"

# --- 檢查金鑰是否存在 ---
if not GEMINI_API_KEY:
    print("警告：缺少 GEMINI_API_KEY。請檢查您的 .env 檔案。AI Agent 將無法運作。")

if not TDX_CLIENT_ID or not TDX_CLIENT_SECRET:
    print("警告：缺少 TDX_CLIENT_ID 或 TDX_CLIENT_SECRET。請檢查您的 .env 檔案。TDX 相關功能將無法運作。")