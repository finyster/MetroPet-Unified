"""
agent/function_tools.py
~~~~~~~~~~~~~~~~~~~~~~~
所有可被 LLM Agent 呼叫的工具函式。
"""

from pathlib import Path
import json
import logging
from dotenv import load_dotenv
from langchain_core.tools import tool
from services import service_registry
from utils.exceptions import StationNotFoundError, RouteNotFoundError

# ---------------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------------
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")  # 若入口檔已載入 .env，可拿掉

# ---------------------------------------------------------------------
# 常用單例服務
# ---------------------------------------------------------------------

metro_soap_api     = service_registry.get_soap_api()
routing_manager    = service_registry.get_routing_manager()
fare_service       = service_registry.get_fare_service()
station_manager    = service_registry.get_station_manager()
local_data_manager = service_registry.get_local_data_manager()
tdx_api            = service_registry.get_tdx_api()
# 新增：ID 轉換服務
id_converter       = service_registry.id_converter_service

# ---------------------------------------------------------------------
# 1. 路徑規劃
# ---------------------------------------------------------------------


@tool
def plan_route(start_station_name: str, end_station_name: str) -> str:
    """
    【路徑規劃專家】
    接收站名，如果站名模糊，會返回一個請求確認的錯誤。
    """
    logger.info(f"🚀 [路徑規劃] 開始規劃路徑：從「{start_station_name}」到「{end_station_name}」。")

    start_result = station_manager.get_station_ids(start_station_name)
    end_result = station_manager.get_station_ids(end_station_name)

    # 檢查起點
    if isinstance(start_result, dict) and 'suggestion' in start_result:
        return json.dumps({"error": "need_confirmation", **start_result}, ensure_ascii=False)
    if not start_result:
        return json.dumps({"error": f"抱歉，我找不到名為「{start_station_name}」的捷運站。"}, ensure_ascii=False)

    # 檢查終點
    if isinstance(end_result, dict) and 'suggestion' in end_result:
        return json.dumps({"error": "need_confirmation", **end_result}, ensure_ascii=False)
    if not end_result:
        return json.dumps({"error": f"抱歉，我找不到名為「{end_station_name}」的捷運站。"}, ensure_ascii=False)

    # --- 如果一切正常，繼續原有的ID轉換和API呼叫流程 ---
    start_tdx_id = start_result[0]
    end_tdx_id = end_result[0]
    logger.info(f"TDX ID 解析成功: start='{start_tdx_id}', end='{end_tdx_id}'")

    start_sid = id_converter.tdx_to_sid(start_tdx_id)
    end_sid = id_converter.tdx_to_sid(end_tdx_id)
    logger.info(f"純數字 SID 轉換成功: start='{start_sid}', end='{end_sid}'")

    # ... (後續的 try/except API 呼叫和 fallback 邏輯完全不變) ...
    if start_sid and end_sid:
        logger.info("📞 嘗試呼叫北捷官方 SOAP API...")
        try:
            api_raw = metro_soap_api.get_recommended_route(start_sid, end_sid)
            if api_raw and api_raw.get("path"):
                logger.info(f"✅ 成功從官方 API 獲取建議路線，耗時 {api_raw.get('time_min', 'N/A')} 分鐘。")
                msg = (
                    f"官方建議路線：{start_station_name} → {end_station_name}，"
                    f"約 {api_raw['time_min']} 分鐘。\n"
                    f"路徑：{' → '.join(api_raw['path'])}"
                )
                if api_raw.get("transfers"):
                    msg += f"\n轉乘站：{'、'.join(api_raw['transfers'])}"
                return json.dumps({
                    "source":   "official_api",
                    "route":    api_raw["path"],
                    "time_min": api_raw["time_min"],
                    "transfer": api_raw.get("transfers", []),
                    "message":  msg
                }, ensure_ascii=False)
        except Exception as e:
            logger.error(f"調用官方 SOAP API 時發生錯誤: {e}", exc_info=True)

    logger.warning("SOAP API 無法使用或呼叫失敗，啟動備用方案：本地路網圖演算法。")
    try:
        fallback = routing_manager.find_shortest_path(start_station_name, end_station_name)
        if "path_details" in fallback:
            logger.info("✅ 成功透過本地演算法找到備用路徑。")
            fallback["message"] = "（備用方案）" + fallback["message"]
            return json.dumps({"source": "local_fallback", **fallback}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"本地路網規劃時發生未知錯誤: {e}", exc_info=True)

    logger.error(f"❌ 無法規劃路徑：從「{start_station_name}」到「{end_station_name}」，所有方法均失敗。")
    return json.dumps({"error": f"非常抱歉，我無法規劃從「{start_station_name}」到「{end_station_name}」的路線，請稍後再試。"}, ensure_ascii=False)

# ---------------------------------------------------------------------
# 2. 票價查詢
# ---------------------------------------------------------------------
@tool
def get_mrt_fare(start_station_name: str, end_station_name: str) -> str:
    """【票價查詢專家】回傳全票與兒童票價格，不含路徑規劃。"""
    logger.info(f"[票價] {start_station_name} → {end_station_name}")
    try:
        fare = fare_service.get_fare(start_station_name, end_station_name)
        return json.dumps({
            "start_station": start_station_name,
            "end_station":   end_station_name,
            "full_fare":     fare.get("full_fare", "未知"),
            "child_fare":    fare.get("child_fare", "未知"),
            "message": (
                f"從「{start_station_name}」到「{end_station_name}」的"
                f"全票 NT${fare.get('full_fare', '未知')}，"
                f"兒童票 NT${fare.get('child_fare', '未知')}。"
            )
        }, ensure_ascii=False)
    except StationNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        logger.exception("票價查詢失敗")
        return json.dumps({"error": f"查詢票價時發生錯誤：{e}"}, ensure_ascii=False)

# ---------------------------------------------------------------------
# 3. 首末班車
# ---------------------------------------------------------------------
@tool
def get_first_last_train_time(station_name: str) -> str:
    """【首末班車專家】查詢指定站點各方向首/末班時間。"""
    logger.info(f"[首末班車] {station_name}")
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)

    timetable = tdx_api.get_first_last_timetable(station_ids[0])
    if not timetable:
        return json.dumps({"error": f"查無「{station_name}」首末班車資訊"}, ensure_ascii=False)

    rows = [
        {"direction": t.get("TripHeadSign", "未知方向"),
         "first":     t.get("FirstTrainTime", "N/A"),
         "last":      t.get("LastTrainTime", "N/A")}
        for t in timetable
    ]
    msg_lines = [f"「{station_name}」首末班車："]
    for r in rows:
        msg_lines.append(f"往 {r['direction']} → 首班 {r['first']}，末班 {r['last']}")

    return json.dumps({"station": station_name, "timetable": rows,
                       "message": "\n".join(msg_lines)}, ensure_ascii=False)

# ---------------------------------------------------------------------
# 4. 出口資訊
# ---------------------------------------------------------------------
@tool
def get_station_exit_info(station_name: str) -> str:
    """【車站出口專家】列出所有出口編號與描述。"""
    logger.info(f"[出口] {station_name}")
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)

    exit_map = local_data_manager.exits
    exits: list[str] = []
    for sid in station_ids:
        exits.extend(
            f"出口 {e.get('ExitNo', 'N/A')}: {e.get('Description', '無描述')}"
            for e in exit_map.get(sid, [])
        )

    if not exits:
        return json.dumps({"error": f"查無「{station_name}」出口資訊"}, ensure_ascii=False)

    if all(x.endswith(": 無描述") for x in exits):
        msg = (f"「{station_name}」共有 {len(exits)} 個出入口，"
               "但暫無詳細描述。")
    else:
        msg = f"「{station_name}」出口資訊：\n" + "\n".join(exits)

    return json.dumps({"station": station_name, "exits": exits,
                       "message": msg}, ensure_ascii=False)

# ---------------------------------------------------------------------
# 5. 車站設施
# ---------------------------------------------------------------------
@tool
def get_station_facilities(station_name: str) -> str:
    """【車站設施專家】列出站內設施與描述。"""
    logger.info(f"[設施] {station_name}")
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)

    facilities = [
        local_data_manager.facilities.get(sid)
        for sid in station_ids
        if sid in local_data_manager.facilities
    ]
    facilities = [f for f in facilities if f]

    if not facilities:
        return json.dumps({"error": f"查無「{station_name}」設施資訊"}, ensure_ascii=False)

    desc = "\n".join(facilities)
    msg = (f"「{station_name}」設施資訊：\n{desc}"
           if desc.strip() != "無詳細資訊"
           else f"「{station_name}」目前無詳細設施描述資訊。")
    return json.dumps({"station": station_name, "facilities_info": desc,
                       "message": msg}, ensure_ascii=False)

# ---------------------------------------------------------------------
# 6. 遺失物
# ---------------------------------------------------------------------
@tool
def get_lost_and_found_info() -> str:
    """【遺失物專家】提供遺失物查詢流程與官方連結。"""
    logger.info("[遺失物] 提供遺失物查詢資訊")
    return json.dumps({
        "message": "遺失物請至捷運公司官網查詢。",
        "official_link": "https://web.metro.taipei/pages/tw/lostandfound/search",
        "instruction": "輸入遺失物時間、地點或物品名稱即可查詢，逾期則需親至遺失物中心。"
    }, ensure_ascii=False)

# ---------------------------------------------------------------------
# 匯出工具清單
# ---------------------------------------------------------------------
all_tools = [
    plan_route,
    get_mrt_fare,
    get_first_last_train_time,
    get_station_exit_info,
    get_station_facilities,
    get_lost_and_found_info,
]
