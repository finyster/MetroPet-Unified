import requests
import os
from datetime import datetime, timezone, timedelta
import hmac
from hashlib import sha1
import base64

# TDX 金鑰，建議從環境變數讀取
APP_ID = os.getenv("TDX_APP_ID")
APP_KEY = os.getenv("TDX_APP_KEY")

class TdxApiHandler:
    """處理 TDX API 認證與請求的類別"""
    def __init__(self, app_id, app_key):
        self.app_id = app_id
        self.app_key = app_key
        self.auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
        self.api_base_url = "https://tdx.transportdata.tw/api/basic"
        self.access_token = None
        self.token_expiry = datetime.now(timezone.utc)

    def get_access_token(self):
        """獲取或刷新 access token"""
        if self.access_token and self.token_expiry > datetime.now(timezone.utc) + timedelta(minutes=5):
            return self.access_token

        headers = {'content-type': 'application/x-www-form-urlencoded'}
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.app_id,
            'client_secret': self.app_key
        }
        response = requests.post(self.auth_url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        self.access_token = token_data['access_token']
        # 設置過期時間，並保留5分鐘的緩衝
        self.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])
        print("Successfully obtained new TDX access token.")
        return self.access_token

    def get_data(self, url):
        """發送帶有認證的 GET 請求"""
        token = self.get_access_token()
        headers = {'authorization': f'Bearer {token}'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

# 實例化 API 處理器
tdx_handler = TdxApiHandler(APP_ID, APP_KEY)

def get_route_and_time(origin_station_id: str, destination_station_id: str) -> dict:
    """
    查詢兩捷運站之間的建議搭乘路徑、預估旅程時間與轉乘資訊。
    :param origin_station_id: 起點站的官方車站 ID。
    :param destination_station_id: 終點站的官方車站 ID。
    :return: 包含路徑、時間、票價等資訊的字典。
    """
    url = f"{tdx_handler.api_base_url}/v2/Rail/Metro/StationToStation/TRTC?OriginStationID={origin_station_id}&DestinationStationID={destination_station_id}&$format=JSON"
    return tdx_handler.get_data(url)

def get_fare(origin_station_id: str, destination_station_id: str) -> dict:
    """
    查詢兩捷運站之間的票價資訊。
    :param origin_station_id: 起點站的官方車站 ID。
    :param destination_station_id: 終點站的官方車站 ID。
    :return: 包含不同票種票價的字典。
    """
    url = f"{tdx_handler.api_base_url}/v2/Rail/Metro/ODFare/TRTC?OriginStationID={origin_station_id}&DestinationStationID={destination_station_id}&$format=JSON"
    return tdx_handler.get_data(url)

def get_live_board(station_id: str) -> dict:
    """
    查詢特定捷運站的即時列車到站資訊。注意：此 API 僅在列車進站時才提供資訊。
    :param station_id: 欲查詢車站的官方 ID。
    :return: 包含列車方向、終點站等資訊的字典。
    """
    url = f"{tdx_handler.api_base_url}/v2/Rail/Metro/LiveBoard/TRTC?$filter=StationID eq '{station_id}'&$format=JSON"
    return tdx_handler.get_data(url)

def get_service_alerts() -> list:
    """
    獲取臺北捷運系統的即時營運通阻事件。
    :return: 包含通阻事件說明的列表。
    """
    # 此 API 來自 [8]，假設其為一個公開的 JSON 端點
    url = "https://www.metro.taipei/API/service_alert.json" # 假設的 URL
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return [{"error": f"無法獲取營運通阻資訊: {e}"}]