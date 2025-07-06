import os
from dotenv import load_dotenv

# 從 .env 檔案載入環境變數
load_dotenv()

# --- API Keys ---
# 從環境變數中取得 OpenAI API 金鑰
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 從環境變數中取得 TDX API 的 Client ID 和 Secret
TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

# --- Data Paths ---
# 定義資料檔案的路徑
CROWD_FLOW_CSV_PATH = "data/metro_crowd_flow.csv"
INTENT_MODEL_PATH = "models/fasttext_intent.bin"
CROWD_MODEL_PATH = "models/xgboost_crowd_model.json"

# --- TDX API Endpoints ---
# 統一定義 TDX API 的相關 URL
TDX_AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
TDX_API_BASE_URL = "https://tdx.transportdata.tw/api/basic"

# 檢查金鑰是否存在，如果不存在則給予提示
if not OPENAI_API_KEY or not TDX_CLIENT_ID or not TDX_CLIENT_SECRET:
    print("警告：缺少必要的 API 金鑰。請檢查您的 .env 檔案。")
    print("TDX 相關功能將無法運作。")