# build_database.py

import os
import json
import re
import time
import config
from services.tdx_service import tdx_api

# 為了避免循環依賴和簡化，我們在這裡重新定義一個與 StationManager 內部邏輯相同的 normalize_name 函數。
def normalize_name(name: str) -> str:
    """標準化站點名稱：小寫、移除括號內容、移除「站」、繁轉簡"""
    if not name: return ""
    name = name.lower().strip().replace("臺", "台")
    name = re.sub(r"[\(（].*?[\)）]", "", name).strip()
    if name.endswith("站"): name = name[:-1]
    return name

def build_station_database():
    """從 TDX API 獲取所有捷運站點資訊，並儲存為 JSON 檔案。"""
    print("\n--- [1/5] 正在建立「站點資料庫」... ---")
    all_stations_data = tdx_api.get_all_stations_of_route()
    if not all_stations_data:
        print("--- ❌ 步驟 1 失敗: 無法獲取車站資料。請檢查 API 金鑰與網路。 ---")
        return

    station_map = {}
    alias_map = {
        "北車": "台北車站", "台車": "台北車站", "台北駅": "台北車站",
        "101": "台北101/世貿",
        "西門": "西門", "西門町": "西門",
        "動物園": "動物園", "動物園駅": "動物園",
        "淡水": "淡水"
    } # 擴展別名，含日文

    for route in all_stations_data:
        for station in route.get("Stations", []):
            zh_name = station.get("StationName", {}).get("Zh_tw")
            en_name = station.get("StationName", {}).get("En")
            station_id = station.get("StationID")

            if zh_name and station_id:
                keys = {normalize_name(zh_name)}
                if en_name: keys.add(normalize_name(en_name))
                for alias, primary in alias_map.items():
                    if normalize_name(zh_name) == normalize_name(primary):
                        keys.add(normalize_name(alias))

                for key in keys:
                    if key:
                        if key not in station_map: station_map[key] = set()
                        station_map[key].add(station_id)

    station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
    os.makedirs(os.path.dirname(config.STATION_DATA_PATH), exist_ok=True)
    with open(config.STATION_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(station_map_list, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 站點資料庫建立成功，共 {len(station_map_list)} 個站名。 ---")
    time.sleep(1)

def build_fare_database():
    """從 TDX API 獲取所有票價資訊，並儲存為 JSON 檔案。"""
    print("\n--- [2/5] 正在建立「票價資料庫」... ---")
    tdx_fares = tdx_api.get_all_fares()
    fare_map = {}
    
    if not tdx_fares:
        print("--- ❌ [TDX] 從 TDX API 獲取票價數據失敗或為空！將不會建立票價檔案。---")
        return 

    print(f"--- [TDX] 成功從 TDX API 獲取了 {len(tdx_fares)} 筆 O-D 配對原始資料。---")
    for info in tdx_fares:
        o_id = info.get("OriginStationID")
        d_id = info.get("DestinationStationID")
        fares = info.get("Fares", [])
        if o_id and d_id and fares:
            adult_fare = next((f.get("Price") for f in fares if f.get("TicketType") == 1 and f.get("FareClass") == 1), None)
            child_fare = next((f.get("Price") for f in fares if f.get("TicketType") == 1 and f.get("FareClass") == 4), None)
            if adult_fare is not None and child_fare is not None:
                # 同時建立正向和反向的 key，確保查詢萬無一失
                key1 = f"{o_id}-{d_id}"
                key2 = f"{d_id}-{o_id}"
                fare_data = {"全票": adult_fare, "兒童票": child_fare}
                fare_map[key1] = fare_data
                fare_map[key2] = fare_data
    
    os.makedirs(os.path.dirname(config.FARE_DATA_PATH), exist_ok=True)
    with open(config.FARE_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(fare_map, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 票價資料庫建立成功，共寫入 {len(fare_map)} 筆票價組合。 ---")
    time.sleep(1)

def build_transfer_database():
    """從 TDX API 獲取捷運轉乘資訊，並儲存為 JSON 檔案。"""
    print("\n--- [3/5] 正在建立「轉乘資料庫」... ---")
    transfer_data = tdx_api.get_line_transfer_info()
    if not transfer_data:
        print("--- ❌ 步驟 3 失敗: 無法獲取轉乘資料。請檢查 API 金鑰與網路。 ---")
        return

    os.makedirs(os.path.dirname(config.TRANSFER_DATA_PATH), exist_ok=True)
    with open(config.TRANSFER_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(transfer_data, f, ensure_ascii=False, indent=2)

    print(f"--- ✅ 轉乘資料庫建立成功，共 {len(transfer_data)} 筆轉乘資訊。 ---")
    time.sleep(1)

def build_facilities_database():
    """從 TDX API 獲取車站設施資訊，並處理 429 錯誤。"""
    print("\n--- [4/5] 正在建立「車站設施資料庫」... ---")
    all_facilities_data = tdx_api.get_station_facilities()
    if not all_facilities_data:
        print("--- ⚠️ 步驟 4 失敗: 無法獲取車站設施資料，可能因 429 錯誤。請稍後重試或檢查 API 配額。 ---")
        return

    facilities_map = {}
    for facility in all_facilities_data:
        station_id = facility.get('StationID')
        if station_id:
            # 將 FacilityDescription 中的換行符號統一處理
            description = facility.get('FacilityDescription', '無詳細資訊').replace('\r\n', '\n').strip()
            if station_id not in facilities_map:
                facilities_map[station_id] = []
            facilities_map[station_id].append(description)

    # 將每個站點的所有設施描述合併成一個字串
    final_facilities_map = {
        station_id: "\n".join(descriptions)
        for station_id, descriptions in facilities_map.items()
    }

    os.makedirs(os.path.dirname(config.FACILITIES_DATA_PATH), exist_ok=True)
    with open(config.FACILITIES_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_facilities_map, f, ensure_ascii=False, indent=4)

    print(f"--- ✅ 車站設施資料庫已成功建立於 {config.FACILITIES_DATA_PATH}，共包含 {len(final_facilities_map)} 個站點的設施資訊。 ---")
    time.sleep(1)

def build_exit_database():
    """從 TDX API 獲取車站出入口資訊，並儲存為 JSON 檔案。"""
    print("\n--- [5/5] 正在建立「車站出入口資料庫」... ---")
    
    all_exits_data = tdx_api.get_station_exits(rail_system="TRTC")
    
    if not all_exits_data:
        print("--- ❌ 步驟 5 失敗: 無法獲取車站出入口資料。請檢查 API 金鑰與網路。 ---")
        return

    exit_map = {}
    processed_exit_count = 0 # 新增計數器
    for exit_info in all_exits_data:
        station_id = exit_info.get("StationID")
        
        # --- 關鍵修正：嘗試獲取正確的 ExitID，處理可能存在的錯誤鍵名 ---
        exit_no = exit_info.get("ExitID")
        # 如果直接獲取不到，嘗試獲取錯誤的鍵名 ''ExitID'
        if exit_no is None:
            exit_no = exit_info.get("''ExitID'") 
            if exit_no is not None:
                # 修正後的打印語句，直接引用變數 exit_no
                print(f"--- Debug: Found malformed ExitID for StationID {station_id}: {exit_no} (original entry: {exit_info}) ---")

        exit_description_obj = exit_info.get("ExitDescription", {})
        exit_description = exit_description_obj.get("Zh_tw", "無描述")
        
        # ！！！新增的調試打印語句！！！
        # 如果 StationID 或 ExitNo 缺失，打印原始數據以供調試
        if not (station_id and exit_no):
            print(f"--- ⚠️ Skipping exit info due to missing StationID or ExitNo: {exit_info} ---")
            continue
        
        if station_id not in exit_map:
            exit_map[station_id] = []
        exit_map[station_id].append({"ExitNo": exit_no, "Description": exit_description.strip()})
        processed_exit_count += 1 # 成功處理的出口數量

    os.makedirs(os.path.dirname(config.EXIT_DATA_PATH), exist_ok=True)
    with open(config.EXIT_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(exit_map, f, ensure_ascii=False, indent=4)

    print(f"--- ✅ 車站出入口資料庫已成功建立於 {config.EXIT_DATA_PATH}，共包含 {len(exit_map)} 個站點的出入口資訊，總共處理了 {processed_exit_count} 筆出口記錄。 ---") # 更新打印信息
    time.sleep(1)


if __name__ == "__main__":
    print("--- 正在開始建立所有本地資料庫，這可能需要一些時間... ---")
    build_station_database()
    build_fare_database()
    build_transfer_database()
    build_facilities_database()
    build_exit_database()
    print("\n--- ✅ 所有本地資料庫建立完成！您現在可以啟動 MetroPet AI Agent 後端服務了。 ---")
