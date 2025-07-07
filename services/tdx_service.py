# services/tdx_service.py
import requests
import time
from typing import Optional
import config

class TDXQuerier:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: Optional[str] = None
        self.token_expiry_time: int = 0

    def _get_access_token(self) -> Optional[str]:
        if self.access_token and time.time() < self.token_expiry_time - 60:
            return self.access_token
        print("Access Token 過期或不存在，正在重新獲取...")
        headers = {"content-type": "application/x-www-form-urlencoded"}
        data = {"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret}
        try:
            response = requests.post(config.TDX_AUTH_URL, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.token_expiry_time = time.time() + token_data["expires_in"]
            print("成功獲取新的 Access Token！")
            return self.access_token
        except requests.exceptions.RequestException as e:
            print(f"錯誤：無法獲取 Access Token。請檢查您的 TDX Client ID 與 Secret。錯誤詳情: {e}")
            return None

    def get(self, url: str) -> Optional[dict]:
        token = self._get_access_token()
        if not token: return None
        headers = {"authorization": f"Bearer {token}"}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"錯誤：API 請求失敗。URL: {url}, 詳情: {e}")
            return None

    def get_mrt_network(self):
        url = f"{config.TDX_API_BASE_URL}/v2/Rail/Metro/Network/TRTC?$format=JSON"
        return self.get(url)

    def get_mrt_fare(self, start_station_id: str, end_station_id: str):
        url = f"{config.TDX_API_BASE_URL}/v2/Rail/Metro/ODFare/TRTC/{start_station_id}/to/{end_station_id}?$format=JSON"
        return self.get(url)

    def get_realtime_arrivals(self, station_id: str):
        url = f"{config.TDX_API_BASE_URL}/v2/Rail/Metro/LiveBoard/TRTC/{station_id}?$format=JSON"
        return self.get(url)

    def get_station_exits(self, station_id: str):
        url = f"{config.TDX_API_BASE_URL}/v2/Rail/Metro/StationExit/TRTC/{station_id}?$format=JSON"
        return self.get(url)

tdx_api = TDXQuerier(config.TDX_CLIENT_ID, config.TDX_CLIENT_SECRET)