# build_database.py

import os
import json
import re
import time
import config
from services.tdx_service import tdx_api
import argparse # ✨ 新增這一行
import requests
from bs4 import BeautifulSoup

# --- 【✨核心新增✨】確保您在檔案最上方，匯入了 metro_soap_api ---
from services.metro_soap_service import metro_soap_api

# 為了避免循環依賴和簡化，我們在這裡重新定義一個與 StationManager 內部邏輯相同的 normalize_name 函數。
def normalize_name(name: str) -> str:
    """標準化站點名稱：小寫、移除括號內容、移除「站」、繁轉簡"""
    if not name: return ""
    name = name.lower().strip().replace("臺", "台")
    name = re.sub(r"[\(（].*?[\)）]", "", name).strip()
    
    # --- 【✨核心修正✨】使用更安全的方式移除字尾 ---
    if name.endswith("站"):
        name = name.removesuffix("站")
        
    return name

# <--- 這裡原本 build_station_database 的內容已經被清空 --->
def build_station_database():
    """從 TDX API 獲取所有捷運站點資訊，並儲存為 JSON 檔案。"""
    print("\n--- [1/5] 正在建立「站點資料庫」... ---")
    all_stations_data = tdx_api.get_all_stations_of_route()
    if not all_stations_data:
        print("--- ❌ 步驟 1 失敗: 無法獲取車站資料。請檢查 API 金鑰與網路。 ---")
        return

    station_map = {}
    official_names = set()

    # 第一輪：先從 API 結果中，收集所有官方的中文站名
    print("--- 正在收集官方站名... ---")
    for route in all_stations_data:
        for station in route.get("Stations", []):
            zh_name = station.get("StationName", {}).get("Zh_tw")
            if zh_name:
                official_names.add(zh_name)
    print(f"--- 共收集到 {len(official_names)} 個不重複的官方站名。 ---")

    # --- 【✨終極版別名地圖✨】 ---
    alias_map = {}

    # 1. 自動為所有官方站名加上「站」字尾的別名
    for name in official_names:
        alias_map[f"{name}站"] = name

    # 2. 手動加入所有已知的別名、簡稱、錯字、地標、外語等
    alias_map.update({
        # === 常用縮寫/簡稱 ===
        "北車": "台北車站", "台車": "台北車站",
        "市府": "市政府",
        "松機": "松山機場",
        "國館": "國父紀念館",
        "中紀": "中正紀念堂", "中正廟": "中正紀念堂",
        "南展": "南港展覽館", "南展館": "南港展覽館",
        "大安森": "大安森林公園", "森林公園": "大安森林公園",
        "西門町": "西門",
        "美麗華": "劍南路",
        "北藝": "劍南路",
        "內科": "內湖",
        "南軟": "南港軟體園區",
        "新產園區": "新北產業園區",

        # === 英文/拼音 ===
        "Taipei Main Station": "台北車站", "Taipei Main": "台北車站",
        "Taipei 101": "台北101/世貿", "Taipei 101 Station": "台北101/世貿", "World Trade Center": "台北101/世貿",
        "Songshan Airport": "松山機場",
        "Taipei Zoo": "動物園", "Tpe Zoo": "動物園", "Muzha Zoo": "動物園",
        "Ximen": "西門",
        "Shilin": "士林",
        "Longshan Temple": "龍山寺",
        "Miramar": "劍南路",
        
        # === 日文漢字 ===
        "台北駅": "台北車站",
        "市政府駅": "市政府",
        "台北101駅": "台北101/世貿",
        "動物園駅": "動物園",

        # === 口語/地標/錯字 ===
        "101": "台北101/世貿", "101大樓": "台北101/世貿",
        "世貿": "台北101/世貿", "世貿中心": "台北101/世貿",
        "木柵動物園": "動物園",
        "士淋": "士林", # 常見錯字
        "關度": "關渡",

        # ===== 地標與商圈 (Landmarks & Shopping Districts) =====
        "SOGO": "忠孝復興",              # SOGO百貨就在忠孝復興站
        "永康街": "東門",                # 永康街商圈的主要入口
        "台大": "公館",                  # 台灣大學正門口
        "師大夜市": "台電大樓",            # 師大夜市的主要入口站
        "寧夏夜市": "雙連",              # 寧夏夜市的主要入口站
        "饒河夜市": "松山",              # 饒河街夜市就在松山站旁
        "士林夜市": "劍潭",              # 劍潭站是士林夜市的主要出入口
        "新光三越": "中山",              # 中山站南西商圈
        "華山文創": "忠孝新生",            # 華山1914文化創意產業園區
        "松菸": "國父紀念館",            # 松山文創園區
        "光華商場": "忠孝新生",            # 台北的電子產品集散地
        "三創": "忠孝新生",              # 三創生活園區
        "貓纜": "動物園",                # 貓空纜車的起點站
        "溫泉": "新北投",                # 新北投以溫泉聞名
        "漁人碼頭": "淡水",              # 淡水漁人碼頭
        "大稻埕": "北門",                # 大稻埕碼頭、迪化街商圈
        "花博": "圓山",                  # 花博公園
        "行天宮拜拜": "行天宮",          # 口語化的說法
        "南門市場": "中正紀念堂",        # 南門市場新址

        # ===== 醫院與學校 (Hospitals & Schools) =====
        "榮總": "石牌",                  # 台北榮民總醫院
        "台大分院": "台大醫院",
        "師大": "古亭",                  # 台灣師範大學
        "台科大": "公館",                # 台灣科技大學
        "北科大": "忠孝新生",            # 台北科技大學

        # ===== 交通樞紐 (Transportation Hubs) =====
        "台北火車站": "台北車站",
        "板橋火車站": "板橋",
        "高鐵站": "台北車站",            # 在台北市區通常指台北車站
        "松山火車站": "松山",
        "南港火車站": "南港",

        # ===== 常見口誤或變體 (Common Misspellings / Variants) =====
        "象山步道": "象山",
        "江子翠站": "江子翠",
        "萬芳": "萬芳醫院",              # 口語上常省略"醫院"
        "台電大樓站": "台電大樓",
        "大安站": "大安",
        "永春站": "永春",
        "後山埤站": "後山埤",
        "昆陽站": "昆陽",
        "Jhongxiao": "忠孝復興",         # 威妥瑪拼音的變體
        "CKS Memorial Hall": "中正紀念堂", # 英文全稱
    })
    
    # --- 第二輪：開始建立包含所有別名的完整 station_map ---
    print("--- 正在建立包含別名的完整站點地圖... ---")
    for route in all_stations_data:
        for station in route.get("Stations", []):
            zh_name = station.get("StationName", {}).get("Zh_tw")
            en_name = station.get("StationName", {}).get("En")
            station_id = station.get("StationID")

            if zh_name and station_id:
                # 將官方中文名和英文名加入 map
                norm_zh_name = normalize_name(zh_name)
                station_map.setdefault(norm_zh_name, set()).add(station_id)
                if en_name:
                    norm_en_name = normalize_name(en_name)
                    station_map.setdefault(norm_en_name, set()).add(station_id)

    # 將別名也指向正確的 ID 集合
    for alias, primary_name in alias_map.items():
        norm_alias = normalize_name(alias)
        norm_primary = normalize_name(primary_name)
        if norm_primary in station_map:
            station_map[norm_alias] = station_map[norm_primary]

    # 將 set 轉換為排序後的 list 以便 JSON 儲存
    station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
    
    os.makedirs(os.path.dirname(config.STATION_DATA_PATH), exist_ok=True)
    with open(config.STATION_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(station_map_list, f, ensure_ascii=False, indent=2)
    print(f"--- ✅ 站點資料庫建立成功，共 {len(station_map_list)} 個站名/別名。 ---")
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
        print("--- ⚠️ 步驟 4 失敗: 無法獲取車站設施資料，可能因 429 錯誤。 ---")
        return

    facilities_map = {}
    for facility in all_facilities_data:
        station_id = facility.get('StationID')
        if station_id:
            description = facility.get('FacilityDescription', '無詳細資訊').replace('\r\n', '\n').strip()
            if station_id not in facilities_map:
                facilities_map[station_id] = []
            facilities_map[station_id].append(description)

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
        print("--- ❌ 步驟 5 失敗: 無法獲取車站出入口資料。 ---")
        return

    exit_map = {}
    processed_exit_count = 0
    for exit_info in all_exits_data:
        station_id = exit_info.get("StationID")
        exit_no = exit_info.get("ExitID")
        if exit_no is None:
            exit_no = exit_info.get("''ExitID'") 

        exit_description_obj = exit_info.get("ExitDescription", {})
        exit_description = exit_description_obj.get("Zh_tw", "無描述")
        
        if not (station_id and exit_no):
            print(f"--- ⚠️ Skipping exit info due to missing StationID or ExitNo: {exit_info} ---")
            continue
        
        if station_id not in exit_map:
            exit_map[station_id] = []
        exit_map[station_id].append({"ExitNo": exit_no, "Description": exit_description.strip()})
        processed_exit_count += 1

    os.makedirs(os.path.dirname(config.EXIT_DATA_PATH), exist_ok=True)
    with open(config.EXIT_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(exit_map, f, ensure_ascii=False, indent=4)

    print(f"--- ✅ 車站出入口資料庫已成功建立於 {config.EXIT_DATA_PATH}，共包含 {len(exit_map)} 個站點的出入口資訊，總共處理了 {processed_exit_count} 筆出口記錄。 ---")
    time.sleep(1)
    
# --- 【✨最終簡化版✨】 ---
def build_lost_and_found_database():
    """
    從 metro_soap_api 獲取所有遺失物資訊，並儲存為 JSON 檔案。
    """
    print("\n--- [6/6] 正在建立「遺失物資料庫」... ---")
    
    try:
        # 直接呼叫我們在 MetroSoapApi 中建立好的新方法
        items = metro_soap_api.get_all_lost_items()

        # 檢查 API 呼叫是否成功
        if items is None: # 如果 get_all_lost_items 回傳 None，代表呼叫失敗
            print("--- ❌ 步驟 6 失敗: 從 metro_soap_api 獲取遺失物資料失敗。請檢查日誌。 ---")
            return

        # 將獲取的資料寫入本地檔案
        with open(config.LOST_AND_FOUND_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        print(f"--- ✅ 遺失物資料庫建立成功，共寫入 {len(items)} 筆資料。 ---")

    except Exception as e:
        print(f"--- ❌ 步驟 6 失敗: 建立遺失物資料庫時發生未知錯誤: {e} ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build local databases for the MetroPet AI Agent.")
    parser.add_argument(
        "--name", 
        type=str,
        default="all",
        choices=["stations", "fares", "transfers", "facilities", "exits", "lost_and_found", "all"],
        help="Specify which database to build. Use 'all' to build everything."
    )
    args = parser.parse_args()

    if args.name == "all":
        print("--- 正在開始建立所有本地資料庫，這可能需要一些時間... ---")
        build_station_database()
        build_fare_database()
        build_transfer_database()
        build_facilities_database()
        build_exit_database()
        build_lost_and_found_database()
        print("\n--- ✅ 所有本地資料庫建立完成！ ---")
    
    elif args.name == "stations":
        build_station_database()
    elif args.name == "fares":
        build_fare_database()
    elif args.name == "transfers":
        build_transfer_database()
    elif args.name == "facilities":
        build_facilities_database()
    elif args.name == "exits":
        build_exit_database()
    elif args.name == "lost_and_found":
        build_lost_and_found_database()