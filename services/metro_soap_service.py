import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import json
import config

class MetroSoapApi:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        
        # 集中管理所有 API 的端點 URL
        self.api_endpoints = {
            "LoseThing": "http://api.metro.taipei/metroapi/LoseThingForWeb.asmx",
            "RouteControl": "http://ws.metro.taipei/trtcBeaconBE/RouteControl.asmx",
            "TrainInfo": "http://mobileapp.metro.taipei/TRTCTraininfo/TrainTimeControl.asmx",
            "HighCapacityCarWeight": "https://api.metro.taipei/metroapi/CarWeight.asmx",
            "WenhuCarWeight": "https://api.metro.taipei/metroapi/CarWeightBR.asmx",
            "PassengerFlow": "https://api.metro.taipei/metroapi/PassengerFlow.asmx" # 假設的 API
        }

    def _make_soap_request(self, endpoint_key: str, soap_action: str, soap_body: str) -> requests.Response | None:
        """
        一個通用的 SOAP 請求函式，用於發送請求到指定的端點。
        """
        api_url = self.api_endpoints.get(endpoint_key)
        if not api_url:
            print(f"--- ❌ 錯誤：找不到名為 '{endpoint_key}' 的 API 端點設定。 ---")
            return None

        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': soap_action
        }
        
        try:
            print(f"--- [SOAP] 正在呼叫 {soap_action}... ---")
            response = requests.post(api_url, data=soap_body.encode('utf-8'), headers=headers, timeout=60)
            response.raise_for_status()
            print(f"--- ✅ [SOAP] 呼叫成功。---")
            return response
        except requests.RequestException as e:
            print(f"--- ❌ 呼叫 SOAP API 時發生錯誤 (URL: {api_url}): {e} ---")
            return None

    # =========== 新增與修改的 API 功能 ===========

    def get_all_lost_items(self) -> list[dict] | None:
        """
        【新功能】呼叫 getLoseThingForWeb_ALL API，獲取所有遺失物資料。
        """
        if not self.username or not self.password:
            print("--- ❌ 錯誤：缺少台北捷運 API 的帳號或密碼。 ---")
            return None

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <getLoseThingForWeb_ALL xmlns="http://tempuri.org/">
      <userName>{self.username}</userName>
      <passWord>{self.password}</passWord>
    </getLoseThingForWeb_ALL>
  </soap:Body>
</soap:Envelope>"""

        response = self._make_soap_request("LoseThing", '"http://tempuri.org/getLoseThingForWeb_ALL"', body)
        
        if not response:
            return None
        
        try:
            soup = BeautifulSoup(response.content, 'xml')
            result_node = soup.find('getLoseThingForWeb_ALLResult')
            if not result_node:
                print("--- ⚠️ 警告：API 回應中找不到 getLoseThingForWeb_ALLResult 標籤。 ---")
                return None
            
            # 假設回傳的內容是包在 Table 節點中的 XML
            items = []
            for thing in result_node.find_all('Table'):
                items.append({
                    "id": thing.find('ls_no').text if thing.find('ls_no') else '',
                    "date": thing.find('get_date').text if thing.find('get_date') else '',
                    "location": thing.find('get_place').text if thing.find('get_place') else '',
                    "name": thing.find('ls_name').text if thing.find('ls_name') else '',
                    "description": thing.find('ls_spec').text if thing.find('ls_spec') else ''
                })
            print(f"--- ✅ [SOAP] 成功獲取並解析了 {len(items)} 筆遺失物資料。 ---")
            return items
        except Exception as e:
            print(f"--- ❌ 解析遺失物 XML 時發生錯誤: {e} ---")
            return None

    def get_recommended_route(self, entry_sid: str, exit_sid: str) -> dict | None:
        """
        【新功能】呼叫 GetRecommandRoute API，獲取推薦的搭乘路線。
        """
        if not all([self.username, self.password, entry_sid, exit_sid]):
            print("--- ❌ 錯誤：缺少路線規劃所需的參數 (帳密或起終點 SID)。 ---")
            return None
            
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetRecommandRoute xmlns="http://tempuri.org/">
      <entrySid>{entry_sid}</entrySid>
      <exitSid>{exit_sid}</exitSid>
      <username>{self.username}</username>
      <password>{self.password}</password>
    </GetRecommandRoute>
  </soap:Body>
</soap:Envelope>"""

        response = self._make_soap_request("RouteControl", '"http://tempuri.org/GetRecommandRoute"', body)
        
        if not response:
            return None

        # 為了方便後續處理，我們先將原始 XML 回傳，讓 Agent 來解析
        # 你也可以在這裡加入 XML 解析邏輯，轉換成 JSON
        return {"xml_response": response.text}

    def get_station_list(self) -> dict | None:
        """
        【新功能】呼叫 GetStationList API，獲取所有車站列表。
        """
        body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetStationList xmlns="http://tempuri.org/" />
  </soap:Body>
</soap:Envelope>"""

        response = self._make_soap_request("RouteControl", '"http://tempuri.org/GetStationList"', body)
        
        if not response:
            return None
        
        # 同樣，我們先回傳原始 XML
        return {"xml_response": response.text}

    def get_train_info(self, car_id: str) -> dict | None:
        """
        【新功能】呼叫 GetTrainInfo API，獲取特定列車資訊。
        """
        if not all([self.username, self.password, car_id]):
            print("--- ❌ 錯誤：缺少查詢列車資訊所需的參數 (帳密或列車 ID)。 ---")
            return None

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetTrainInfo xmlns="http://tempuri.org/">
      <carID>{car_id}</carID>
      <username>{self.username}</username>
      <password>{self.password}</password>
    </GetTrainInfo>
  </soap:Body>
</soap:Envelope>"""
        
        # 注意: SOAPAction 是 "/GetTrainInfo"，沒有 namespace
        response = self._make_soap_request("TrainInfo", '"/GetTrainInfo"', body)

        if not response:
            return None
            
        return {"xml_response": response.text}


    # =========== 你原本既有的 API 功能 (維持不變) ===========

    def get_high_capacity_car_weight_info(self) -> list[dict] | None:
        if not self.username or not self.password:
            print("--- ❌ 錯誤 _：缺少台北捷運 API 的帳號或密碼。 ---")
            return None

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <getCarWeightByInfoEx xmlns="http://tempuri.org/">
      <userName>{self.username}</userName>
      <passWord>{self.password}</passWord>
    </getCarWeightByInfoEx>
  </soap:Body>
</soap:Envelope>"""
        response = self._make_soap_request("HighCapacityCarWeight", '"http://tempuri.org/getCarWeightByInfoEx"', body)
        
        if not response:
            return None

        response_text = response.content.decode('utf-8').strip()
        json_start_index = response_text.find('[')
        json_end_index = response_text.rfind(']')

        car_weights = []
        if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
            json_data_str = response_text[json_start_index : json_end_index + 1]
            try:
                data = json.loads(json_data_str)
                for item in data:
                    car_weights.append({
                        "train_number": item.get('TrainNumber', ''),
                        "car_pair_number": item.get('CN1', ''),
                        "line_direction_cid": item.get('CID', ''),
                        "station_id": item.get('StationID', ''),
                        "car1_congestion": item.get('Cart1L', ''),
                        "car2_congestion": item.get('Cart2L', ''),
                        "car3_congestion": item.get('Cart3L', ''),
                        "car4_congestion": item.get('Cart4L', ''),
                        "car5_congestion": item.get('Cart5L', ''),
                        "car6_congestion": item.get('Cart6L', ''),
                        "update_time": item.get('utime', '')
                    })
                print(f"--- ✅ [SOAP] 成功獲取並解析了 {len(car_weights)} 筆高運量列車車廂擁擠度資料。 ---")
                return car_weights
            except json.JSONDecodeError as je:
                print(f"--- ❌ 高運量列車 API 回應的 JSON 解析失敗: {je} ---")
        else:
            print("--- ⚠️ 警告：在高運量列車 API 回應中未找到有效的 JSON 數據。 ---")
        return None


    def get_wenhu_car_weight_info(self) -> list[dict] | None:
        if not self.username or not self.password:
            print("--- ❌ 錯誤：缺少台北捷運 API 的帳號或密碼。 ---")
            return None

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <getCarWeightBRInfo xmlns="http://tempuri.org/">
      <userName>{self.username}</userName>
      <passWord>{self.password}</passWord>
    </getCarWeightBRInfo>
  </soap:Body>
</soap:Envelope>"""
        response = self._make_soap_request("WenhuCarWeight", '"http://tempuri.org/getCarWeightBRInfo"', body)

        if not response:
            return None
        
        soup = BeautifulSoup(response.content, 'xml')
        fault = soup.find('faultstring')
        if fault:
            print(f"--- ❌ API 錯誤 (文湖線 SOAP Fault): {fault.text} ---")
            return None

        car_weight_result_tag = soup.find('getCarWeightBRInfoResult')
        if not car_weight_result_tag or not car_weight_result_tag.text:
            print("--- ⚠️ 警告：API 回應中找不到 getCarWeightBRInfoResult 標籤或其內容為空。 ---")
            return None

        json_string = car_weight_result_tag.text
        car_weights = []
        try:
            data = json.loads(json_string)
            for item in data:
                car_weights.append({
                    "train_number": item.get('TrainNumber', ''),
                    "line_direction_cid": item.get('CID', ''),
                    "direction_chinese": item.get('DU', ''),
                    "station_id": item.get('StationID', ''),
                    "station_name": item.get('StationName', ''),
                    "car_number_cn1": item.get('CN1', ''),
                    "car_number_cn2": item.get('CN2', ''),
                    "car1_congestion": item.get('Car1', ''),
                    "car2_congestion": item.get('Car2', ''),
                    "car3_congestion": item.get('Car3', ''),
                    "car4_congestion": item.get('Car4', ''),
                    "update_time": item.get('UpdateTime', '')
                })
            print(f"--- ✅ [SOAP] 成功獲取並解析了 {len(car_weights)} 筆文湖線列車車廂擁擠度資料。 ---")
            return car_weights
        except json.JSONDecodeError as je:
            print(f"--- ❌ 文湖線 API 回應的 JSON 解析失敗: {je} ---")
            return None
    
    # ... 其他你可能有的函式 ...


# 建立 MetroSoapApi 的單一實例，方便在專案其他地方直接 import 使用
# 注意：你的 config 檔案需要有 METRO_API_USERNAME 和 METRO_API_PASSWORD
metro_soap_api = MetroSoapApi(username=config.METRO_API_USERNAME, password=config.METRO_API_PASSWORD)