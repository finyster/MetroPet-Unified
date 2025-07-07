# agent/function_tools.py

from langchain_core.tools import tool
from services.local_data_service import local_data_manager

@tool
def get_mrt_fare(start_station_name: str, end_station_name: str) -> str:
    """查詢台北捷運從起點站到終點站的單程票票價。"""
    print(f"--- [工具] 正在從本地檔案查詢票價: {start_station_name} -> {end_station_name} ---")
    price = local_data_manager.get_fare(start_station_name, end_station_name)
    if price is not None:
        return f"從 {start_station_name} 到 {end_station_name} 的單程票價是 {price} 元。"
    return f"抱歉，我在本地資料中查不到從 {start_station_name} 到 {end_station_name} 的票價資訊。"

@tool
def get_station_exit_info(station_name: str) -> str:
    """查詢特定捷運站點的所有出口資訊。"""
    print(f"--- [工具] 正在從本地檔案查詢出口資訊: {station_name} ---")
    exit_info = local_data_manager.get_exits_by_station(station_name)
    if exit_info:
        return exit_info
    return f"抱歉，我在本地資料中查不到 '{station_name}' 的出口資訊，請檢查站名是否正確。"

# ---【工具強化】---
@tool
def get_estimated_travel_time(start_station: str, end_station: str) -> str:
    """
    計算在【同一條路線上】從起點站到終點站的總預估行駛時間。
    如果兩站不在同一條直達路線上，此工具將無法計算。
    """
    print(f"--- [工具] 正在計算總行駛時間: {start_station} -> {end_station} ---")
    
    # 直接呼叫我們在 service 中寫好的複雜計算邏輯
    travel_time_info = local_data_manager.calculate_travel_time(start_station, end_station)
    
    if travel_time_info:
        return travel_time_info
    
    return f"抱歉，計算從 {start_station} 到 {end_station} 的時間時發生錯誤。"

# --- 更新後的最終工具列表 ---
all_tools = [
    get_mrt_fare, 
    get_station_exit_info,
    get_estimated_travel_time # <- 使用強化版的新工具
]