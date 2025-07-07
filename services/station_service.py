# services/station_service.py
import json
import os
import config
from .tdx_service import tdx_api

class StationManager:
    def __init__(self, station_data_path: str):
        self.station_data_path = station_data_path
        self.station_map = self._load_station_data()

    def _load_station_data(self):
        if os.path.exists(self.station_data_path):
            print(f"從快取檔案 {self.station_data_path} 載入站點資料...")
            with open(self.station_data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self.update_station_data()

    def update_station_data(self) -> dict:
        print("本地站點資料不存在或需更新，正在從網路下載...")
        network_data = tdx_api.get_mrt_network()
        if not network_data:
            print("錯誤：無法從 TDX API 獲取路網資料。")
            return {}
        station_map = {}
        for route in network_data:
            for station in route.get('Stations', []):
                station_name = station.get('StationName', {}).get('Zh_tw')
                station_id = station.get('StationID')
                if station_name and station_id:
                    clean_name = station_name.replace("站", "").lower()
                    if clean_name not in station_map:
                        station_map[clean_name] = []
                    station_map[clean_name].append(station_id)
        os.makedirs(os.path.dirname(self.station_data_path), exist_ok=True)
        with open(self.station_data_path, 'w', encoding='utf-8') as f:
            json.dump(station_map, f, ensure_ascii=False, indent=4)
        print(f"站點資料已成功更新並儲存至 {self.station_data_path}")
        return station_map

    def get_station_id(self, station_name: str):
        clean_name = station_name.replace("站", "").lower()
        ids = self.station_map.get(clean_name)
        return ids[0] if ids else None

station_manager = StationManager(config.STATION_DATA_PATH)