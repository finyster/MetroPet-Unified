# services/tdx_service.py 

import requests
import config
import time
import json # 引入 json 模組用於解析錯誤訊息

class TDXApi:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://tdx.transportdata.tw/api/basic"
        self.auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
        self.access_token = None
        # 第一次獲取 Token
        self._get_access_token()

    def _get_access_token(self):
        """獲取 TDX Access Token"""
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        data = {'grant_type': 'client_credentials', 'client_id': self.client_id, 'client_secret': self.client_secret}
        try:
            response = requests.post(self.auth_url, headers=headers, data=data, timeout=20)
            response.raise_for_status()
            print("--- ✅ 成功獲取 TDX Access Token！ ---")
            self.access_token = response.json().get('access_token')
        except requests.RequestException as e:
            print(f"--- ❌ 獲取 Access Token 失敗: {e} ---")
            self.access_token = None
            
    def _get_api_data(self, url: str, retry: int = 5, delay: int = 10):
        """
        【強化版】API 資料獲取函式
        - 增加最大重試次數至 5 次
        - 拉長初始等待時間至 10 秒
        """
        if not self.access_token:
            return None # 如果一開始就沒有 token，直接失敗
        
        headers = {'authorization': f'Bearer {self.access_token}', 'accept': 'application/json'}
        for attempt in range(retry):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                
                # Token 過期處理
                if response.status_code == 401:
                    print("--- ⚠️ Access Token 已過期或無效，正在重新獲取... ---")
                    self._get_access_token()
                    if not self.access_token: return None # 如果重試失敗，則返回
                    headers['authorization'] = f'Bearer {self.access_token}'
                    continue # 重新進行這次請求

                response.raise_for_status() # 檢查其他 HTTP 錯誤
                return response.json()

            except requests.exceptions.HTTPError as e:
                # 專門處理 429 Too Many Requests
                if e.response.status_code == 429:
                    print(f"--- ⚠️ 429 Too Many Requests，等待 {delay} 秒後重試 ({attempt + 1}/{retry}) ---")
                    time.sleep(delay)
                    delay *= 2  # 指數退避，讓等待時間越來越長
                else:
                    print(f"--- ❌ API 請求失敗 (HTTP Error) on URL: {url} ---")
                    try:
                        print(f"--- 錯誤詳情: {e.response.json()} ---")
                    except json.JSONDecodeError:
                        print(f"--- 錯誤詳情 (非 JSON): {e.response.text} ---")
                    return None # 其他 HTTP 錯誤，直接失敗
            except requests.exceptions.RequestException as e:
                print(f"--- ❌ API 請求發生嚴重錯誤 (RequestException) on URL: {url} ---")
                print(f"--- 錯誤詳情: {e} ---")
                return None
        
        print(f"--- ❌ 在 {retry} 次重試後，依然無法從 URL 獲取資料: {url} ---")
        return None

    def _get_all_data_paginated(self, base_url: str, page_size: int = 500):
        """
        【強化版】分頁資料獲取函式
        - 降低單次請求筆數至 500
        - 拉長每次請求間的固定延遲
        """
        all_data = []
        skip = 0
        while True:
            # 組合分頁的 URL
            url_connector = "&" if "?" in base_url else "?"
            paginated_url = f"{base_url}{url_connector}$top={page_size}&$skip={skip}"
            
            print(f"--- 正在請求分頁資料: $top={page_size}, $skip={skip} ... ---")
            page_data = self._get_api_data(paginated_url)
            
            if page_data is None:
                print(f"--- ❌ 分頁請求失敗於 $skip={skip}，將回傳目前已獲取的資料。 ---")
                break # 如果請求失敗，中斷迴圈，返回已有的資料
            
            if not page_data:
                print(f"--- ✅ 已到達資料結尾，總共獲取了 {len(all_data)} 筆資料。 ---")
                # 新增調試打印：如果第一頁就是空的，可能表示 API 根本沒數據
                if not all_data and skip == 0:
                    print(f"--- Debug: First page of data for {base_url} was empty. ---")
                break # 如果回傳的資料為空，表示已經沒有更多資料了
                
            all_data.extend(page_data)
            
            # 如果回傳的資料筆數小於請求的筆數，表示這是最後一頁
            if len(page_data) < page_size:
                print(f"--- ✅ 已獲取最後一頁資料，總共獲取了 {len(all_data)} 筆資料。 ---")
                break
            
            # 準備請求下一頁
            skip += page_size
            # ✨【關鍵】✨ 在每一次成功的分頁請求後，都固定休息一下，這是避免 429 的核心
            time.sleep(1.5) 

        return all_data if all_data else None

    # --- 以下所有 get_... 函式都不需修改，它們會自動繼承強化後的分頁能力 ---

    def get_all_stations_of_route(self):
        url = f"{self.base_url}/v2/Rail/Metro/StationOfRoute/TRTC?$format=JSON"
        return self._get_all_data_paginated(url)

    def get_all_fares(self):
        url = f"{self.base_url}/v2/Rail/Metro/ODFare/TRTC?$format=JSON"
        return self._get_all_data_paginated(url, page_size=1000) # 票價資料可以嘗試用較大的 page_size

    def get_line_transfer_info(self):
        url = f"{self.base_url}/v2/Rail/Metro/LineTransfer/TRTC?$format=JSON"
        return self._get_all_data_paginated(url)

    def get_station_facilities(self):
        url = f"{self.base_url}/v2/Rail/Metro/StationFacility/TRTC?$format=JSON"
        return self._get_all_data_paginated(url)

    def get_station_exits(self, rail_system: str = "TRTC"):
        url = f"{self.base_url}/v2/Rail/Metro/StationExit/{rail_system}?$format=JSON"
        return self._get_all_data_paginated(url)
    
    def get_mrt_network(self):
        # 這個 API 獲取的是路網的元數據，不包含站點序列
        url = f"{self.base_url}/v2/Rail/Metro/Network/TRTC?$format=JSON"
        return self._get_all_data_paginated(url)

    def get_first_last_timetable(self, station_id: str):
        url = f"{self.base_url}/v2/Rail/Metro/FirstLastTimetable/TRTC?$filter=StationID eq '{station_id}'&$format=JSON"
        return self._get_api_data(url)


# 建立 TDXApi 的單一實例
tdx_api = TDXApi(client_id=config.TDX_CLIENT_ID, client_secret=config.TDX_CLIENT_SECRET)
