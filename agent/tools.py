# agent/function_tools.py

from langchain_core.tools import tool

# --- 導入我們升級後的本地資料服務 ---
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
    """查詢特定捷運站點的所有出口資訊，包含出口編號和位置描述。"""
    print(f"--- [工具] 正在從本地檔案查詢出口資訊: {station_name} ---")
    exit_info = local_data_manager.get_exits_by_station(station_name)
    if exit_info:
        return exit_info
    return f"抱歉，我在本地資料中查不到 '{station_name}' 的出口資訊，請檢查站名是否正確。"

# ---【新工具】---
@tool
def get_travel_time_between_adjacent_stations(station_A: str, station_B: str) -> str:
    """
    查詢台北捷運【相鄰兩站】之間的預估行駛時間。
    注意：此工具僅適用於直接相連的下一站，無法計算多站旅程。
    """
    print(f"--- [工具] 正在查詢相鄰站點時間: {station_A} <-> {station_B} ---")
    
    time_info = local_data_manager.get_adjacent_travel_time(station_A, station_B)
    
    if time_info:
        travel_time = time_info.get('行駛時間(秒)', '未知')
        stop_time = time_info.get('停靠時間(秒)', '未知')
        return (f"從 {station_A} 到相鄰的 {station_B}：\n"
                f"- 預估行駛時間約為 {travel_time} 秒。\n"
                f"- 列車在該站的預估停靠時間約為 {stop_time} 秒。")
    
    return f"抱歉，我無法查詢到 {station_A} 與 {station_B} 之間的相鄰站點資訊，它們可能不是相鄰的兩站。"


# --- 更新後的最終工具列表 ---
all_tools = [
    get_mrt_fare, 
    get_station_exit_info,
    get_travel_time_between_adjacent_stations # <- 加入新工具
]