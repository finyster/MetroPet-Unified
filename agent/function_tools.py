import json
from langchain_core.tools import tool
from services import service_registry # 從 ServiceRegistry 導入實例
from utils.exceptions import StationNotFoundError, RouteNotFoundError
import logging
from typing import Optional # 導入 Optional 類型

logger = logging.getLogger(__name__)

# 直接從 service_registry 獲取服務實例
fare_service = service_registry.get_fare_service()
routing_manager = service_registry.get_routing_manager()
station_manager = service_registry.get_station_manager()
local_data_manager = service_registry.get_local_data_manager()
tdx_api = service_registry.tdx_api # TDX API 實例也應該由 ServiceRegistry 管理
lost_and_found_service = service_registry.get_lost_and_found_service() # 新增：獲取遺失物服務
metro_soap_service = service_registry.get_metro_soap_service()
congestion_predictor = service_registry.get_congestion_predictor()

@tool
def plan_route(start_station_name: str, end_station_name: str) -> str:
    """
    【路徑規劃專家】當使用者詢問「怎麼去」、「如何搭乘」、「路線」、「要多久」、「經過哪幾站」時，專門使用此工具。
    這個工具會規劃從起點到終點的最短捷運路線，並回傳包含轉乘指引和預估時間的完整路徑。
    """
    logger.info(f"--- [工具(路徑)] 智慧規劃路線: {start_station_name} -> {end_station_name} ---")
    
    try:
        # 這裡可以考慮優先使用 metro_soap_service.get_recommand_route_soap()
        # 但這需要 routing_manager 內部邏輯調整，以決定使用哪個數據源
        # 目前仍沿用 routing_manager.find_shortest_path
        result = routing_manager.find_shortest_path(start_station_name, end_station_name)
        
        # 確保 message 字段存在，即使 path_details 為空
        if "message" not in result:
            if "path_details" in result and result["path_details"]:
                # 優化路線描述，使其更清晰
                path_description = []
                current_line = None
                for step in result['path_details']:
                    if 'line' in step and step['line']!= current_line:
                        current_line = step['line']
                        path_description.append(f"搭乘 {current_line} 線")
                    path_description.append(f"至 {step['station_name']}")
                    if 'transfer_to_line' in step:
                        path_description.append(f"轉乘 {step['transfer_to_line']} 線")
                
                result["message"] = (
                    f"從「{start_station_name}」到「{end_station_name}」的預估時間約為 {result.get('estimated_time_minutes', '未知')} 分鐘。\n"
                    f"詳細路線：{' -> '.join(path_description)}。"
                )
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
    【基礎票價查詢】當使用者僅詢問「多少錢」、「票價」、「費用」，但未指定特定身份（如老人、兒童、學生）時使用。
    此工具提供標準的「全票」和「兒童票」票價。
    如果使用者詢問特定票種（如愛心票、敬老票、學生票、台北市兒童票），請改用 `get_detailed_fare_info` 工具。
    """
    logger.info(f"--- [工具(基礎票價)] 查詢: {start_station_name} -> {end_station_name} ---")
    try:
        fare_info = fare_service.get_fare(start_station_name, end_station_name)
        message_parts = [f"從「{start_station_name}」到「{end_station_name}」的票價資訊如下："]
        
        if '全票' in fare_info:
            message_parts.append(f"全票為 NT${fare_info['全票']}。")
        if '兒童票' in fare_info:
            message_parts.append(f"兒童票為 NT${fare_info['兒童票']}。")
        
        if len(message_parts) == 1:
            message_parts.append("抱歉，目前沒有找到該路線的票價資訊。")
        else:
            message_parts.append("\n如需查詢愛心票、學生票等特殊票種，請提供您的乘客類型。")

        return json.dumps({
            "start_station": start_station_name,
            "end_station": end_station_name,
            "fare_details": fare_info,
            "message": "\n".join(message_parts)
        }, ensure_ascii=False)
    except StationNotFoundError as e:
        logger.warning(f"--- [工具(基礎票價)] 查詢時發生錯誤: {e} ---")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"--- [工具(基礎票價)] 查詢時發生未知錯誤: {e} ---", exc_info=True)
        return json.dumps({"error": f"抱歉，查詢票價時發生內部問題。"}, ensure_ascii=False)

@tool
def get_detailed_fare_info(start_station_name: str, end_station_name: str, passenger_type: str) -> str:
    """
    【特殊票價專家】當使用者詢問特定身份或票種的票價時（例如「愛心票」、「敬老票」、「學生票」、「台北市兒童」、「新北市兒童」、「一日票」、「24小時票」），專門使用此工具。
    Args:
        start_station_name (str): 起點站名。
        end_station_name (str): 終點站名。
        passenger_type (str): 必須提供一個乘客類型，例如 "愛心票", "台北市兒童", "學生票", "一日票" 等。
    """
    logger.info(f"--- [工具(詳細票價)] 查詢: {start_station_name} -> {end_station_name}, 類型: {passenger_type} ---")
    try:
        fare_details = fare_service.get_fare_details(start_station_name, end_station_name, passenger_type)
        
        if "error" in fare_details:
            return json.dumps(fare_details, ensure_ascii=False)

        message = (
            f"從「{start_station_name}」到「{end_station_name}」，"
            f"「{passenger_type}」的票價為 NT${fare_details.get('fare', '未知')}。"
            f" ({fare_details.get('description', '無詳細說明')})"
        )
        
        fare_details["message"] = message
        return json.dumps(fare_details, ensure_ascii=False)
        
    except StationNotFoundError as e:
        logger.warning(f"--- [工具(詳細票價)] 查詢時發生錯誤: {e} ---")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"--- [工具(詳細票價)] 查詢時發生未知錯誤: {e} ---", exc_info=True)
        return json.dumps({"error": f"抱歉，查詢詳細票價時發生內部問題。"}, ensure_ascii=False)

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
        timetables = timetable_data
        
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
def get_lost_and_found_info(station_name: Optional[str] = None, item_name: Optional[str] = None, days_ago: int = 7) -> str:
    """
    【遺失物專家】提供關於捷運遺失物的處理方式與查詢網址，並可查詢特定車站或物品的遺失物。
    Args:
        station_name (str, optional): 拾獲車站名稱關鍵字。
        item_name (str, optional): 物品名稱關鍵字。
        days_ago (int, optional): 查詢過去幾天內的資料。預設為 7 天。
    """
    logger.info(f"--- [工具(遺失物)] 查詢遺失物資訊: 車站={station_name}, 物品={item_name}, 過去={days_ago}天 ---")
    
    # 優先嘗試從 LostAndFoundService 查詢具體物品
    items = lost_and_found_service.query_items(station_name=station_name, item_name=item_name, days_ago=days_ago)
    
    if items:
        message_parts = [f"在過去 {days_ago} 天內，找到以下符合條件的遺失物："]
        for item in items:
            # 更新鍵名以匹配 SOAP API 的回應
            message_parts.append(
                f"物品：{item.get('ls_name', '未知物品')}, "
                f"描述：{item.get('ls_spec', '無描述')}, "
                f"拾獲地點：{item.get('get_place', '未知地點')}, "
                f"拾獲日期：{item.get('get_date', '未知日期')}。"
            )
        message_parts.append("\n您可以前往台北捷運遺失物中心或撥打客服專線詢問。")
        response = {
            "query_station": station_name,
            "query_item": item_name,
            "found_items": items,
            "message": "\n".join(message_parts)
        }
    else:
        # 如果沒有找到具體物品，則提供一般查詢指引
        response = {
            "message": (
                "抱歉，目前沒有找到符合您條件的遺失物。您可以嘗試調整查詢條件，或參考以下資訊：\n"
                "關於遺失物，您可以到台北捷運公司的官方網站查詢喔！\n"
                f"官方查詢連結：https://web.metro.taipei/pages/tw/lostandfound/search\n"
                "您可以透過上面的連結，輸入遺失物時間、地點或物品名稱來尋找。如果超過公告時間，可能就要親自到捷運遺失物中心詢問了。\n"
                "台北捷運遺失物服務中心位於中山地下街 R1 出口附近，服務時間為週二至週六 12:00~20:00。\n"
                "您也可以撥打 24 小時客服專線 AI 客服尋求協助。"
            ),
            "official_link": "https://web.metro.taipei/pages/tw/lostandfound/search",
            "instruction": "您可以透過上面的連結，輸入遺失物時間、地點或物品名稱來尋找。如果超過公告時間，可能就要親自到捷運遺失物中心詢問了。"
        }
    return json.dumps(response, ensure_ascii=False)
# --- 【 ✨✨✨ 修正並強化這個工具 ✨✨✨ 】 ---
@tool
def predict_train_congestion(station_name: str, direction: str) -> str:
    """
    【即時列車與擁擠度專家】當使用者詢問「下一班車什麼時候到」、「月台上的車還有多久來」、「現在車廂擠不擠」等關於特定車站即將到站列車的即時資訊與車廂擁擠度預測時，專門使用此工具。
    它會結合即時列車到站資料與模型預測，提供下一班車的到站時間和各車廂的擁擠程度。
    
    Args:
        station_name (str): 使用者詢問的車站名稱。
        direction (str): 使用者詢問的行駛方向或終點站。
    """
    logger.info(f"--- [工具(整合預測)] 查詢: {station_name} 往 {direction} 方向 ---")

    if not station_name or not direction:
        return json.dumps({
            "error": "Missing parameters",
            "message": "請問您想查詢哪個車站以及往哪個方向的列車資訊呢？例如「台北車站」往「南港展覽館」方向。"
        }, ensure_ascii=False)

    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)
    
    station_id = station_ids[0]

    # --- 步驟 1: 執行擁擠度預測 (永遠可靠的核心功能) ---
    congestion_result = congestion_predictor.predict_for_station(station_name, direction)
    congestion_data = congestion_result.get("congestion_by_car") if "error" not in congestion_result else None

    # --- 步驟 2: 嘗試獲取即時到站資訊 ( gracefully handling failures ) ---
    arrival_message = ""
    is_wenhu_line = station_id.startswith('BR')

    if is_wenhu_line:
        arrival_message = f"目前文湖線（「{station_name}」站）暫不支援即時列車到站時間查詢。"
    else:
        live_arrivals = tdx_api.get_station_live_board(station_id=station_id)
        if live_arrivals:
            next_train_info = None
            for arrival in live_arrivals:
                if direction in arrival.get("destination", ""):
                    next_train_info = arrival
                    break
            
            if next_train_info:
                arrival_time_min = next_train_info.get('arrival_time_minutes', '未知')
                arrival_message = f"下一班往「{next_train_info['destination']}」的列車，預計在 {arrival_time_min} 分鐘後抵達「{station_name}」站。"
            else:
                arrival_message = f"目前查無往「{direction}」方向的即時列車資訊。"
        else:
            arrival_message = f"抱歉，目前無法取得「{station_name}」站的即時列車到站資訊。"

    # --- 步驟 3: 組合最終回覆 ---
    final_message_parts = [arrival_message]

    if congestion_data:
        final_message_parts.append("\n根據預測，車廂擁擠度如下：")
        congestion_list = [f"* 第 {c['car_number']} 節車廂：{c['congestion_text']}" for c in congestion_data]
        final_message_parts.extend(congestion_list)

        if any(c['congestion_level'] >= 3 for c in congestion_data):
             final_message_parts.append("\n提醒您，部分車廂可能人潮較多，建議您往較空曠的車廂移動喔！")
        else:
             final_message_parts.append("\n看起來車廂都還蠻舒適的！")
    
    response = {
        "message": "\n".join(final_message_parts)
    }
    
    return json.dumps(response, ensure_ascii=False)

# --- 唯一的 all_tools 列表，維持原樣，供 AgentExecutor 使用 ---
all_tools = [
    plan_route,
    get_mrt_fare,
    get_detailed_fare_info, # 新增工具
    get_first_last_train_time,
    get_station_exit_info,
    get_lost_and_found_info,
    get_station_facilities,
    predict_train_congestion,
]

@tool
def get_soap_route_recommendation(start_station_name: str, end_station_name: str) -> str:
    """
    【官方建議路線】向台北捷運官方伺服器請求建議的搭乘路線。
    當使用者想知道「官方建議怎麼走」或當 `plan_route` 工具的結果不理想時，可使用此工具作為替代方案。
    """
    logger.info(f"--- [工具(官方路線)] 查詢: {start_station_name} -> {end_station_name} ---")
    try:
        # 注意：這裡我們調用 routing_manager 的新方法，而不是直接調用 soap service
        recommendation = routing_manager.get_route_recommendation_soap(start_station_name, end_station_name)
        return json.dumps(recommendation, ensure_ascii=False)
    except (StationNotFoundError, RouteNotFoundError) as e:
        logger.warning(f"--- [工具(官方路線)] 查詢時發生錯誤: {e} ---")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"--- [工具(官方路線)] 查詢時發生未知錯誤: {e} ---", exc_info=True)
        return json.dumps({"error": "抱歉，查詢官方建議路線時發生內部問題。"}, ensure_ascii=False)

# 更新 all_tools 列表
all_tools.append(get_soap_route_recommendation)