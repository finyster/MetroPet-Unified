# agent/function_tools.py 

import json
from langchain_core.tools import tool
from services import service_registry # 從 ServiceRegistry 導入實例
from utils.exceptions import StationNotFoundError, RouteNotFoundError
import logging

logger = logging.getLogger(__name__)

# 直接從 service_registry 獲取服務實例
fare_service = service_registry.get_fare_service()
routing_manager = service_registry.get_routing_manager()
station_manager = service_registry.get_station_manager()
local_data_manager = service_registry.get_local_data_manager()
tdx_api = service_registry.tdx_api # TDX API 實例也應該由 ServiceRegistry 管理

@tool
def plan_route(start_station_name: str, end_station_name: str) -> str:
    """
    【路徑規劃專家】當使用者詢問「怎麼去」、「如何搭乘」、「路線」、「要多久」、「經過哪幾站」時，專門使用此工具。
    這個工具會規劃從起點到終點的最短捷運路線，並回傳包含轉乘指引和預估時間的完整路徑。
    """
    logger.info(f"--- [工具(路徑)] 智慧規劃路線: {start_station_name} -> {end_station_name} ---")
    
    try:
        result = routing_manager.find_shortest_path(start_station_name, end_station_name)
        # 確保 message 字段存在，即使 path_details 為空
        if "message" not in result:
            if "path_details" in result and result["path_details"]:
                result["message"] = f"從「{start_station_name}」到「{end_station_name}」的預估時間約為 {result.get('estimated_time_minutes', '未知')} 分鐘。詳細路線：{' '.join(result['path_details'])}"
            else:
                result["message"] = f"抱歉，無法從「{start_station_name}」規劃到「{end_station_name}」的捷運路線。"
        return json.dumps(result, ensure_ascii=False)
    except (StationNotFoundError, RouteNotFoundError) as e:
        logger.warning(f"--- [工具(路徑)] 規劃路線時發生錯誤: {e} ---")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"--- [工具(路徑)] 規劃路線時發生未知錯誤: {e} ---", exc_info=True)
        return json.dumps({"error": f"抱歉，規劃路線時發生內部問題。錯誤訊息：{e}"}, ensure_ascii=False)


@tool
def get_mrt_fare(start_station_name: str, end_station_name: str) -> str:
    """
    【票價查詢專家】當使用者明確詢問「多少錢」、「票價」、「費用」時，專門使用此工具。
    這個工具只回傳票價資訊（全票與兒童票），不提供路線規劃。
    """
    logger.info(f"--- [工具(票價)] 查詢票價: {start_station_name} -> {end_station_name} ---")
    
    try:
        fare_info = fare_service.get_fare(start_station_name, end_station_name)
        return json.dumps({
            "start_station": start_station_name,
            "end_station": end_station_name,
            "full_fare": fare_info.get('full_fare', '未知'),
            "child_fare": fare_info.get('child_fare', '未知'),
            "message": f"從「{start_station_name}」到「{end_station_name}」的全票票價為 NT${fare_info.get('full_fare', '未知')}，兒童票為 NT${fare_info.get('child_fare', '未知')}。"
        }, ensure_ascii=False)
    except StationNotFoundError as e:
        logger.warning(f"--- [工具(票價)] 查詢票價時發生錯誤: {e} ---")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"--- [工具(票價)] 查詢票價時發生未知錯誤: {e} ---", exc_info=True)
        return json.dumps({"error": f"抱歉，查詢票價時發生內部問題。錯誤訊息：{e}"}, ensure_ascii=False)

@tool
def get_first_last_train_time(station_name: str) -> str:
    """
    【首末班車專家】查詢指定捷運站點，各個方向（終點站）的首班車與末班車時間。
    """
    logger.info(f"--- [工具(首末班車)] 查詢首末班車時間: {station_name} ---")
    
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)
    
    station_id_to_query = station_ids[0] 
    timetable_data = tdx_api.get_first_last_timetable(station_id_to_query)
    
    if timetable_data:
        timetables = [{"direction": item.get("TripHeadSign", "未知方向"), "first_train": item.get("FirstTrainTime", "N/A"), "last_train": item.get("LastTrainTime", "N/A")} for item in timetable_data]
        
        message_parts = [f"「{station_name}」站的首末班車時間如下："]
        for entry in timetables:
            message_parts.append(f"往 {entry['direction']} 方向：首班車 {entry['first_train']}，末班車 {entry['last_train']}。")
        message_parts.append("請注意，首班車和末班車時間可能會因為特殊情況或維修而有所變動。")

        return json.dumps({"station": station_name, "timetable": timetables, "message": "\n".join(message_parts)}, ensure_ascii=False)
    
    return json.dumps({"error": f"查無 '{station_name}' 的首末班車資訊。"}, ensure_ascii=False)

@tool
def get_station_exit_info(station_name: str) -> str:
    """
    【車站出口專家】查詢指定捷運站的出口資訊，包括出口編號以及附近的街道或地標。
    """
    logger.info(f"--- [工具(出口)] 查詢車站出口: {station_name} ---")
    
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids: return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)

    exit_map = local_data_manager.exits
    all_exits_formatted = []
    for sid in station_ids:
        if sid in exit_map:
            for exit_detail in exit_map[sid]:
                exit_no = exit_detail.get('ExitNo', 'N/A')
                description = exit_detail.get('Description', '無描述')
                all_exits_formatted.append(f"出口 {exit_no}: {description}")
            
    if all_exits_formatted:
        if all(e.endswith(": 無描述") for e in all_exits_formatted):
            message = f"「{station_name}」站目前有 {len(all_exits_formatted)} 個出入口，但詳細描述資訊暫時無法提供。出入口編號為：{', '.join([e.split(':')[0].replace('出口 ', '') for e in all_exits_formatted])}。"
            return json.dumps({"station": station_name, "exits": all_exits_formatted, "message": message}, ensure_ascii=False)
        else:
            message = f"「{station_name}」站的出入口資訊如下：\n" + "\n".join(all_exits_formatted)
            return json.dumps({"station": station_name, "exits": all_exits_formatted, "message": message}, ensure_ascii=False)
        
    return json.dumps({"error": f"找不到車站「{station_name}」的出口資訊。"}, ensure_ascii=False)

@tool
def get_station_facilities(station_name: str) -> str:
    """
    【車站設施專家】查詢指定捷運站的內部設施資訊，如廁所、電梯、詢問處等。
    """
    logger.info(f"--- [工具(設施)] 查詢車站設施: {station_name} ---")
    
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids: return json.dumps({"error": f"抱歉，我找不到名為「{station_name}」的捷運站。"}, ensure_ascii=False)
    
    facilities_map = local_data_manager.facilities
    all_facilities_desc = []
    for sid in station_ids:
        if sid in facilities_map:
            all_facilities_desc.append(facilities_map[sid])
    
    if not all_facilities_desc: 
        return json.dumps({"error": f"抱歉，查無「{station_name}」的設施資訊。"}, ensure_ascii=False)
    
    combined_description = "\n".join(all_facilities_desc)

    if combined_description.strip() == "無詳細資訊" or all(desc.strip() == "無詳細資訊" for desc in all_facilities_desc):
        message = f"「{station_name}」站目前無詳細設施描述資訊。"
        return json.dumps({"station": station_name, "facilities_info": combined_description, "message": message}, ensure_ascii=False)
    else:
        message = f"「{station_name}」站的設施資訊如下：\n{combined_description}"
        return json.dumps({"station": station_name, "facilities_info": combined_description, "message": message}, ensure_ascii=False)

@tool
def get_lost_and_found_info() -> str:
    """
    【遺失物專家】提供關於捷運遺失物的處理方式與查詢網址。
    """
    logger.info(f"--- [工具(遺失物)] 提供遺失物查詢資訊 ---")
    response = { "message": "關於遺失物，您可以到台北捷運公司的官方網站查詢喔！", "official_link": "https://web.metro.taipei/pages/tw/lostandfound/search", "instruction": "您可以透過上面的連結，輸入遺失物時間、地點或物品名稱來尋找。如果超過公告時間，可能就要親自到捷運遺失物中心詢問了。" }
    return json.dumps(response, ensure_ascii=False)

# --- 唯一的 all_tools 列表，維持原樣，供 AgentExecutor 使用 ---
all_tools = [
    plan_route,
    get_mrt_fare,
    get_first_last_train_time,
    get_station_exit_info,
    get_lost_and_found_info,
    get_station_facilities,
]