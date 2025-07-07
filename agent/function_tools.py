# agent/function_tools.py
import json
from langchain_core.tools import tool
from services.tdx_service import tdx_api
from services.station_service import station_manager
# 匯入我們全新的路線規劃服務
from services.routing_service import routing_manager

@tool
def get_mrt_fare(start_station_name: str, end_station_name: str) -> str:
    """查詢台北捷運從一個站到另一個站的票價。"""
    # ... (此工具程式碼不變)
    print(f"--- [工具] 查詢票價: {start_station_name} -> {end_station_name} ---")
    start_id = station_manager.get_station_id(start_station_name)
    end_id = station_manager.get_station_id(end_station_name)
    if not start_id or not end_id:
        missing = [name for name, id_val in [(start_station_name, start_id), (end_station_name, end_id)] if not id_val]
        return json.dumps({"error": f"找不到車站: {', '.join(missing)}"}, ensure_ascii=False)
    fare_data = tdx_api.get_mrt_fare(start_id, end_id)
    if fare_data and fare_data[0].get('Fares'):
        fares = {f.get('TicketType', '未知').replace('票', ''): f.get('Price', -1) for f in fare_data[0]['Fares']}
        return json.dumps({"fares": fares}, ensure_ascii=False)
    return json.dumps({"error": "無法查詢到票價資訊"}, ensure_ascii=False)

# --- 【核心修改】加入全新的路線規劃工具 ---
@tool
def plan_route(start_station_name: str, end_station_name: str) -> str:
    """
    規劃從起點到終點的最短捷運路線。
    當使用者問「怎麼去」、「如何搭乘」、「路線」時使用。
    """
    print(f"--- [工具] 規劃路線: {start_station_name} -> {end_station_name} ---")
    result = routing_manager.find_shortest_path(start_station_name, end_station_name)
    return json.dumps(result, ensure_ascii=False)

@tool
def get_first_last_train_time(station_name: str) -> str:
    """查詢指定車站的首班車與末班車時間。"""
    print(f"--- [工具] 查詢首末班車時間: {station_name} ---")
    station_id = station_manager.get_station_id(station_name)
    if not station_id:
        return json.dumps({"error": f"找不到車站: {station_name}"}, ensure_ascii=False)
    
    timetable_data = tdx_api.get_first_last_timetable(station_id)
    
    if timetable_data:
        timetables = []
        for item in timetable_data:
            timetables.append({
                "direction": item.get("TripHeadSign", "未知方向"),
                "first_train": item.get("FirstTrainTime", "N/A"),
                "last_train": item.get("LastTrainTime", "N/A")
            })
        return json.dumps({"station": station_name, "timetable": timetables}, ensure_ascii=False)
    
    return json.dumps({"error": f"查無 '{station_name}' 的首末班車資訊"}, ensure_ascii=False)


# --- 最終的工具列表 ---
all_tools = [
    get_mrt_fare,
    plan_route,
    get_first_last_train_time,
]