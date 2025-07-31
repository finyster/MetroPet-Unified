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
sid_resolver       = service_registry.get_sid_resolver()
metro_soap_api     = service_registry.get_soap_api()
routing_manager    = service_registry.get_routing_manager()
fare_service       = service_registry.get_fare_service()
station_manager    = service_registry.get_station_manager()
local_data_manager = service_registry.get_local_data_manager()
tdx_api            = service_registry.get_tdx_api()

# ---------------------------------------------------------------------
# 1. 路徑規劃
# ---------------------------------------------------------------------
@tool
def plan_route(start_station_name: str, end_station_name: str) -> str:
    """
    【路徑規劃專家】

    1. 站名 ➜ SID（支援中/英文、常見別名）
    2. 呼叫台北捷運官方 GetRecommandRoute SOAP API
    3. 官方 API 失敗時，自動降級本地最短路徑
    4. 於終端輸出 start_sid / end_sid 供開發者確認
    """
    # 站名 → SID
    start_sid = sid_resolver.get_sid(start_station_name)
    end_sid   = sid_resolver.get_sid(end_station_name)

    print(f"[DEBUG] start_sid={start_sid}, end_sid={end_sid}")  # 供終端確認

    if not start_sid:
        return json.dumps({"error": f"找不到起點「{start_station_name}」對應的 SID"}, ensure_ascii=False)
    if not end_sid:
        return json.dumps({"error": f"找不到終點「{end_station_name}」對應的 SID"}, ensure_ascii=False)

    # 呼叫官方 API
    api_raw = metro_soap_api.get_recommended_route(start_sid, end_sid)
    if api_raw and api_raw.get("path"):
        msg = (
            f"官方建議路線：{start_station_name} → {end_station_name}，"
            f"約 {api_raw['time_min']} 分鐘。\n"
            f"路徑：{' → '.join(api_raw['path'])}"
        )
        if api_raw["transfers"]:
            msg += f"\n轉乘站：{'、'.join(api_raw['transfers'])}"

        return json.dumps({
            "source":   "official_api",
            "route":    api_raw["path"],
            "time_min": api_raw["time_min"],
            "transfer": api_raw["transfers"],
            "message":  msg
        }, ensure_ascii=False)

    # 官方 API 失敗 → fallback
    logger.warning("官方 API 失敗，改用本地最短路徑演算法")
    fallback = routing_manager.find_shortest_path(start_station_name, end_station_name)
    if "route" in fallback:
        return json.dumps({"source": "local_fallback", **fallback}, ensure_ascii=False)

    return json.dumps({"error": "無法規劃可行路線，請稍後再試"}, ensure_ascii=False)

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
