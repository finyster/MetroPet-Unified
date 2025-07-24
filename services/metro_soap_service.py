import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import json
import config
import logging

logger = logging.getLogger(__name__)

class MetroSoapService:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.api_endpoints = {
            "LoseThing": "http://api.metro.taipei/metroapi/LoseThingForWeb.asmx",
            "RouteControl": "http://ws.metro.taipei/trtcBeaconBE/RouteControl.asmx",
            "TrainInfo": "http://mobileapp.metro.taipei/TRTCTraininfo/TrainTimeControl.asmx",
            "HighCapacityCarWeight": "https://api.metro.taipei/metroapi/CarWeight.asmx",
            "WenhuCarWeight": "https://api.metro.taipei/metroapi/CarWeightBR.asmx",
            "PassengerFlow": "https://api.metro.taipei/metroapi/PassengerFlow.asmx"
        }

    def _send_soap_request(self, endpoint_key: str, soap_action: str, soap_body: str) -> ET.Element | None:
        """通用的 SOAP 請求函式，發送請求並返回解析後的 XML 根元素。"""
        api_url = self.api_endpoints.get(endpoint_key)
        if not api_url:
            logger.error(f"--- ❌ 錯誤：找不到名為 '{endpoint_key}' 的 API 端點設定。 ---")
            return None

        headers = {'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': soap_action}
        try:
            logger.info(f"--- 正在呼叫 {soap_action} (URL: {api_url})... ---")
            response = requests.post(api_url, data=soap_body.encode('utf-8'), headers=headers, timeout=60)
            response.raise_for_status()
            logger.info(f"--- ✅ 呼叫成功。---")
            return ET.fromstring(response.content)
        except requests.RequestException as e:
            logger.error(f"--- ❌ 呼叫 SOAP API 時發生錯誤 (URL: {api_url}): {e} ---", exc_info=True)
            return None
        except ET.ParseError as e:
            logger.error(f"--- ❌ 解析 SOAP API 回應的 XML 時發生錯誤: {e} ---", exc_info=True)
            return None

    def _xml_to_dict(self, element: ET.Element) -> dict | str | None:
        """遞歸地將 XML Element 轉換為 Python 字典。"""
        # 處理沒有子元素的節點（即葉節點）
        if not list(element):
            return element.text or ""

        result = {}
        for child in element:
            # 清理標籤名稱，移除命名空間
            tag = child.tag.split('}')[-1]
            child_dict = self._xml_to_dict(child)

            # 如果標籤已存在，表示這是一個列表
            if tag in result:
                # 如果原本不是列表，先轉換為列表
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(child_dict)
            else:
                result[tag] = child_dict
        return result

    def _extract_soap_body(self, root: ET.Element, result_tag: str) -> dict | list | None:
        """從 SOAP Envelope 中提取 Body 內容並轉換為字典。"""
        # Namespace for SOAP
        ns = {'soap': 'http://schemas.xmlsoap.org/soap/envelope/'}
        soap_body = root.find('soap:Body', ns)
        if soap_body is None:
            logger.warning("--- ⚠️ 警告：SOAP 回應中找不到 Body 標籤。 ---")
            return None
        
        # 找到第一個子元素，即實際的回應內容
        response_element = soap_body[0]
        if response_element is None:
            logger.warning("--- ⚠️ 警告：SOAP Body 中沒有回應內容。 ---")
            return None
            
        # 找到包含結果的特定標籤
        result_element = response_element.find(f".//{{{response_element.tag.split('}')[0][1:]}}}{result_tag}")
        if result_element is None:
            logger.warning(f"--- ⚠️ 警告：API 回應中找不到 {result_tag} 標籤。 ---")
            return None
            
        # 使用 _xml_to_dict 進行轉換
        return self._xml_to_dict(result_element)

    # =========== API 功能實現 ===========

    def get_all_lost_items_soap(self) -> list[dict] | None:
        """呼叫 getLoseThingForWeb_ALL API，獲取所有遺失物資料。"""
        if not self.username or not self.password:
            logger.error("--- ❌ 錯誤：缺少台北捷運 API 的帳號或密碼。 ---")
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

        root = self._send_soap_request("LoseThing", '"http://tempuri.org/getLoseThingForWeb_ALL"', body)
        if root is None:
            return None
        
        try:
            result = self._extract_soap_body(root, 'getLoseThingForWeb_ALLResult')
            # API 可能返回包含 'diffgr:diffgram' 的複雜結構
            if result and 'diffgr:diffgram' in result and 'NewDataSet' in result['diffgr:diffgram']:
                items = result['diffgr:diffgram']['NewDataSet'].get('Table', [])
                # 如果只有一個項目，它不會是列表
                if not isinstance(items, list):
                    items = [items]
                logger.info(f"--- ✅ 成功獲取並解析了 {len(items)} 筆遺失物資料。 ---")
                return items
            logger.warning("--- ⚠️ 警告：遺失物 API 回應的結構不符合預期。 ---")
            return None
        except (KeyError, TypeError) as e:
            logger.error(f"--- ❌ 解析遺失物回應時發生鍵或類型錯誤: {e} ---", exc_info=True)
            return None

    def get_recommand_route_soap(self, entry_sid: str, exit_sid: str) -> dict | None:
        """呼叫 GetRecommandRoute API，獲取推薦的搭乘路線。"""
        if not all([self.username, self.password, entry_sid, exit_sid]):
            logger.error("--- ❌ 錯誤：缺少路線規劃所需的參數 (帳密或起終點 SID)。 ---")
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

        root = self._send_soap_request("RouteControl", '"http://tempuri.org/GetRecommandRoute"', body)
        if root is None:
            return None
        
        try:
            route_info = self._extract_soap_body(root, 'GetRecommandRouteResult')
            if route_info:
                logger.info(f"--- ✅ 成功獲取並解析了推薦路線資料。 ---")
                return route_info
            return None
        except (KeyError, TypeError) as e:
            logger.error(f"--- ❌ 解析推薦路線回應時發生錯誤: {e} ---", exc_info=True)
            return None

    def get_station_list_soap(self) -> list[dict] | None:
        """呼叫 GetStationList API，獲取所有車站列表。"""
        body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetStationList xmlns="http://tempuri.org/" />
  </soap:Body>
</soap:Envelope>"""

        root = self._send_soap_request("RouteControl", '"http://tempuri.org/GetStationList"', body)
        if root is None:
            return None
        
        try:
            result = self._extract_soap_body(root, 'GetStationListResult')
            if result and 'diffgr:diffgram' in result and 'NewDataSet' in result['diffgr:diffgram']:
                stations = result['diffgr:diffgram']['NewDataSet'].get('Table', [])
                if not isinstance(stations, list):
                    stations = [stations]
                logger.info(f"--- ✅ 成功獲取並解析了 {len(stations)} 筆車站列表資料。 ---")
                return stations
            logger.warning("--- ⚠️ 警告：車站列表 API 回應的結構不符合預期。 ---")
            return None
        except (KeyError, TypeError) as e:
            logger.error(f"--- ❌ 解析車站列表回應時發生錯誤: {e} ---", exc_info=True)
            return None

    def get_train_info_soap(self, car_id: str) -> dict | None:
        """呼叫 GetTrainInfo API，獲取特定列車資訊。"""
        if not all([self.username, self.password, car_id]):
            logger.error("--- ❌ 錯誤：缺少查詢列車資訊所需的參數 (帳密或列車 ID)。 ---")
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
        
        root = self._send_soap_request("TrainInfo", '"/GetTrainInfo"', body)
        if root is None:
            return None
        
        try:
            train_info = self._extract_soap_body(root, 'GetTrainInfoResult')
            if train_info:
                logger.info(f"--- ✅ 成功獲取並解析了列車資訊。 ---")
                return train_info
            return None
        except (KeyError, TypeError) as e:
            logger.error(f"--- ❌ 解析列車資訊回應時發生錯誤: {e} ---", exc_info=True)
            return None