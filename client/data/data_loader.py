# data/data_loader.py

import json
import os
import config
from utils.exceptions import DataValidationError

def _load_json_file(path: str, data_name: str) -> dict:
    """一個健壯的 JSON 載入函式。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"--- ✅ [DataLoader] {data_name}資料庫已載入，共 {len(data)} 筆。")
            return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"--- ❌ [DataLoader] 警告：載入 {data_name} 資料檔案 {path} 失敗: {e} ---")
        raise DataValidationError(f"載入 {data_name} 資料檔案失敗: {e}")

def load_all_mrt_data() -> dict:
    """
    統一載入所有本地捷運資料庫。
    """
    print("--- [DataLoader] 正在載入所有本地資料庫... ---")
    mrt_data = {}
    try:
        mrt_data['fares'] = _load_json_file(config.FARE_DATA_PATH, "票價")
        mrt_data['facilities'] = _load_json_file(config.FACILITIES_DATA_PATH, "設施")
        mrt_data['exits'] = _load_json_file(config.EXIT_DATA_PATH, "出口")
        mrt_data['stations_map'] = _load_json_file(config.STATION_DATA_PATH, "站點映射") # 站名到ID的映射
        # connections 和 lines 數據目前沒有獨立的 JSON，但未來重構後會加入
        # mrt_data['connections'] = _load_json_file(config.CONNECTIONS_DATA_PATH, "連線")
        # mrt_data['lines'] = _load_json_file(config.LINES_DATA_PATH, "路線")
        print("--- ✅ [DataLoader] 所有資料庫載入完成。 ---")
    except DataValidationError as e:
        print(f"--- ❌ [DataLoader] 載入部分資料庫失敗，請檢查 build_database.py 是否已成功運行。詳情: {e} ---")
        # 這裡可以選擇拋出異常或返回部分數據
        raise ServiceInitializationError(f"資料載入失敗，服務無法初始化: {e}")
    return mrt_data

# 這裡不直接初始化 data_loader，而是讓 ServiceRegistry 來調用 load_all_mrt_data
# 確保資料載入的時機和順序由 ServiceRegistry 控制