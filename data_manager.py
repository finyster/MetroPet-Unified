import requests
import pandas as pd
from datetime import datetime
from email.utils import formatdate
from hashlib import sha1
import hmac
import base64

# 從設定檔導入變數
import config

class TDXManager:
    """
    負責處理所有與交通部 TDX 平台的 API 互動。
    包含取得認證、發送請求等。
    """
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = self._get_access_token()

    def _get_access_token(self):
        """
        向 TDX 認證伺服器請求 access token。
        """
        if not self.client_id or not self.client_secret:
            return None
        try:
            auth_response = requests.post(
                config.TDX_AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
            )
            auth_response.raise_for_status()
            return auth_response.json().get("access_token")
        except requests.RequestException as e:
            print(f"錯誤：無法取得 TDX Access Token: {e}")
            return None

    def get_api_data(self, api_url):
        """
        使用 access token 呼叫指定的 TDX API。
        """
        if not self.access_token:
            print("錯誤：沒有有效的 TDX Access Token。")
            return None
        try:
            response = requests.get(
                api_url,
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"錯誤：呼叫 TDX API 失敗: {e}")
            # 如果 token 過期 (401)，可以嘗試重新獲取
            if e.response and e.response.status_code == 401:
                print("Token 可能已過期，正在嘗試重新獲取...")
                self.access_token = self._get_access_token()
                if self.access_token:
                    return self.get_api_data(api_url) # 重試一次
            return None

    # --- 具體的 API 呼叫函式 ---

    def get_mrt_network(self):
        """取得臺北捷運路網資料"""
        url = f"{config.TDX_API_BASE_URL}/v2/Rail/Metro/Network/TRTC"
        return self.get_api_data(url)

    def get_realtime_arrivals(self, station_id: str):
        """
        取得特定車站的即時到站資訊
        注意：TDX 的北捷資料是「即將到站」時才會顯示，非預測
        """
        url = f"{config.TDX_API_BASE_URL}/v2/Rail/Metro/LiveBoard/TRTC/{station_id}"
        return self.get_api_data(url)

    def get_mrt_fare(self, start_station_id: str, end_station_id: str):
        """取得起迄站間的票價"""
        # 注意：參數名稱 (OriginStationID, DestinationStationID) 是根據社群範例推斷，
        # 最終需以您登入 TDX 平台後看到的文件為準。
        url = f"{config.TDX_API_BASE_URL}/v2/Rail/Metro/ODFare/TRTC?$filter=OriginStationID eq '{start_station_id}' and DestinationStationID eq '{end_station_id}'&$format=JSON"
        return self.get_api_data(url)

def load_crowd_flow_data():
    """
    從本地端 CSV 檔案載入人流資料。
    這是您可以優先實作的功能。
    """
    try:
        df = pd.read_csv(config.CROWD_FLOW_CSV_PATH)
        # 在這裡可以先做一些基本的資料前處理
        print("人流資料 CSV 載入成功。")
        return df
    except FileNotFoundError:
        print(f"錯誤：找不到人流資料檔案於 {config.CROWD_FLOW_CSV_PATH}")
        return None

# --- 建立單例 (Singleton) ---
# 確保整個應用程式只會有一個 TDXManager 實例，避免重複獲取 token
tdx_manager = TDXManager(config.TDX_CLIENT_ID, config.TDX_CLIENT_SECRET)