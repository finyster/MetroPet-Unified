# utils/station_name_normalizer.py

import re
import json
import os
import config

# 定義一個全局變量來儲存站點名稱到 ID 的映射，避免重複加載
_station_name_to_id_map = None

def _load_station_name_map():
    """從 mrt_station_info.json 載入站點名稱到 ID 的映射。"""
    global _station_name_to_id_map
    if _station_name_to_id_map is not None:
        return _station_name_to_id_map

    map_path = config.STATION_DATA_PATH
    if not os.path.exists(map_path):
        print(f"--- ⚠️ 警告: 站點資料檔案 {map_path} 不存在，無法載入站名標準化映射。 ---")
        _station_name_to_id_map = {}
        return _station_name_to_id_map

    try:
        with open(map_path, 'r', encoding='utf-8') as f:
            station_data = json.load(f)
            # station_data 結構是 {normalized_name: [StationID1, StationID2]}
            # 我們需要的是 {normalized_user_input: official_normalized_name}
            # 或者更直接的，{normalized_user_input: official_station_id}
            
            # 這裡我們建立一個更全面的映射，將所有標準化後的官方名稱和別名都映射到其官方名稱
            # 以便 normalize_station_name 函數可以直接返回官方名稱
            name_to_official_name = {}
            for normalized_official_name, station_ids in station_data.items():
                # 這裡的 normalized_official_name 已經是標準化後的官方中文名或英文名或別名
                # 我們需要確保它能映射回其「主要」的官方中文名稱，以便後續服務使用
                # 由於 station_map 已經包含了多個 ID，我們需要一個更穩定的官方名稱
                # 這裡假設 station_data 的 key 已經是我們希望的「標準」名稱
                name_to_official_name[normalized_official_name] = normalized_official_name 
                
            _station_name_to_id_map = station_data # 直接使用 station_data 作為映射
            print(f"--- ✅ 已載入 {len(_station_name_to_id_map)} 筆站名標準化映射。 ---")
            return _station_name_to_id_map
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"--- ❌ 錯誤: 載入站點資料檔案 {map_path} 失敗: {e} ---")
        _station_name_to_id_map = {}
        return _station_name_to_id_map

def normalize_station_name(name: str) -> str | None:
    """
    標準化站點名稱：小寫、移除括號內容、移除「站」、繁轉簡，
    並嘗試將別名轉換為其在資料庫中的標準名稱。
    """
    if not name:
        return None
    
    # 確保映射已載入
    if _station_name_to_id_map is None:
        _load_station_name_map()
    
    # 標準化輸入名稱
    normalized_input = name.lower().strip().replace("臺", "台")
    normalized_input = re.sub(r"[\(（].*?[\)）]", "", normalized_input).strip()
    if normalized_input.endswith("站"):
        normalized_input = normalized_input[:-1]

    # 嘗試直接從映射中查找
    if normalized_input in _station_name_to_id_map:
        # 返回映射中的鍵，因為它已經是標準化後的名稱
        return normalized_input
    
    # 如果直接找不到，但輸入是官方名稱的別名，我們需要確保別名能被識別
    # 由於 _station_name_to_id_map 的鍵已經包含了別名，這裡的邏輯可以簡化
    # 如果走到這裡，說明 normalized_input 不在任何已知的標準化名稱或別名中
    print(f"--- Debug: 無法將 '{name}' 標準化為已知站名。標準化後為 '{normalized_input}'。 ---")
    return None

# 在模組載入時預先載入映射
_load_station_name_map()