# build_cache.py
import os
import json
import re
from services.tdx_service import tdx_api # 引用我們修正過的 tdx_service
import config

def normalize_name(name: str) -> str:
    """標準化站名：轉小寫、處理臺/台、移除括號和'站'字"""
    if not name: return ""
    name = name.lower().strip().replace("臺", "台")
    name = re.sub(r"[\(（].*?[\)）]", "", name).strip()
    if name.endswith("站"):
        name = name[:-1]
    return name

def build_station_map():
    """從 TDX API 獲取資料並建立一個強大的站名對照表"""
    print("--- [Cache Builder] 開始建立站點快取資料庫... ---")
    
    # 步驟 1: 一次性獲取所有車站資料
    all_stations_data = tdx_api.get_all_stations_of_route()
    
    # 步驟 2: 嚴格檢查 API 回應
    if not all_stations_data or not isinstance(all_stations_data, list):
        print("--- ❌ 致命錯誤：從 TDX API 獲取的車站資料為空或格式不正確。請檢查 TDX_CLIENT_ID 和 SECRET。 ---")
        return

    print(f"--- ✅ [Cache Builder] 成功從 TDX API 獲取 {len(all_stations_data)} 筆路線資料。 ---")
    
    station_map = {}
    
    # 步驟 3: 解析所有路線中的所有車站
    try:
        for route in all_stations_data:
            for station in route.get("Stations", []):
                zh_name = station.get("StationName", {}).get("Zh_tw")
                en_name = station.get("StationName", {}).get("En")
                station_id = station.get("StationID")

                if not (zh_name and station_id):
                    continue

                # 建立一個包含所有可能名稱的集合
                names_to_map = {normalize_name(zh_name), normalize_name(en_name)}
                
                for name in names_to_map:
                    if name:
                        if name not in station_map:
                            station_map[name] = set()
                        station_map[name].add(station_id)
        
        station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}

        if not station_map_list:
            print("--- ❌ 致命錯誤：處理後的 station_map 仍然為空。 ---")
            return
            
        # 步驟 4: 寫入快取檔案
        cache_path = config.STATION_DATA_PATH
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(station_map_list, f, ensure_ascii=False, indent=2)
        print(f"--- ✅ [Cache Builder] 站點資料庫已成功建立！共處理 {len(station_map_list)} 個唯一的站名。 ---")
        print(f"--- 檔案已儲存至: {cache_path} ---")

    except Exception as e:
        print(f"--- ❌ 致命錯誤：解析資料或寫入檔案時發生未預期的錯誤: {e} ---")

if __name__ == "__main__":
    build_station_map()