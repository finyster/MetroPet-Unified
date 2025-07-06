from langchain_core.tools import tool
import data_manager # 導入我們的資料管理器

@tool
def get_mrt_fare(start_station_name: str, end_station_name: str) -> str:
    """
    查詢台北捷運從起點站到終點站的票價。
    你需要提供中文的起點站名和終點站名。
    """
    # TODO: 實作站名到站點 ID 的轉換
    # 這一步需要一個站名與 ID 的對照表，這個表可以從 get_mrt_network() API 獲得
    start_station_id = "BL12" # 範例: 市政府
    end_station_id = "R03"   # 範例: 台北101/世貿

    print(f"正在查詢從 {start_station_name} ({start_station_id}) 到 {end_station_name} ({end_station_id}) 的票價...")
    
    fare_data = data_manager.tdx_manager.get_mrt_fare(start_station_id, end_station_id)

    if fare_data and len(fare_data) > 0:
        # 解析回傳的資料，這部分的結構需要參考 TDX 的實際回傳格式
        fare_info = fare_data[0]
        price = fare_info.get("Fares", [{}])[0].get("Price")
        return f"從 {start_station_name} 到 {end_station_name} 的單程票價是 {price} 元。"
    else:
        return f"抱歉，無法查詢到從 {start_station_name} 到 {end_station_name} 的票價資訊。"

@tool
def get_station_arrival_time(station_name: str) -> str:
    """
    查詢特定台北捷運站點目前月台的列車即將到站資訊。
    你需要提供中文的站名。
    """
    # TODO: 同上，需要站名到 ID 的轉換
    station_id = "BL12" # 範例: 市政府

    print(f"正在查詢 {station_name} ({station_id}) 的即時到站資訊...")
    arrival_data = data_manager.tdx_manager.get_realtime_arrivals(station_id)

    if arrival_data:
        response_text = f"{station_name} 的即時到站資訊如下：\n"
        for train in arrival_data:
            line = train.get("LineName", "未知路線")
            destination = train.get("DestinationStationName", {}).get("Zh_tw", "未知終點站")
            arrival_time = train.get("EstimateTime")
            if arrival_time is not None:
                response_text += f"- 往 {destination} ({line}) 的列車：約 {arrival_time} 分鐘後到站。\n"
            else: # 北捷的資料特性是進站時才會顯示
                arrival_time_text = train.get("TripStatus", "未知狀態")
                if arrival_time_text == 1:
                    arrival_time_text = "列車進站中"
                response_text += f"- 往 {destination} ({line}) 的列車：{arrival_time_text}。\n"
        return response_text
    else:
        return f"抱歉，目前無法取得 {station_name} 的即時到站資訊。"


@tool
def query_lost_and_found(item_description: str) -> str:
    """
    當使用者詢問遺失物相關問題時使用。
    由於沒有官方 API，此工具會提供查詢網頁的連結。
    """
    print(f"使用者正在查詢遺失物：{item_description}")
    return "關於遺失物查詢，由於沒有統一的即時 API，建議您直接上臺北捷運公司的官方遺失物查詢網站，或致電客服中心。網站連結：https://web.metro.taipei/pages/tw/lostandfound/search"

# 將所有工具放在一個 list 中，方便 Agent 使用
all_tools = [get_mrt_fare, get_station_arrival_time, query_lost_and_found]