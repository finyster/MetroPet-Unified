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
import pandas as pd # 確保頂部有 import pandas

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

# --- ✨【核心修改：以本地 SID Map 為主的全新函式】✨ ---
def build_station_database():
    """
    從本地最完整的 stations_sid_map.json 建立站點資料庫，
    並從 TDX API 補充英文站名，最後整合詳細別名。
    """
    print("\n--- [1/6] 正在建立「站點資料庫」(主要來源: stations_sid_map.json)... ---")
    
    sid_map_path = config.STATIONS_SID_MAP_PATH
    if not os.path.exists(sid_map_path):
        print(f"--- ❌ 步驟 1 失敗: 找不到核心資料檔 {sid_map_path} ---")
        return

    # 1. 讀取最完整的 SID Map 作為基礎
    with open(sid_map_path, 'r', encoding='utf-8') as f:
        sid_map_data = json.load(f)

    # 2. 從 TDX API 獲取資料，僅用於補充英文站名
    print("--- 正在從 TDX API 獲取英文站名補充資料... ---")
    tdx_stations = tdx_api.get_all_stations()
    tdx_id_to_en_name = {}
    if tdx_stations:
        for station in tdx_stations:
            station_id = station.get("StationID")
            en_name = station.get("StationName", {}).get("En")
            if station_id and en_name:
                tdx_id_to_en_name[station_id] = en_name

    station_map = {}
    
    # 3. 遍歷 SID Map，建立基礎的 中文名 -> [ID列表] 映射
    for item in sid_map_data:
        zh_name = item.get("SCNAME")
        tdx_id = item.get("SCODE")
        if zh_name and tdx_id:
            # 忽略地下街等非捷運站的SCODE
            if 'MALL' in tdx_id: continue
            
            norm_zh_name = normalize_name(zh_name)
            station_map.setdefault(norm_zh_name, set()).add(tdx_id)

            # 補充英文名稱
            if tdx_id in tdx_id_to_en_name:
                norm_en_name = normalize_name(tdx_id_to_en_name[tdx_id])
                station_map.setdefault(norm_en_name, set()).add(tdx_id)

    # 4. 整合您提供的超詳細別名地圖
    alias_map = {
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
        "SOGO": "忠孝復興",
        "永康街": "東門",
        "台大": "公館",
        "師大夜市": "台電大樓",
        "寧夏夜市": "雙連",
        "饒河夜市": "松山",
        "士林夜市": "劍潭",
        "新光三越": "中山",
        "華山文創": "忠孝新生",
        "松菸": "國父紀念館",
        "光華商場": "忠孝新生",
        "三創": "忠孝新生",
        "貓纜": "動物園",
        "溫泉": "新北投",
        "漁人碼頭": "淡水",
        "大稻埕": "北門",
        "花博": "圓山",
        "行天宮拜拜": "行天宮",
        "南門市場": "中正紀念堂",

        # ===== 醫院與學校 (Hospitals & Schools) =====
        "榮總": "石牌",
        "台大分院": "台大醫院",
        "師大": "古亭",
        "台科大": "公館",
        "北科大": "忠孝新生",

        # ===== 交通樞紐 (Transportation Hubs) =====
        "台北火車站": "台北車站",
        "板橋火車站": "板橋",
        "高鐵站": "台北車站",
        "松山火車站": "松山",
        "南港火車站": "南港",

        # ===== 常見口誤或變體 (Common Misspellings / Variants) =====
        "象山步道": "象山",
        "江子翠站": "江子翠",
        "萬芳": "萬芳醫院",
        "台電大樓站": "台電大樓",
        "大安站": "大安",
        "永春站": "永春",
        "後山埤站": "後山埤",
        "昆陽站": "昆陽",
        "Jhongxiao": "忠孝復興",
        "CKS Memorial Hall": "中正紀念堂",
    }
    
    for alias, primary_name in alias_map.items():
        norm_alias = normalize_name(alias)
        norm_primary = normalize_name(primary_name)
        if norm_primary in station_map:
            station_map[norm_alias] = station_map[norm_primary]

    # 5. 最終處理與儲存
    station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
    
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

# --- ✨【核心修改處：從 CSV 讀取設施資料】✨ ---
def build_facilities_database():
    """
    從手動下載的 mrt_station_facilities_raw.csv 讀取詳細設施資訊，
    並轉換為 Agent 所需的 JSON 格式。
    """
    print("\n--- [5/6] 正在從 CSV 建立「車站設施資料庫」... ---")
    
    # 【步驟1 修改】將檔名改為英文，增加可讀性與相容性
    csv_path = os.path.join(config.DATA_DIR, 'mrt_station_facilities_raw.csv')
    station_map_path = config.STATION_DATA_PATH

    if not os.path.exists(csv_path):
        print(f"--- ❌ 步驟 5 失敗: 找不到設施 CSV 檔案 -> {csv_path} ---")
        print("--- 👉 請確認您已將下載的 CSV 重新命名為 mrt_station_facilities_raw.csv 並放置到 data 資料夾。 ---")
        return
        
    if not os.path.exists(station_map_path):
        print(f"--- ❌ 步驟 5 失敗: 找不到站點地圖檔案 -> {station_map_path} ---")
        print("--- 👉 請先執行 `python build_database.py --name stations` 來生成此檔案。 ---")
        return

    try:
        # 載入站點名稱到 ID 的映射表，以便對應
        with open(station_map_path, 'r', encoding='utf-8') as f:
            station_map = json.load(f)

        # 【步驟2 修改】讀取 CSV 時，明確指定使用 'utf-8' 編碼來解決亂碼問題
        df = pd.read_csv(csv_path, encoding='utf-8')
        
        facilities_map = {}
        
        # 遍歷 CSV 中的每一行
        for _, row in df.iterrows():
            station_name_raw = row.get('車站名稱')
            if not station_name_raw or pd.isna(station_name_raw):
                continue
            
            # 標準化 CSV 中的站名，以便在我們的站點地圖中查找
            norm_name = normalize_name(station_name_raw)
            station_ids = station_map.get(norm_name)
            
            if not station_ids:
                print(f"--- ⚠️ 警告: 在站點地圖中找不到 '{station_name_raw}' 的對應 ID，跳過此站設施。 ---")
                continue

            # 將所有設施欄位的資訊整合成一個易讀的字串
            info_parts = []
            facility_columns = {
                "電梯": row.get('電梯'), "電扶梯": row.get('電扶梯'),
                "銀行ATM": row.get('銀行ATM'), "哺乳室": row.get('哺乳室'),
                "飲水機": row.get('飲水機'), "充電站": row.get('充電站'),
                "廁所": row.get('廁所')
            }

            for name, value in facility_columns.items():
                if value and not pd.isna(value):
                    # 將換行符轉為易讀格式，並加上標題
                    formatted_value = str(value).replace('\n', ', ')
                    info_parts.append(f"【{name}】\n{formatted_value}")
            
            final_info = "\n\n".join(info_parts) if info_parts else "無詳細設施資訊。"

            # 為此站所有可能的 ID 都填上相同的設施資訊
            for sid in station_ids:
                facilities_map[sid] = final_info

        # 儲存結果
        with open(config.FACILITIES_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(facilities_map, f, ensure_ascii=False, indent=4)

        print(f"--- ✅ 車站設施資料庫已成功建立，共處理 {len(facilities_map)} 個站點 ID 的設施資訊。 ---")

    except UnicodeDecodeError:
        print("--- ❌ 讀取 CSV 失敗，使用 UTF-8 解碼失敗。請嘗試手動用 VS Code 或記事本等工具將 CSV 檔案「另存為 UTF-8」格式後再試一次。 ---")
    except Exception as e:
        print(f"--- ❌ 步驟 5 失敗: 處理 CSV 或建立 JSON 時發生錯誤: {e} ---")

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