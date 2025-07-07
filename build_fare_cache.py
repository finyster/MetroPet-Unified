# build_metro_database.py
import os
import json
import re
import config
from services.tdx_service import tdx_api

def normalize_name(name: str) -> str:
    if not name: return ""
    name = name.lower().strip().replace("臺", "台")
    name = re.sub(r"[\(（].*?[\)）]", "", name).strip()
    if name.endswith("站"): name = name[:-1]
    return name

def build_all_caches():
    print("--- 🚀 開始建立捷運靜態資料庫... ---")

    # 1. 建立站點資料庫 (mrt_station_info.json)
    all_stations_data = tdx_api.get_all_stations_of_route()
    if not all_stations_data:
        print("--- ❌ 步驟 1 失敗: 無法獲取車站資料。請檢查 API 金鑰。 ---")
        return
    
    station_map = {}
    for route in all_stations_data:
        for station in route.get("Stations", []):
            zh_name = station.get("StationName", {}).get("Zh_tw")
            en_name = station.get("StationName", {}).get("En")
            station_id = station.get("StationID")
            if zh_name and station_id:
                keys = {normalize_name(zh_name), normalize_name(en_name)}
                for key in keys:
                    if key:
                        if key not in station_map: station_map[key] = set()
                        station_map[key].add(station_id)
    
    station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
    with open(config.STATION_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(station_map_list, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 站點資料庫建立成功，共 {len(station_map_list)} 個站名。 ---")

    # 2. 建立轉乘資料庫 (mrt_transfer_info.json)
    transfer_data = tdx_api.get_line_transfer_info()
    if not transfer_data:
        print("--- ❌ 步驟 2 失敗: 無法獲取轉乘資料。 ---")
        return
    with open(config.TRANSFER_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(transfer_data, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 轉乘資料庫建立成功，共 {len(transfer_data)} 筆轉乘資訊。 ---")

    print("\n--- 🎉 所有資料庫均已成功建立！可以啟動主程式了。 ---")

if __name__ == "__main__":
    build_all_caches()