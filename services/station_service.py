# services/station_service.py
import json
import os
import re
import config
from .tdx_service import tdx_api

class StationManager:
    def __init__(self, station_data_path: str):
        self.station_data_path = station_data_path
        self.station_map = self._load_or_create_station_data()
        self.line_map = self._create_line_map()

    def _load_or_create_station_data(self):
        # ... (此函式內容同上一版，貼上時請保留)
        if os.path.exists(self.station_data_path):
            print(f"--- ✅ 從快取檔案 {os.path.basename(self.station_data_path)} 載入站點資料... ---")
            with open(self.station_data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        print(f"--- ⚠️ 找不到站點快取檔案，正在從 TDX API 重新建立... ---")
        return self.update_station_data()

    def _normalize_string(self, text: str) -> str:
        """標準化字串：小寫、移除空格、處理括號、繁轉簡"""
        text = text.lower().strip()
        text = re.sub(r"[\(（].*?[\)）]", "", text) # 移除括號和其中的內容
        return text.replace("臺", "台")

    def _create_line_map(self):
        """建立一個路線名稱的對照表，例如 "BL" -> "板南線" """
        if not self.station_map: return {}
        line_map = {}
        for station_ids in self.station_map.values():
            for station_id in station_ids:
                line_code = station_id[:2]
                if line_code.isalpha(): # 只處理如 'BL', 'BR' 的代碼
                    # 簡易的路線對照，可以擴充
                    if line_code == 'BL': line_map[line_code] = '板南線'
                    if line_code == 'BR': line_map[line_code] = '文湖線'
                    if line_code == 'R': line_map[line_code] = '淡水信義線'
                    if line_code == 'G': line_map[line_code] = '松山新店線'
                    if line_code == 'O': line_map[line_code] = '中和新蘆線'
                    if line_code == 'Y': line_map[line_code] = '環狀線'
        return line_map

    def update_station_data(self) -> dict:
        # ... (此函式內容同上一版，貼上時請保留)
        network_data = tdx_api.get_mrt_network()
        if not network_data:
            print("--- ❌ 錯誤：無法從 TDX API 獲取路網資料。 ---")
            return {}
        station_map = {}
        # 英文站名對照表
        english_map = {
            "taipei main station": "台北車站",
            "taipei zoo": "動物園"
        }
        for route in network_data:
            for station in route.get('Stations', []):
                zh_name = station.get('StationName', {}).get('Zh_tw')
                en_name = station.get('StationName', {}).get('En')
                station_id = station.get('StationID')
                if zh_name and station_id:
                    # 標準化中文名
                    clean_zh = self._normalize_string(zh_name).replace("站", "")
                    if clean_zh not in station_map: station_map[clean_zh] = set()
                    station_map[clean_zh].add(station_id)
                    # 加入英文別名
                    if en_name:
                        clean_en = self._normalize_string(en_name)
                        if clean_en not in station_map: station_map[clean_en] = set()
                        station_map[clean_en].add(station_id)
                    # 加入手動設定的英文別名
                    for en_alias, zh_main_name in english_map.items():
                        if zh_name == zh_main_name:
                            if en_alias not in station_map: station_map[en_alias] = set()
                            station_map[en_alias].add(station_id)

        station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
        os.makedirs(os.path.dirname(self.station_data_path), exist_ok=True)
        with open(self.station_data_path, 'w', encoding='utf-8') as f:
            json.dump(station_map_list, f, ensure_ascii=False, indent=4)
        print(f"--- ✅ 站點資料已成功更新並儲存至 {self.station_data_path} ---")
        return station_map_list

    def get_station_id(self, station_name: str) -> str | None:
        if not station_name: return None
        clean_name = self._normalize_string(station_name).replace("站", "")
        ids = self.station_map.get(clean_name)
        if ids:
            return ids[0]
        print(f"--- ❌ 在 station_map 中找不到名稱為 '{clean_name}' 的站點 ---")
        return None

station_manager = StationManager(config.STATION_DATA_PATH)