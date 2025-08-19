import json
from langchain_core.tools import tool
from services import service_registry # 從 ServiceRegistry 導入實例
from utils.exceptions import StationNotFoundError, RouteNotFoundError, DataLoadError 
import logging
from typing import Optional # 導入 Optional 類型
from datetime import datetime, timedelta # 新增：導入 datetime 和 timedelta
import dateparser
import random, re
# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 直接從 service_registry 獲取服務實例
fare_service = service_registry.get_fare_service()
routing_manager = service_registry.get_routing_manager()
station_manager = service_registry.get_station_manager()
local_data_manager = service_registry.get_local_data_manager()
tdx_api = service_registry.tdx_api
lost_and_found_service = service_registry.get_lost_and_found_service()
metro_soap_service = service_registry.get_metro_soap_service()
congestion_predictor = service_registry.get_congestion_predictor()
first_last_train_time_service =  service_registry.get_first_last_train_time_service()

# 修正：在所有依賴服務都載入後再初始化 RealtimeMRTService
from services.realtime_mrt_service import RealtimeMRTService
realtime_mrt_service = RealtimeMRTService(metro_soap_api=metro_soap_service, station_manager=station_manager)
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
    【暖心班次小助理】當使用者可能錯過列車，或是在深夜、清晨查詢班次時，用這個工具來查詢指定捷運站的首末班車時間。它會用友善貼心的方式回報，並提供溫馨提醒和可愛的小圖示。
    """
    logger.info(f"--- [工具(首末班車)] 查詢首末班車時間: {station_name} ---")
    
    first_last_train_time_service = service_registry.first_last_train_time_service

    if first_last_train_time_service is None:
        logger.error("FirstLastTrainTimeService 未初始化。請檢查 ServiceRegistry 的初始化流程。")
        return json.dumps({"error": "🥺 抱歉！目前捷運資訊服務好像有點小狀況，請您稍後再試試看喔！"}, ensure_ascii=False)

    try:
        timetable_data = first_last_train_time_service.get_timetable_for_station(station_name)
        
        if timetable_data:
            current_hour = datetime.now().hour

            # --- 訊息美化與個人化 ---

            # 隨機選擇開場白，增加變化性
            openings = [
                f"🎉 嗨嗨！我來幫您看看「{station_name}」站的班次喔！💪",
                f"💖 好的，馬上為您查詢「{station_name}」站的首末班車時間～ 請稍等一下下！",
                f"✨ 這是「{station_name}」站的詳細時刻表，希望對您有幫助喔！👇"
            ]
            message_parts = [random.choice(openings)]

            # 根據當前時間給予不同情境的提醒
            if current_hour >= 22 or current_hour <= 1:
                message_parts.append("\n🌙 現在時間比較晚囉，要特別注意末班車時間，別錯過囉！🏃‍♀️")
            elif 1 < current_hour <= 5:
                message_parts.append("\n😴 夜深了～您是不是正在等第一班車呢？我來幫您看看！☀️")
            else:
                message_parts.append("\n😊 這是您要查詢的固定班次資訊喔！")


            # 重新組織時刻表訊息，使其更清晰、更可愛
            for entry in timetable_data:
                destination = entry.get('destination_station', '未知終點站')
                first_train = entry.get('first_train_time', 'N/A')
                last_train = entry.get('last_train_time', 'N/A')
                service_days = entry.get('service_days', '每日行駛') # 加入 service_days 顯示

                # 簡化 service_days 顯示
                # 請注意：此處假定 service_days 的格式為 '{,1,1,1,1,1,1,1,1}' 代表每日
                # 如果您的實際數據有其他複雜的格式，可能需要更詳細的解析邏輯
                if service_days == "'{,1,1,1,1,1,1,1,1}'" or "1,1,1,1,1,1,1" in service_days: # 增加更寬鬆的判斷
                    service_days_display = "每日行駛"
                else:
                    service_days_display = "特定日行駛" # 如果有更複雜的服務日期，可能需要更詳細的解析

                line_info = (
                    f"\n➡️ 往 **{destination}** 方向：\n"
                    f"   ⏰ 首班車： **{first_train}**\n"
                    f"   ⏰ 末班車： **{last_train}**\n"
                    f"   🗓️ 營運日： {service_days_display}"
                )
                message_parts.append(line_info)

            # 隨機選擇結尾語
            closings = [
                "\n\n希望這個資訊對您有幫助，祝您旅途順利喔！🌈",
                "\n\n出門在外要注意安全，希望您能順利搭上車！💖",
                "\n\n如果時間有點趕，別忘了注意安全喔！有我在，您就安心搭車吧！�",
                "\n\n請您再確認一下時間，快樂出門，平安回家喔！😊"
            ]
            message_parts.append(random.choice(closings))

            # 保留官方的免責聲明，但用比較輕鬆的口吻
            message_parts.append("\n\n(✨ 貼心提醒：首末班車時間可能因維修、國定假日或特殊情況而變動，建議您提早一點到車站，並以車站現場公告為準最保險喔！)")

            # 使用兩個換行符號，讓最終呈現的訊息段落分明
            return json.dumps({
                "station": station_name, 
                "timetable": timetable_data, 
                "message": "\n".join(message_parts)
            }, ensure_ascii=False)
        
        # 查無資料的可愛回覆
        return json.dumps({"error": f"🧐 哎呀，好像沒有找到「{station_name}」站的首末班車資訊耶... \n這可能是因為該站目前沒有提供相關資料，或是資料正在更新中。\n您可以試著查詢其他車站，或是再確認一下站名是否有打錯喔！💡"}, ensure_ascii=False)
    
    except StationNotFoundError as e:
        logger.warning(f"--- [工具(首末班車)] 查詢時發生錯誤: {e} ---")
        # 找不到車站的可愛回覆
        return json.dumps({"error": f"😕 抱歉，我目前找不到「{station_name}」這個車站的資料耶。\n請確認您輸入的站名是不是正確的，或試試看其他相近的名稱喔！🗺️"}, ensure_ascii=False)
    except DataLoadError as e:
        logger.error(f"--- [工具(首末班車)] 數據載入錯誤: {e} ---", exc_info=True)
        # 資料載入失敗的可愛回覆
        return json.dumps({"error": "😴 抱歉，時刻表資料庫好像正在午休，現在無法查詢！請您稍後再試一次喔！⏰"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"--- [工具(首末班車)] 查詢時發生未知錯誤: {e} ---", exc_info=True)
        # 未知錯誤的可愛回覆
        return json.dumps({"error": f"🤖 糟糕，查詢「{station_name}」站的時候，發生了一點點小問題，技術人員正在努力搶修中！請您稍後再試試看喔！🛠️"}, ensure_ascii=False)


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
@tool
def get_realtime_mrt_info(station_name: str, destination: str) -> str:
    """
    【即時捷運到站專家】當使用者詢問「現在XX站往YY方向的車還有多久來」、「下一班車在哪裡」等關於
    特定車站和方向的即時列車資訊時，請使用此工具。這個工具會提供最即時的列車位置和到站倒數。

    Args:
        station_name (str): 使用者詢問的**目前**所在車站名稱。
        destination (str): 列車的行駛方向或終點站名稱。
    """
    logger.info(f"--- [工具(即時到站)] 查詢: {station_name} 往 {destination} 方向 ---")

    tool_output = {} # 初始化工具回傳的結構化數據

    try:
        current_query_time = datetime.now()

        realtime_mrt_service = service_registry.realtime_mrt_service
        station_manager = service_registry.station_manager # 確保取得 station_manager

        if not station_name or not destination:
            raise ValueError("請提供您所在的車站和列車的目的地。")

        # 解析並標準化使用者輸入的站名
        resolved_station_name = realtime_mrt_service.search_station(station_name)
        resolved_destination_name = realtime_mrt_service.search_station(destination)

        if not resolved_station_name:
            raise StationNotFoundError(f"我無法識別車站「{station_name}」。")
        if not resolved_destination_name:
            raise StationNotFoundError(f"我無法識別目的地「{destination}」。")

        # 獲取用於顯示給使用者的官方完整名稱
        official_station_display_name = station_manager.get_official_unnormalized_name(resolved_station_name)
        official_destination_display_name = station_manager.get_official_unnormalized_name(resolved_destination_name)

        # 推導出真正的列車終點站 (可能有多個，取第一個作為主要方向顯示)
        target_terminus_list = realtime_mrt_service.resolve_train_terminus(
            resolved_station_name, resolved_destination_name
        )

        if not target_terminus_list:
            tool_output = {
                "status": "No train found",
                "reason": "invalid_direction",
                "query_station": official_station_display_name,
                "query_destination": official_destination_display_name,
                "message_hint": f"從「{official_station_display_name}」站沒有往「{official_destination_display_name}」方向的直達列車。",
                "possible_directions": [station_manager.get_official_unnormalized_name(key) for key in station_manager.get_terminal_stations_for(resolved_station_name)]
            }
            return json.dumps(tool_output, ensure_ascii=False)


        candidate_trains = realtime_mrt_service.get_next_train_info(
            target_station_official_name=resolved_station_name,
            target_direction_normalized_list=target_terminus_list
        )

        if not candidate_trains:
            tool_output = {
                "status": "No train found",
                "reason": "no_realtime_data",
                "query_station": official_station_display_name,
                "query_destination": official_destination_display_name,
                "message_hint": f"目前沒有找到往「{official_destination_display_name}」方向的列車資訊。"
            }
        else:
            next_train_info = []
            for train in candidate_trains[:3]: # 只取最近的3班車
                countdown_str = train.get('CountDown', 'N/A')
                current_train_station = train.get('StationName', '未知車站')

                eta_seconds = None
                arrival_time_str = None
                
                if countdown_str == '列車進站':
                    eta_seconds = 0
                    arrival_time_str = (current_query_time).strftime('%H:%M') # 列車進站，視為立即到達
                else:
                    total_minutes = 0
                    # 嘗試解析 "X分鐘Y秒"
                    match_seconds = re.search(r'(\d+)\s*分鐘\s*(\d+)\s*秒', countdown_str)
                    # 嘗試解析 "X分鐘"
                    match_minutes = re.search(r'(\d+)\s*分鐘', countdown_str)
                    # 嘗試解析純數字 (例如： "5")
                    match_single_number = re.search(r'^(\d+)$', countdown_str.strip())

                    if match_seconds:
                        minutes = int(match_seconds.group(1))
                        seconds = int(match_seconds.group(2))
                        eta_seconds = minutes * 60 + seconds
                    elif match_minutes:
                        minutes = int(match_minutes.group(1))
                        eta_seconds = minutes * 60
                    elif match_single_number:
                        minutes = int(match_single_number.group(1))
                        eta_seconds = minutes * 60
                    
                    if eta_seconds is not None:
                        estimated_arrival_datetime = current_query_time + timedelta(seconds=eta_seconds)
                        arrival_time_str = estimated_arrival_datetime.strftime('%H:%M')
                    else:
                        # 如果無法解析，則使用原始倒數字串
                        countdown_str = countdown_str # 保持原始字串

                next_train_info.append({
                    "current_location": current_train_station,
                    "countdown_raw": countdown_str, # 原始倒數字串
                    "eta_seconds": eta_seconds, # 精確到秒的倒數
                    "arrival_time": arrival_time_str # 預計抵達的實際時間點 (HH:MM)
                })

            tool_output = {
                "status": "Success",
                "query_time": current_query_time.strftime('%H點%M分'),
                "query_station": official_station_display_name,
                "query_destination": official_destination_display_name,
                "train_terminus": station_manager.get_official_unnormalized_name(target_terminus_list[0]), # 確保是顯示名稱
                "next_trains": next_train_info,
                "suggestion": {
                    "text": "想知道這班車會不會很擠嗎？您可以問我「[車站名稱] 往 [目的地] 擠不擠」",
                    "example_query": f"{official_station_display_name} 往 {official_destination_display_name} 擠不擠"
                }
            }

        return json.dumps(tool_output, ensure_ascii=False)

    except StationNotFoundError as e:
        tool_output = {
            "status": "Error",
            "error_type": "Station Not Found",
            "message": f"😕 抱歉，我好像找不到您說的車站或目的地耶。錯誤訊息：{e}"
        }
        logger.warning(f"--- [工具(即時到站)] 查無車站或目的地: {e} ---")
        return json.dumps(tool_output, ensure_ascii=False)
    except ValueError as e:
        tool_output = {
            "status": "Error",
            "error_type": "Invalid Parameter/Direction",
            "message": f"🤔 哎呀，您提供的資訊好像有點問題，或是該方向沒有直達列車。錯誤訊息：{e}"
        }
        logger.warning(f"--- [工具(即時到站)] 參數錯誤或方向無效: {e} ---")
        return json.dumps(tool_output, ensure_ascii=False)
    except Exception as e:
        tool_output = {
            "status": "Error",
            "error_type": "Unknown Error",
            "message": "🤖 糟糕，我的捷運查詢系統好像出了一點小狀況，請稍後再試一次喔！"
        }
        logger.error(f"--- [工具(即時到站)] 發生未知錯誤: {e} ---", exc_info=True)
        return json.dumps(tool_output, ensure_ascii=False)

# --- 【 ✨✨✨ 修正並強化這個工具 ✨✨✨ 】 ---
# 假設這是您之前加入的 Emoji 對應
CONGESTION_EMOJI_MAP = {
    1: "😊 舒適",
    2: "🤔 正常",
    3: "😥 略多",
    4: "😡 擁擠"
}

@tool
def predict_train_congestion(station_name: str, direction: str, datetime_str: Optional[str] = None) -> str:
    """
    【捷運擁擠度預測專家】當使用者詢問「XX站擠不擠」、「YY站往ZZ方向人多嗎」這類關於車廂擁擠度的問題時，請使用此工具。
    它可以預測當前或未來特定時間的車廂擁擠程度。此工具常與 get_realtime_mrt_info 工具一起使用，來回答關於「車上人多不多」這類複合問題。

    Args:
        station_name (str): 預測的車站名稱。
        direction (str): 預測的行駛方向或終點站名稱。
        datetime_str (str, optional): 預測的日期和時間，可以是標準格式 `YYYY-MM-DD HH:MM`，
        也可以是自然語言表達，例如「明天早上八點」或「下一班車」。若未提供此參數，
        工具將自動使用當前時間進行預測。
    """
    logger.info(f"--- [工具(預測)] 原始查詢: {station_name} 往 {direction} 方向, 時間: {datetime_str} ---")

    if not station_name or not direction:
        return json.dumps({
            "error": "Missing parameters",
            "message": "🤔 哎呀，我需要知道您想查詢的「車站」和「方向」才能為您預測喔！" # 人性化錯誤訊息
        }, ensure_ascii=False)

    target_datetime = None
    if datetime_str:
        # 增加對口語化時間的處理
        if datetime_str.lower() in ["現在", "即將", "馬上", "下一班車"]:
            target_datetime = datetime.now()
        else:
            # 使用 dateparser 來解析自然語言時間字串
            target_datetime = dateparser.parse(
                datetime_str,
                settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': 'Asia/Taipei'}
            )
    
    if not target_datetime:
        # 如果使用者沒有提供時間，或 dateparser 無法解析，則使用當前時間
        target_datetime = datetime.now()
        logger.info("--- 未提供時間或無法解析，自動設定為當前時間 ---")

    # --- 關鍵防禦：檢查解析出來的日期是否過於久遠，這通常代表 LLM 的幻覺或解析錯誤 ---
    now = datetime.now()
    if target_datetime > now + timedelta(days=365) or target_datetime < now - timedelta(days=1):
        logger.warning(f"--- ⚠️ 檢測到不合理的日期: {target_datetime.isoformat()}，可能為 LLM 幻覺。---")
        return json.dumps({
            "error": "Invalid time period",
            "message": f"📅 抱歉，您提供的日期 `{datetime_str}` 看起來有點太遙遠了。我只能預測一年內的擁擠度喔！今天的日期是 `{now.strftime('%Y-%m-%d')}`。" # 人性化錯誤訊息
        }, ensure_ascii=False)
        
    # --- 別名解析 ---
    # 確保 station_manager 已透過 service_registry 取得
    station_manager = service_registry.station_manager 
    congestion_predictor = service_registry.congestion_predictor

    # 1. 解析並標準化使用者輸入的車站和方向名稱
    resolved_station_name_key = station_manager.resolve_station_alias(station_name)
    resolved_direction_key = station_manager.resolve_station_alias(direction)

    # 取得用於顯示給使用者的官方完整名稱
    official_station_display_name = station_manager.get_official_unnormalized_name(resolved_station_name_key)
    official_direction_display_name = station_manager.get_official_unnormalized_name(resolved_direction_key)

    # 2. 獲取該出發站所有可能的終點站 (已標準化為內部鍵)
    possible_terminals_keys = station_manager.get_terminal_stations_for(resolved_station_name_key)
    
    # 檢查出發站是否存在或有路線
    if not possible_terminals_keys:
        return json.dumps({
            "error": "Station not found or no routes",
            "message": f"😕 抱歉，我好像找不到「{station_name}」這個車站的資料，或是它沒有可查詢的路線耶。請問您有輸入正確的車站名稱嗎？" # 人性化錯誤訊息
        }, ensure_ascii=False)

    # 3. 驗證使用者查詢的方向是否為合法終點站
    if resolved_direction_key not in possible_terminals_keys:
        # 將可能的終點站內部鍵轉換為顯示名稱，以便提供友善提示
        display_terminals = [station_manager.get_official_unnormalized_name(key) for key in possible_terminals_keys]
        
        # 判斷是否因為方向名稱本身有問題，還是該站點根本沒有此方向
        error_message = f"🧭 哎呀！從「{official_station_display_name}」站，好像沒有直接開往「{direction}」的車耶。" # 人性化錯誤訊息
        if display_terminals:
            error_message += f"\n\n您可以試試看往以下幾個方向查詢：\n✨ **{'、'.join(display_terminals)}**"
        else:
            error_message += f"\n\n這個車站似乎沒有明確的行駛方向資訊。"

        return json.dumps({
            "error": "Invalid direction",
            "message": error_message
        }, ensure_ascii=False)

    # 執行擁擠度預測
    prediction_result = congestion_predictor.predict_for_station(
        station_name=official_station_display_name, # 使用官方顯示名稱進行預測
        direction=official_direction_display_name,   # 使用官方顯示名稱進行預測
        target_datetime=target_datetime
    )

    if "error" in prediction_result:
        return json.dumps({"message": f"😥 抱歉，預測時發生了一點小問題：{prediction_result['error']}"}, ensure_ascii=False) # 人性化錯誤訊息

    congestion_data = prediction_result.get("congestion_by_car", [])
    
    if congestion_data:
        time_display = target_datetime.strftime('%Y年%m月%d日 %H點%M分')
        if datetime_str and datetime_str.lower() in ["現在", "即將", "馬上", "下一班車"]:
            time_display = "現在"
                
        # 保持原本的輸出格式：開場白 + 列車擁擠度列表
        message_parts = [
            f"根據預測，在 {time_display} 往「{official_direction_display_name}」方向的列車擁擠度如下：",
            "---"
        ]
        
        for car in congestion_data:
            car_number = car['car_number']
            congestion_level = car['congestion_level']
            emoji_text = CONGESTION_EMOJI_MAP.get(congestion_level, "❔")
            message_parts.append(f"第 {car_number} 節車廂：{emoji_text}")
        
        # 從這裡開始加入人性化的總結語句
        max_congestion = max(c['congestion_level'] for c in congestion_data) if congestion_data else 0
        if max_congestion >= 3: # 假設 3 代表中等擁擠，4 代表非常擁擠
            message_parts.append("\n💡 **貼心提醒**：部分車廂可能人潮較多，建議您往較空曠的車廂移動喔！")
        elif max_congestion == 2: # 假設 2 代表普通
            message_parts.append("\n😊 車廂狀況還不錯，人潮普通，可以輕鬆搭乘！")
        else: # 假設 0, 1 代表空曠
            message_parts.append("\n🎉 太棒了！看起來車廂非常空曠，祝您有趟愉快的旅程！")
            
        final_message = "\n".join(message_parts)
    else:
        final_message = f"😥 抱歉，目前暫時無法取得「{official_station_display_name}」往「{official_direction_display_name}」方向在此時段的擁擠度預測資料。您可以試試看其他時間或目的地喔！" # 人性化無資料訊息

    response = {"message": final_message}
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
    get_realtime_mrt_info,
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