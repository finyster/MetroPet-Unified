import json # Keep json for potential future use, though not strictly needed for this version
import os # Keep os for file existence check (though LocalDataManager handles this)
import config # Keep config for data path (though LocalDataManager uses it)
from services.local_data_service import local_data_manager # Import LocalDataManager
from services.station_service import station_manager # Import StationManager

def get_station_exits_info(station_id: str = None, station_name: str = None):
    """
    從 LocalDataManager 獲取指定站點的出入口資訊。
    
    Args:
        station_id (str, optional): 站點 ID（如 "BL01"）。
        station_name (str, optional): 站點名稱（如 "頂埔"），通過 station_manager 進行匹配。
    
    Returns:
        list: 包含出入口資訊的列表，若無匹配則返回空列表。
    """
    # Check if exit data is loaded (LocalDataManager handles file existence)
    if not local_data_manager.exits:
        print("--- ❌ 出入口資料尚未載入。請確認 build_database.py 已成功執行且資料檔案存在。 ---")
        return []

    exit_data = local_data_manager.exits # Use data from LocalDataManager

    if station_id:
        return exit_data.get(station_id, [])
    elif station_name:
        # Use station_manager to get station IDs
        station_ids = station_manager.get_station_ids(station_name)
        
        if not station_ids:
            print(f"--- ⚠️ 找不到與站名 '{station_name}' 匹配的站點 ID。 ---")
            return []

        results = []
        for sid in station_ids:
            if sid in exit_data:
                results.extend(exit_data[sid])
        return results
    else:
        print("--- ⚠️ 請提供 station_id 或 station_name 參數。 ---")
        return []

# Remove the redundant normalize_name function
# def normalize_name(name: str) -> str:
#     """標準化站點名稱：小寫、移除括號內容、移除「站」、繁轉簡"""
#     if not name:
#         return ""
#     name = name.lower().strip().replace("臺", "台")
#     name = re.sub(r"[\(（].*?[\)）]", "", name).strip()
#     if name.endswith("站"):
#         name = name[:-1]
#     return name

if __name__ == "__main__":
    # 範例用法 (需要確保 LocalDataManager 和 StationManager 已初始化)
    # 這部分可能需要一個更完整的測試環境來運行
    print("--- 運行 services/exit_service.py 範例 ---")
    # 注意：直接運行此文件需要初始化 LocalDataManager 和 StationManager
    # 通常這個服務會在應用程式啟動時被其他模組調用
    # exits_by_id = get_station_exits_info(station_id="BL01")
    # print("出入口資訊 (按 ID):", exits_by_id)

    # exits_by_name = get_station_exits_info(station_name="頂埔")
    # print("出入口資訊 (按名稱):", exits_by_name)
    pass # Add a pass statement since the examples are commented out