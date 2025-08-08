import requests
import xml.etree.ElementTree as ET
import json
import logging
import config
import re # 引入正則表達式模組
import csv
from io import StringIO

# 配置日誌記錄
logger = logging.getLogger(__name__)

class MetroSoapService:
    """
    提供與台北捷運 SOAP API 互動的服務。
    處理 SOAP 請求的發送、XML/JSON/CSV 回應的解析以及錯誤日誌記錄。
    """
    def __init__(self, username: str, password: str):
        """
        初始化 MetroSoapService 實例。
        :param username: 台北捷運 API 帳號。
        :param password: 台北捷運 API 密碼。
        """
        self.username = username
        self.password = password
        self.api_endpoints = {
            "LoseThing": "http://api.metro.taipei/metroapi/LoseThingForWeb.asmx",
            "RouteControl": "http://ws.metro.taipei/trtcBeaconBE/RouteControl.asmx",
            "TrainInfo": "https://api.metro.taipei/metroapi/TrackInfo.asmx",
            "HighCapacityCarWeight": "https://api.metro.taipei/metroapi/CarWeight.asmx", 
            "WenhuCarWeight": "https://api.metro.taipei/metroapi/CarWeightBR.asmx", 
            "PassengerFlow": "https://api.metro.taipei/metroapi/PassengerFlow.asmx"
        }
        # 定義常用的 XML 命名空間，便於解析
        self.namespaces = {
            'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xsd': 'http://www.w3.org/2001/XMLSchema',
            'tempuri': 'http://tempuri.org/',
            'diffgr': 'urn:schemas-microsoft-com:xml-diffgram-v1',
            'msdata': 'urn:schemas-microsoft-com:xml-msdata'
        }

    def _send_soap_request(self, endpoint_key: str, soap_action: str, soap_body: str) -> requests.Response | None:
        """
        通用的 SOAP 請求函式，發送請求並返回原始的 requests.Response 物件。
        不再在此函式內進行 XML 或 JSON 解析。
        :param endpoint_key: API 端點在 self.api_endpoints 中的鍵。
        :param soap_action: SOAPAction HTTP 標頭的值。
        :param soap_body: SOAP 請求的 XML 主體字串。
        :return: 原始的 requests.Response 物件或 None (如果發生錯誤)。
        """
        api_url = self.api_endpoints.get(endpoint_key)
        if not api_url:
            logger.error(f"❌ 錯誤：找不到名為 '{endpoint_key}' 的 API 端點設定。")
            return None

        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': soap_action
        }
        try:
            logger.info(f"🚀 正在呼叫 {soap_action} (URL: {api_url})...")
            response = requests.post(api_url, data=soap_body.encode('utf-8'), headers=headers, timeout=60)
            response.raise_for_status()  # 檢查 HTTP 狀態碼，如果不是 2xx 則拋出異常
            logger.info(f"✅ 呼叫 {soap_action} 成功。")
            return response
        except requests.exceptions.Timeout:
            logger.error(f"❌ 呼叫 SOAP API 超時 (URL: {api_url}, Action: {soap_action})。")
            return None
        except requests.RequestException as e:
            logger.error(f"❌ 呼叫 SOAP API 時發生網路或 HTTP 錯誤 (URL: {api_url}, Action: {soap_action}): {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ 呼叫 SOAP API 時發生未知錯誤 (URL: {api_url}, Action: {soap_action}): {e}", exc_info=True)
            return None

    def _xml_to_dict(self, element: ET.Element) -> dict | str | None:
        """
        遞歸地將 XML Element 轉換為 Python 字典。
        會處理命名空間並將標籤名清理為無命名空間的形式。
        :param element: 要轉換的 XML 元素。
        :return: 轉換後的字典、字串（如果是葉節點）或 None。
        """
        # 清理標籤名稱，移除命名空間
        tag = element.tag.split('}')[-1]

        # 如果沒有子元素，返回其文本內容
        if not list(element):
            return element.text.strip() if element.text else ""

        result = {}
        for child in element:
            child_tag = child.tag.split('}')[-1]
            child_value = self._xml_to_dict(child)

            if child_tag in result:
                # 如果該標籤已存在，表示有多個同名子元素，將其轉換為列表
                if not isinstance(result[child_tag], list):
                    result[child_tag] = [result[child_tag]]
                result[child_tag].append(child_value)
            else:
                result[child_tag] = child_value
        return result

    def _extract_soap_body_content_xml_element(self, root: ET.Element, result_tag: str) -> ET.Element | None:
        """
        從 SOAP Envelope 中提取 Body 內容中指定 result_tag 的 XML 元素。
        用於標準 SOAP XML 回應。
        :param root: SOAP 回應的根 XML 元素。
        :param result_tag: 期望的結果標籤名（不包含命名空間）。
        :return: 包含結果的 XML 元素 (ET.Element) 或 None。
        """
        # 尋找 soap:Body 元素
        soap_body = root.find('soap:Body', self.namespaces)
        if soap_body is None:
            logger.warning("⚠️ 警告：SOAP 回應中找不到 Body 標籤。")
            return None
        
        # 尋找 soap:Body 下的第一個子元素，通常是 API 的回應包裝元素
        response_wrapper = soap_body[0] if len(soap_body) > 0 else None
        if response_wrapper is None:
            logger.warning("⚠️ 警告：SOAP Body 中沒有回應內容。")
            return None
            
        # 尋找該回應包裝元素下的目標 result_tag 元素
        # 使用 find 而不是 iter，因為通常 result_tag 是直接子元素
        target_element = response_wrapper.find(f'{{http://tempuri.org/}}{result_tag}')
        
        if target_element is None:
            logger.warning(f"⚠️ 警告：API 回應中找不到預期的 '{result_tag}' 標籤。")
            # 為了確保涵蓋所有情況，如果直接查找不到，可以嘗試遍歷其子元素（但通常不應該這樣）
            for element in response_wrapper.iter():
                if element.tag.split('}')[-1] == result_tag:
                    return element
        return target_element

    def _parse_dataset_xml_string(self, xml_string: str) -> list[dict] | None:
        """
        輔助函式：解析內嵌的 `diffgr:diffgram` 結構的 XML 字串。
        這種結構常見於遺失物和車站列表 API。
        :param xml_string: 包含 diffgram 結構的 XML 字串。
        :return: 轉換後的資料列表或 None。
        """
        if not xml_string:
            return None
        try:
            root = ET.fromstring(xml_string)
            new_data_set = root.find('diffgr:diffgram/NewDataSet', self.namespaces)
            if new_data_set:
                items = []
                # 注意：這裡的 'Table' 元素通常沒有命名空間
                for table_element in new_data_set.findall('Table'):
                    items.append(self._xml_to_dict(table_element))
                
                if items:
                    return items
            logger.warning("⚠️ 警告：無法從內嵌 XML 字串中解析出有效的資料集 (NewDataSet/Table)。")
            return None
        except ET.ParseError as e:
            logger.error(f"❌ 從內嵌 XML 字串解析 diffgram 時發生錯誤: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ 處理內嵌 diffgram XML 字串時發生未知錯誤: {e}", exc_info=True)
            return None

    # --- API 功能實現 ---

    def get_high_capacity_car_weight_info(self) -> list[dict] | None:
        """
        獲取高運量線車廂擁擠度資料。API 名稱: getCarWeightByInfoEx
        此 API 的實際回應是**直接的 JSON 字串**，而非 SOAP XML。
        """
        if not self.username or not self.password:
            logger.error("❌ 錯誤：缺少台北捷運 API 的帳號或密碼，無法獲取高運量線車廂擁擠度資料。")
            return None

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="{self.namespaces['xsi']}" xmlns:xsd="{self.namespaces['xsd']}" xmlns:soap="{self.namespaces['soap']}">
  <soap:Body>
    <getCarWeightByInfoEx xmlns="{self.namespaces['tempuri']}">
      <userName>{self.username}</userName>
      <passWord>{self.password}</passWord>
    </getCarWeightByInfoEx>
  </soap:Body>
</soap:Envelope>"""

        response = self._send_soap_request("HighCapacityCarWeight", f'"{self.namespaces["tempuri"]}getCarWeightByInfoEx"', body)
        if response is None:
            return None
        
        try:
            # 直接嘗試將 response.text 解析為 JSON
            json_str = response.text.strip()
            
            if not json_str:
                logger.warning("⚠️ 警告：高運量線 API 回應為空或不包含可解析的 JSON 字串。")
                return None

            # 確保內容是有效的 JSON 格式，可能會有 SOAP XML 的標籤混入
            # 使用正則表達式找到第一個 '[' 到最後一個 ']' 之間的內容作為 JSON
            match = re.search(r'(\[.+\])', json_str, re.DOTALL)
            if match:
                clean_json_str = match.group(1)
            else:
                logger.error(f"❌ 高運量線 API 回應內容不是有效的 JSON 格式，且無法提取: {json_str[:200]}...")
                return None

            items = json.loads(clean_json_str)
            if isinstance(items, list):
                logger.info(f"✅ 成功解析了 {len(items)} 筆高運量線車廂擁擠度資料。")
                return items
            else:
                logger.warning(f"⚠️ 警告：高運量線 API 解析成功，但不是預期的 JSON 陣列。類型: {type(items)}")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"❌ 解析高運量線 API 的 JSON 回應時發生錯誤: {e}. 原始字串可能為: {json_str[:500]}...", exc_info=True)
        except Exception as e:
            logger.error(f"❌ 處理高運量線 API 回應時發生未知錯誤: {e}", exc_info=True)
        
        return None

    def get_wenhu_car_weight_info(self) -> list[dict] | None:
        """
        獲取文湖線車廂擁擠度資料。API 名稱: getCarWeightBRInfo
        此 API 的回應是 SOAP XML，其結果節點內嵌**一個 JSON 陣列字串**。
        """
        if not self.username or not self.password:
            logger.error("❌ 錯誤：缺少台北捷運 API 的帳號或密碼，無法獲取文湖線車廂擁擠度資料。")
            return None

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="{self.namespaces['xsi']}" xmlns:xsd="{self.namespaces['xsd']}" xmlns:soap="{self.namespaces['soap']}">
  <soap:Body>
    <getCarWeightBRInfo xmlns="{self.namespaces['tempuri']}">
      <userName>{self.username}</userName>
      <passWord>{self.password}</passWord>
    </getCarWeightBRInfo>
  </soap:Body>
</soap:Envelope>"""

        response = self._send_soap_request("WenhuCarWeight", f'"{self.namespaces["tempuri"]}getCarWeightBRInfo"', body)
        if response is None:
            return None

        try:
            root = ET.fromstring(response.content) # 首先解析外層的 SOAP XML
            # 找到包含 JSON 字串的結果節點
            result_node = self._extract_soap_body_content_xml_element(root, 'getCarWeightBRInfoResult')
            
            if result_node is not None and result_node.text: # 確保節點存在且有文本內容
                json_string_from_xml = result_node.text.strip()
                
                if not json_string_from_xml:
                    logger.warning("⚠️ 警告：文湖線 API 回應的 XML 節點中未找到 JSON 字串。")
                    return None

                # 提取 JSON 字串（可能被額外的引號包圍，或者有其他雜亂字符）
                # 這裡需要更強健的正則表達式來提取 JSON 陣列
                match = re.search(r'(\[.+\])', json_string_from_xml, re.DOTALL)
                if match:
                    clean_json_str = match.group(1)
                else:
                    logger.error(f"❌ 文湖線 API 回應的 XML 節點內容不是有效的 JSON 格式，且無法提取: {json_string_from_xml[:200]}...")
                    return None

                items = json.loads(clean_json_str) # 將這個內嵌的 JSON 字串解析
                if isinstance(items, list):
                    logger.info(f"✅ 成功解析了 {len(items)} 筆文湖線車廂擁擠度資料。")
                    return items
                else:
                    logger.warning(f"⚠️ 警告：文湖線 API 解析成功，但不是預期的 JSON 陣列。類型: {type(items)}")
                    return None
            else:
                logger.warning("⚠️ 警告：文湖線 API 回應格式不符合預期，未能找到或解析內嵌 JSON (result_node 或其text為空)。")
        except ET.ParseError as e:
            logger.error(f"❌ 解析文湖線 API 的 SOAP XML 回應時發生錯誤: {e}", exc_info=True)
        except json.JSONDecodeError as e:
            logger.error(f"❌ 解析文湖線 API 內嵌的 JSON 回應時發生錯誤: {e}. 原始字串可能為: {json_string_from_xml[:500]}...", exc_info=True)
        except Exception as e:
            logger.error(f"❌ 處理文湖線 API 回應時發生未知錯誤: {e}", exc_info=True)
        
        return None

    def get_all_lost_items_soap(self) -> list[dict] | None:
        """
        呼叫 getLoseThingForWeb_ALL API，獲取所有遺失物資料。
        回應結果是一個 XML 元素，其文本內容包含 diffgr:diffgram 結構的 XML 字串。
        """
        if not self.username or not self.password:
            logger.error("❌ 錯誤：缺少台北捷運 API 的帳號或密碼，無法獲取遺失物資料。")
            return None

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="{self.namespaces['xsi']}" xmlns:xsd="{self.namespaces['xsd']}" xmlns:soap="{self.namespaces['soap']}">
  <soap:Body>
    <getLoseThingForWeb_ALL xmlns="{self.namespaces['tempuri']}">
      <userName>{self.username}</userName>
      <passWord>{self.password}</passWord>
    </getLoseThingForWeb_ALL>
  </soap:Body>
</soap:Envelope>"""

        response = self._send_soap_request("LoseThing", f'"{self.namespaces["tempuri"]}getLoseThingForWeb_ALL"', body)
        if response is None:
            return None
        
        try:
            root = ET.fromstring(response.content)
            result_element = self._extract_soap_body_content_xml_element(root, 'getLoseThingForWeb_ALLResult')
            if result_element and result_element.text:
                items = self._parse_dataset_xml_string(result_element.text)
                if items is not None:
                    logger.info(f"✅ 成功獲取並解析了 {len(items)} 筆遺失物資料。")
                    return items
            logger.warning("⚠️ 警告：遺失物 API 回應格式不符合預期或無資料。")
        except ET.ParseError as e:
            logger.error(f"❌ 解析遺失物 API 的 SOAP XML 回應時發生錯誤: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ 處理遺失物 API 回應時發生未知錯誤: {e}", exc_info=True)
        
        return None

    def get_recommand_route_soap(self, entry_sid: str, exit_sid: str) -> dict | None:
        """
        呼叫 GetRecommandRoute API，獲取推薦的搭乘路線。
        :param entry_sid: 起始車站的 SID。
        :param exit_sid: 終點車站的 SID。
        """
        if not all([self.username, self.password, entry_sid, exit_sid]):
            logger.error("❌ 錯誤：缺少路線規劃所需的參數 (帳密或起終點 SID)。")
            return None
            
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="{self.namespaces['xsi']}" xmlns:xsd="{self.namespaces['xsd']}" xmlns:soap="{self.namespaces['soap']}">
  <soap:Body>
    <GetRecommandRoute xmlns="{self.namespaces['tempuri']}">
      <entrySid>{entry_sid}</entrySid>
      <exitSid>{exit_sid}</exitSid>
      <username>{self.username}</username>
      <password>{self.password}</password>
    </GetRecommandRoute>
  </soap:Body>
</soap:Envelope>"""

        response = self._send_soap_request("RouteControl", f'"{self.namespaces["tempuri"]}GetRecommandRoute"', body)
        if response is None:
            return None
        
        try:
            root = ET.fromstring(response.content)
            result_element = self._extract_soap_body_content_xml_element(root, 'GetRecommandRouteResult')
            if result_element:
                route_info = self._xml_to_dict(result_element)
                if route_info:
                    logger.info("✅ 成功獲取並解析了推薦路線資料。")
                    return route_info
            logger.warning("⚠️ 警告：推薦路線 API 回應格式不符合預期或無資料。")
        except ET.ParseError as e:
            logger.error(f"❌ 解析推薦路線 API 的 SOAP XML 回應時發生錯誤: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ 處理推薦路線 API 回應時發生未知錯誤: {e}", exc_info=True)
        
        return None

    def get_station_list_soap(self) -> list[dict] | None:
        """
        呼叫 GetStationList API，獲取所有車站列表。
        回應結果是一個 XML 元素，其文本內容包含 diffgr:diffgram 結構的 XML 字串。
        """
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="{self.namespaces['xsi']}" xmlns:xsd="{self.namespaces['xsd']}" xmlns:soap="{self.namespaces['soap']}">
  <soap:Body>
    <GetStationList xmlns="{self.namespaces['tempuri']}" />
  </soap:Body>
</soap:Envelope>"""

        response = self._send_soap_request("RouteControl", f'"{self.namespaces["tempuri"]}GetStationList"', body)
        if response is None:
            return None
        
        try:
            root = ET.fromstring(response.content)
            result_element = self._extract_soap_body_content_xml_element(root, 'GetStationListResult')
            if result_element and result_element.text:
                stations = self._parse_dataset_xml_string(result_element.text)
                if stations is not None:
                    logger.info(f"✅ 成功獲取並解析了 {len(stations)} 筆車站列表資料。")
                    return stations
            logger.warning("⚠️ 警告：車站列表 API 回應格式不符合預期或無資料。")
        except ET.ParseError as e:
            logger.error(f"❌ 解析車站列表 API 的 SOAP XML 回應時發生錯誤: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ 處理車站列表 API 回應時發生未知錯誤: {e}", exc_info=True)
        
        return None

    def get_realtime_track_info(self) -> list[dict] | None:
            """
            呼叫 getTrackInfo API，獲取即將在幾分鐘後抵達的列車預測資訊。
            此 API 的回應格式特殊且不穩定，需要更強健的解析方式。
            """
            if not self.username or not self.password:
                logger.error("❌ 錯誤：缺少台北捷運 API 的帳號或密碼，無法獲取即時列車資訊。")
                return None

            body = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="{self.namespaces['xsi']}" xmlns:xsd="{self.namespaces['xsd']}" xmlns:soap="{self.namespaces['soap']}">
        <soap:Body>
            <getTrackInfo xmlns="{self.namespaces['tempuri']}">
                <userName>{self.username}</userName>
                <passWord>{self.password}</passWord>
            </getTrackInfo>
        </soap:Body>
    </soap:Envelope>"""

            response = self._send_soap_request("TrainInfo", f'"{self.namespaces["tempuri"]}getTrackInfo"', body)
            if response is None:
                return None

            try:
                response_text = response.text.strip()
                
                if not response_text:
                    logger.warning("⚠️ 警告：getTrackInfo API 回應為空。")
                    return None
                
                # --- 【核心修正】這裡使用正則表達式尋找並提取 JSON 陣列 ---
                # 這個模式會尋找以 '[' 開頭，以 ']' 結尾的內容，並忽略中間的所有字符（包括換行）
                match = re.search(r'(\[.+\])', response_text, re.DOTALL)
                
                if not match:
                    logger.error(f"❌ getTrackInfo API 回應中未找到有效的 JSON 陣列。原始回應前 200 字元: {response_text[:200]}...")
                    return None
                
                json_str = match.group(1)

                items = json.loads(json_str)
                
                if isinstance(items, list):
                    clean_data = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        
                        # 處理 Countdown
                        countdown = item.get('CountDown', '未知')
                        if '進站' in countdown:
                            countdown = '列車進站'
                        else:
                            try:
                                # 確保 countdown 是 "分鐘:秒" 格式
                                m, s = map(int, countdown.split(':'))
                                countdown = f"{m} 分鐘 {s} 秒"
                            except (ValueError, IndexError):
                                countdown = '未知'

                        clean_data.append({
                            'StationName': item.get('StationName'),
                            'DestinationName': item.get('DestinationName'),
                            'CountDown': countdown,
                            'NowDateTime': item.get('NowDateTime'),
                            'LineID': item.get('LineID'),
                            'StationID': item.get('StationID')
                        })
                    
                    logger.info(f"✅ 成功解析了 {len(clean_data)} 筆即時列車預測資訊。")
                    return clean_data
                else:
                    logger.warning(f"⚠️ 警告：getTrackInfo API 解析成功，但不是預期的 JSON 陣列。類型: {type(items)}")
                    return None
            except json.JSONDecodeError as e:
                logger.error(f"❌ 解析 getTrackInfo API 提取的 JSON 回應時發生錯誤: {e}. 原始字串可能為: {json_str[:500]}...", exc_info=True)
            except Exception as e:
                logger.error(f"❌ 處理 getTrackInfo API 回應時發生未知錯誤: {e}", exc_info=True)
            
            return None

# 建立 MetroSoapService 的一個實例 (instance)，並命名為 metro_soap_api
metro_soap_api = MetroSoapService(
    username=config.METRO_API_USERNAME,
    password=config.METRO_API_PASSWORD
)