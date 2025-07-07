# build_database.py
import os
import json
import re
import time
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

    # 1. 建立站點資料庫
    print("\n[1/3] 正在建立「站點資料庫」...")
    all_stations_data = tdx_api.get_all_stations_of_route()
    if not all_stations_data:
        print("--- ❌ 步驟 1 失敗: 無法獲取車站資料。請檢查 API 金鑰與網路。 ---")
        return

    station_map, alias_map = {}, {"北車": "台北車站", "101": "台北101/世貿"}
    for route in all_stations_data:
        for station in route.get("Stations", []):
            zh, en, id = station.get("StationName", {}).get("Zh_tw"), station.get("StationName", {}).get("En"), station.get("StationID")
            if zh and id:
                keys = {normalize_name(zh), normalize_name(en)}
                for alias, primary in alias_map.items():
                    if normalize_name(zh) == normalize_name(primary): keys.add(normalize_name(alias))
                for key in keys:
                    if key:
                        if key not in station_map: station_map[key] = set()
                        station_map[key].add(id)
    
    station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
    with open(config.STATION_DATA_PATH, 'w', encoding='utf-8') as f: json.dump(station_map_list, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 站點資料庫建立成功，共 {len(station_map_list)} 個站名。 ---")
    time.sleep(1)

    # 2. 建立票價資料庫
    print("\n[2/3] 正在建立「票價資料庫」...")
    all_fares_data = tdx_api.get_all_fares()
    if not all_fares_data:
        print("--- ❌ 步驟 2 失敗: 無法獲取票價資料。 ---")
        return
        
    fare_map = {}
    for info in all_fares_data:
        o_id, d_id, fares = info.get("OriginStationID"), info.get("DestinationStationID"), info.get("Fares")
        if o_id and d_id and fares:
            key = f"{o_id}-{d_id}"
            fare_map[key] = {"全票": next((f.get("Price") for f in fares if f.get("FareClass") == 1), 0), "兒童票": next((f.get("Price") for f in fares if f.get("FareClass") == 4), 0)}
    with open(config.FARE_DATA_PATH, 'w', encoding='utf-8') as f: json.dump(fare_map, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 票價資料庫建立成功，共 {len(fare_map)} 筆票價組合。 ---")
    time.sleep(1)

    # 3. 建立轉乘資料庫
    print("\n[3/3] 正在建立「轉乘資料庫」...")
    transfer_data = tdx_api.get_line_transfer_info()
    if not transfer_data:
        print("--- ❌ 步驟 3 失敗: 無法獲取轉乘資料。 ---")
        return
    with open(config.TRANSFER_DATA_PATH, 'w', encoding='utf-8') as f: json.dump(transfer_data, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 轉乘資料庫建立成功，共 {len(transfer_data)} 筆轉乘資訊。 ---")

    print("\n\n--- 🎉 所有資料庫均已成功建立！可以啟動主程式了。 ---")

if __name__ == "__main__":
    build_all_caches()