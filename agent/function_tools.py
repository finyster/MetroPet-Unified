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
import config, re

from utils.station_name_normalizer import normalize_station_name
from services.lost_item_search_service import lost_item_search_service
from datetime import datetime, timedelta
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
# ---------------------------------------------------------------------#
@tool
def plan_route(start_station_name: str, end_station_name: str) -> str:
    """
    【路徑規劃專家】
    接收起點和終點站名，規劃路線並提供兩種資訊：
    1. 詳細、人性化的搭乘方向指引。
    2. 官方API提供的、包含所有停靠站的完整路徑列表。
    """
    logger.info(f"🚀 [路徑規劃] 開始規劃路徑：從「{start_station_name}」到「{end_station_name}」。")

    # 1. 驗證站名
    start_result = station_manager.get_station_ids(start_station_name)
    end_result = station_manager.get_station_ids(end_station_name)

    # ... (站名驗證邏輯與您提供的版本相同，此處為簡化省略，請保留您原有的驗證碼)
    if isinstance(start_result, dict) and 'suggestion' in start_result:
        return json.dumps({"error": "need_confirmation", **start_result}, ensure_ascii=False)
    if not start_result or not isinstance(start_result, list):
        return json.dumps({"error": f"抱歉，我找不到名為「{start_station_name}」的捷運站。"}, ensure_ascii=False)
    if isinstance(end_result, dict) and 'suggestion' in end_result:
        return json.dumps({"error": "need_confirmation", **end_result}, ensure_ascii=False)
    if not end_result or not isinstance(end_result, list):
        return json.dumps({"error": f"抱歉，我找不到名為「{end_station_name}」的捷運站。"}, ensure_ascii=False)

    start_sid = id_converter.tdx_to_sid(start_result[0])
    end_sid = id_converter.tdx_to_sid(end_result[0])

    # 2. 主要邏輯：優先使用官方API
    if start_sid and end_sid:
        logger.info(f"📞 嘗試呼叫北捷官方 SOAP API (SID: {start_sid} -> {end_sid})...")
        try:
            api_raw = metro_soap_api.get_recommended_route(start_sid, end_sid)
            
            if api_raw and isinstance(api_raw.get("path"), list) and len(api_raw["path"]) > 1:
                logger.info("✅ 成功從官方 API 獲取建議路線，開始進行雙重路徑處理...")
                
                # --- ✨ 核心改動 ✨ ---
                # 2.1 獲取原始的完整路徑列表
                full_path_list = api_raw["path"]
                
                # 2.2 產生人性化的搭乘指引
                detailed_directions = routing_manager.generate_directions_from_path(full_path_list)
                
                # 2.3 組合包含兩種資訊的最終訊息
                message = (
                    f"好的，從「{start_station_name}」到「{end_station_name}」的建議路線如下，預估時間約 {api_raw['time_min']} 分鐘：\n\n"
                    f"**搭乘指引：**\n" +
                    "\n".join(f"➡️ {step}" for step in detailed_directions) +
                    f"\n\n**行經車站：**\n" +
                    f"{' → '.join(full_path_list)}"
                )
                
                # 2.4 回傳包含所有資訊的 JSON
                return json.dumps({
                    "source": "official_api_enhanced",
                    "time_min": api_raw["time_min"],
                    "directions": detailed_directions, # 人性化指引
                    "full_path": full_path_list,       # 原始停靠站
                    "message": message
                }, ensure_ascii=False)

        except Exception as e:
            logger.error(f"調用官方 SOAP API 或人性化處理時發生錯誤: {e}", exc_info=True)
    
    # 3. 備用方案 (保持不變，它本身就會回傳詳細資訊)
    logger.warning("SOAP API 無法使用或呼叫失敗，啟動備用方案：本地路網圖演算法。")
    try:
        fallback = routing_manager.find_shortest_path(start_station_name, end_station_name)
        if "path_details" in fallback:
            logger.info("✅ 成功透過本地演算法找到備用路徑。")
            fallback["message"] = "（備用方案）" + fallback["message"]
            return json.dumps({"source": "local_fallback", **fallback}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"本地路網規劃時發生未知錯誤: {e}", exc_info=True)

    # 4. 最終失敗
    logger.error(f"❌ 無法規劃路徑：從「{start_station_name}」到「{end_station_name}」，所有方法均失敗。")
    return json.dumps({"error": f"非常抱歉，我無法規劃從「{start_station_name}」到「{end_station_name}」的路線。"}, ensure_ascii=False)
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
    # 1. 記錄 Log，方便我們在後台看到 AI 何時呼叫了這個工具
    logger.info(f"[設施] {station_name}")

    # 2. 呼叫 StationManager，將使用者口語化的站名（如 "北車"）
    #    轉換成標準的車站 ID 列表（如 ["BL12", "R10"]）
    #    如果找不到，就直接回傳錯誤訊息。
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)

    # 3. 讀取我們建立好的設施資料庫 (mrt_station_facilities.json)
    #    並根據上一步找到的車站 ID，把對應的詳細設施資訊撈出來。
    facilities = [
        local_data_manager.facilities.get(sid)
        for sid in station_ids
        if sid in local_data_manager.facilities
    ]
    # 移除可能的空值
    facilities = [f for f in facilities if f]

    # 4. 如果在資料庫中找不到任何資訊，回傳查無資料的錯誤。
    if not facilities:
        return json.dumps({"error": f"查無「{station_name}」設施資訊"}, ensure_ascii=False)

    # 5. 將找到的設施資訊（可能有多筆，針對轉乘站）合併成一個字串
    #    並建立一個友善的回覆訊息。
    desc = "\n".join(list(set(facilities))) # 使用 set 避免轉乘站資訊重複
    msg = f"「{station_name}」站的設施資訊如下：\n{desc}"

    # 6. 將最終結果包裝成 JSON 格式回傳給 AI Agent
    return json.dumps({
        "station": station_name, 
        "facilities_info": desc,
        "message": msg
    }, ensure_ascii=False)

# ---------------------------------------------------------------------
# 6. 遺失物智慧搜尋 (最終版)
# ---------------------------------------------------------------------
@tool
def search_lost_and_found(
    item_description: str | None = None, 
    station_name: str | None = None,
    date_str: str | None = None
) -> str:
    """
    【遺失物智慧搜尋專家】
    根據物品的模糊描述、可能的地點和日期（例如'昨天'或'2025/08/02'）來搜尋遺失物。
    """
    logger.info(f"[智慧遺失物搜尋] 正在搜尋: 物品='{item_description}', 車站='{station_name}', 日期='{date_str}'")
    
    if not item_description and not station_name:
        return json.dumps({"error": "缺少搜尋條件", "message": "請至少告訴我物品的描述或可能的車站喔！"}, ensure_ascii=False)

    # --- 【✨核心擴充✨】建立一個超級豐富的「物品別名地圖」 ---
    item_alias_map = {
        # ===== 電子票證類 =====
        "悠遊卡": "電子票證", "一卡通": "電子票證", "icash": "電子票證",
        "愛金卡": "電子票證", "ic卡": "電子票證", "學生卡": "電子票證",
        "敬老卡": "電子票證", "愛心卡": "電子票證",

        # ===== 3C / 電子產品類 =====
        "手機": "行動電話", "iphone": "行動電話",
        "airpods": "他類(耳機(無線)/藍牙)", "藍芽耳機": "他類(耳機(無線)/藍牙)", "無線耳機": "他類(耳機(無線)/藍牙)",
        "耳機": "他類(耳機",  # 使用不完整的詞，以匹配 "耳機)" 和 "耳機("
        "airpods": "他類(耳機(無線)/藍牙)",
        "airpods pro": "他類(耳機(無線)/藍牙)",
        "充電線": "他類(充電(傳輸)線)", "快充線": "他類(充電(傳輸)線)", "傳輸線": "他類(充電(傳輸)線)",
        "充電器": "他類(充電器)", "豆腐頭": "他類(充電器)",
        "行動電源": "他類(行動電源)", "充電寶": "他類(行動電源)",
        "電子菸": "他類(電子菸)",
        "相機": "照相機",

        # ===== 證件 / 卡片類 =====
        "身分證": "證件", "健保卡": "證件", "駕照": "證件", "學生證": "證件",
        "信用卡": "信用卡", "金融卡": "金融卡", "提款卡": "金融卡",
        "卡夾": "車票夾", "票卡夾": "車票夾",

        # ===== 雨具類 =====
        "雨傘": "傘", "陽傘": "傘",
        "折疊傘": "摺傘",
        "長柄傘": "長傘",

        # ===== 包包 / 袋子類 =====
        "錢包": "皮夾",
        "零錢袋": "零錢包",
        "提袋": "手提袋", "購物袋": "手提袋",
        "後背包": "背包", "書包": "背包",
        "塑膠袋": "塑膠袋",
        "紙袋": "紙袋",

        # ===== 衣物 / 飾品類 =====
        "衣服": "衣物", "外套": "衣物",
        "帽子": "帽子",
        "戒指": "戒指", "首飾": "首飾", "項鍊": "首飾", "手鍊": "首飾", "耳環": "耳環",
        "眼鏡": "眼鏡", "太陽眼鏡": "眼鏡",
        "手錶": "手錶",

        # ===== 其他常見「他類」物品 =====
        "筆": "他類(筆)", "原子筆": "他類(筆)",
        "手帕": "他類(手帕)",
        "束口袋": "他類(束口袋)",
        "吊飾": "他類(吊飾)", "鑰匙圈": "他類(吊飾)",

        # ===== 其他常見物品 =====
        "鑰匙": "鑰匙",
        "水壺": "水壺", "保溫瓶": "保溫瓶",
        "娃娃": "玩偶", "公仔": "玩偶",
    }
    # ----------------------------------------------------

    # --- 步驟 1: 處理日期 ---
    search_date = None
    if date_str:
        try:
            if "昨天" in date_str:
                search_date = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
            elif "今天" in date_str:
                search_date = datetime.now().strftime('%Y/%m/%d')
            else:
                search_date = datetime.strptime(date_str, '%Y/%m/%d').strftime('%Y/%m/%d')
            logger.info(f"日期條件解析成功: {search_date}")
        except ValueError:
            logger.warning(f"無法解析日期字串: '{date_str}'，將忽略日期條件。")
            pass

    # --- 步驟 2: 處理地點 (站名 -> 站名 + 路線名) ---
    search_locations = set()
    if station_name:
        norm_station_name = station_name.replace("站", "").replace("駅", "")
        search_locations.add(norm_station_name)
        
        station_ids = station_manager.get_station_ids(station_name)
        if isinstance(station_ids, list) and station_ids:
            line_prefix_match = re.match(r"([A-Z]+)", station_ids[0])
            if line_prefix_match:
                line_prefix = line_prefix_match.group(1)
                line_map = {'BL': '板南線', 'BR': '文湖線', 'R': '淡水信義線', 'G': '松山新店線', 'O': '中和新蘆線', 'Y': '環狀線'}
                line_name = line_map.get(line_prefix)
                if line_name:
                    search_locations.add(line_name)
        logger.info(f"地點條件擴展為: {search_locations}")

    # --- 步驟 3: 處理物品 (精準別名 -> 語意搜尋) ---
    search_item_terms = set()
    if item_description:
        # 1. 優先使用「精準別名」進行轉換
        norm_item_desc = item_description.lower()
        if norm_item_desc in item_alias_map:
            official_item_name = item_alias_map[norm_item_desc]
            search_item_terms.add(official_item_name.lower())
            logger.info(f"物品 '{norm_item_desc}' 透過別名精準匹配到 '{official_item_name}'")
        
        # 2. 接著，使用「向量搜尋」來尋找其他語意相似的詞
        found_names = lost_item_search_service.find_similar_items(item_description, top_k=3, threshold=0.6)
        if found_names:
            search_item_terms.update(name.lower() for name in found_names)
            
        # 3. 無論如何，都將使用者原始的描述也加入搜尋目標
        search_item_terms.add(norm_item_desc)
        logger.info(f"物品條件擴展為: {search_item_terms}")

    # --- 步驟 4: 載入資料並執行最終篩選 ---
    try:
        with open(config.LOST_AND_FOUND_DATA_PATH, 'r', encoding='utf-8') as f:
            all_items = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error(f"遺失物資料庫檔案遺失或損毀: {config.LOST_AND_FOUND_DATA_PATH}")
        return json.dumps({"error": "資料庫錯誤", "message": "抱歉，遺失物資料庫好像不見了。"}, ensure_ascii=False)

    filtered_items = all_items
    if search_date:
        filtered_items = [item for item in filtered_items if item.get('col_Date') == search_date]
    if search_locations:
        filtered_items = [item for item in filtered_items if any(loc.lower() in item.get('col_TRTCStation', '').lower() for loc in search_locations)]
    if search_item_terms:
        filtered_items = [item for item in filtered_items if any(term in item.get('col_LoseName', '').lower() for term in search_item_terms)]

    # --- 步驟 5: 格式化並回傳結果 ---
    top_results = filtered_items[:10]
    
    if not top_results:
        return json.dumps({"count": 0, "message": "很抱歉，在資料庫中找不到符合條件的遺失物。"}, ensure_ascii=False)

    formatted_results = [
        {"拾獲日期": item.get("col_Date"), "物品名稱": item.get("col_LoseName"), "拾獲車站": item.get("col_TRTCStation"), "保管單位": item.get("col_NowPlace")}
        for item in top_results
    ]
    
    return json.dumps({
        "count": len(top_results),
        "message": f"好的，幫您在資料庫中找到了 {len(top_results)} 筆最相關的遺失物資訊：",
        "results": formatted_results
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------
# 7. 捷運美食搜尋 (新功能)
# ---------------------------------------------------------------------
@tool
def search_mrt_food(station_name: str, source_keyword: str | None = None) -> str:
    """
    【捷運美食家】
    根據使用者提供的捷運站名，查詢該站附近推薦的美食。
    可選擇性地根據來源關鍵字(例如 '米其林', '黃仁勳', '500碗')進行篩選。
    """
    # ✨ 新增：讓日誌也記錄下來源關鍵字，方便除錯
    logger.info(f"[美食搜尋] 正在搜尋「{station_name}」，來源關鍵字: '{source_keyword}'")

    # 1. 驗證並取得標準化的站名 (邏輯不變)
    station_ids = station_manager.get_station_ids(station_name)
    if not station_ids:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)

    # 2. 載入美食地圖資料 (邏輯不變)
    food_map = local_data_manager.food_map
    if not food_map:
        return json.dumps({"error": "美食地圖資料尚未載入。"}, ensure_ascii=False)
        
    # 3. 先找出該站點的「所有」餐廳 (邏輯不變)
    norm_station_name = normalize_station_name(station_name)
    all_restaurants_at_station = []
    for entry in food_map:
        if normalize_station_name(entry.get("station")) == norm_station_name:
            all_restaurants_at_station = entry.get("restaurants", [])
            break
    
    # ✨✨✨【核心修改】將篩選邏輯放在這裡 ✨✨✨
    # 檢查使用者是否提供了 `source_keyword`，並且我們確實找到了餐廳列表
    if source_keyword and all_restaurants_at_station:
        logger.info(f"--- 偵測到關鍵字 '{source_keyword}'，開始進行篩選...")
        
        filtered_restaurants = []
        # 遍歷每一家餐廳
        for restaurant in all_restaurants_at_station:
            # 取得餐廳的 source 欄位，可能是一個字串，也可能是一個列表
            source_info = restaurant.get("source", "")
            
            # 為了能統一處理，我們將 source 轉成一個 JSON 字串來進行比對
            # 這樣無論它是 "米其林" 還是 ["米其林", "500碗"]，都能被搜尋到
            source_text_for_search = json.dumps(source_info, ensure_ascii=False).lower()
            
            # 如果關鍵字存在於 source 的文字中，就將這家餐廳加入篩選結果
            if source_keyword.lower() in source_text_for_search:
                filtered_restaurants.append(restaurant)
        
        # 用篩選後的結果，覆蓋掉原本的餐廳列表
        found_restaurants = filtered_restaurants
        logger.info(f"--- 篩選完畢，找到 {len(found_restaurants)} 筆相符的結果。")
    else:
        # 如果沒有提供關鍵字，就使用全部的餐廳列表
        found_restaurants = all_restaurants_at_station

    # 4. 檢查最終是否有結果 (邏輯不變)
    if not found_restaurants:
        # 如果是篩選後沒有結果，可以給出更精確的提示
        if source_keyword:
             message = f"哎呀，在「{station_name}」附近，我找不到符合「{source_keyword}」這個來源的美食資訊耶。"
        else:
             message = f"哎呀，我目前還沒有收藏「{station_name}」附近的美食資訊耶。"
        
        return json.dumps({
            "station": station_name,
            "count": 0,
            "message": message
        }, ensure_ascii=False)

    # 5. 格式化並回傳最終結果 (邏輯不變)
    return json.dumps({
        "station": station_name,
        "count": len(found_restaurants),
        "message": f"好的，幫您找到了 {len(found_restaurants)} 家在「{station_name}」附近的美食：",
        "restaurants": found_restaurants
    }, ensure_ascii=False, indent=2)

@tool
def list_available_food_maps() -> str:
    """
    【美食地圖盤點專家】
    掃描美食資料庫，回傳所有不重複的美食地圖來源種類。
    """
    logger.info("[盤點資源] 正在掃描可用的美食地圖種類...")
    
    food_map = local_data_manager.food_map
    if not food_map:
        return json.dumps({"error": "美食地圖資料尚未載入。"}, ensure_ascii=False)

    unique_sources = set()
    for entry in food_map:
        for restaurant in entry.get("restaurants", []):
            source_info = restaurant.get("source")
            if not source_info:
                continue
            
            # 處理 source 是列表的情況 (例如: ["米其林", "500碗"])
            if isinstance(source_info, list):
                for s in source_info:
                    unique_sources.add(s)
            # 處理 source 是單一字串的情況
            elif isinstance(source_info, str):
                unique_sources.add(source_info)

    if not unique_sources:
        return json.dumps({"count": 0, "maps": []}, ensure_ascii=False)

    # 為了讓名稱更簡潔，可以做一些基本清理
    # 例如，從 "《台灣米其林指南2024》必比登推介地圖" 中取出 "必比登"
    cleaned_names = set()
    for s in unique_sources:
        if "必比登" in s:
            cleaned_names.add("米其林必比登推薦")
        elif "米其林" in s:
            cleaned_names.add("米其林星級餐廳")
        elif "黃仁勳" in s:
            cleaned_names.add("黃仁勳美食地圖")
        elif "500碗" in s:
            cleaned_names.add("500碗小吃地圖")
        elif "寵物友善" in s:
            cleaned_names.add("寵物友善餐廳")
        else:
            cleaned_names.add(s) # 如果沒有匹配，保留原名

    map_list = sorted(list(cleaned_names))

    return json.dumps({
        "count": len(map_list),
        "maps": map_list,
        "message": f"我這裡有 {len(map_list)} 種美食地圖可供參考：{', '.join(map_list)}。"
    }, ensure_ascii=False, indent=2)

@tool
def get_metro_line_info(line_name: str) -> str:
    """
    【捷運路網專家】
    當使用者詢問關於特定捷運「路線」的資訊時使用此工具。
    例如：「文湖線的起點和終點是哪裡？」、「板南線有哪些轉乘站？」
    它會回傳該路線的起訖站、所有車站和可轉乘的站點列表。
    """
    logger.info(f"🗺️ [路網查詢] 正在查詢路線資訊：{line_name}")
    
    # 標準化使用者可能輸入的簡稱
    normalized_map = {
        "棕": "文湖線", "文湖": "文湖線", "br": "文湖線",
        "紅": "淡水信義線", "淡水信義": "淡水信義線", "r": "淡水信義線",
        "綠": "松山新店線", "松山新店": "松山新店線", "g": "松山新店線",
        "橘": "中和新蘆線", "中和新蘆": "中和新蘆線", "o": "中和新蘆線",
        "藍": "板南線", "板南": "板南線", "bl": "板南線",
        "黃": "環狀線", "環狀": "環狀線", "y": "環狀線",
    }
    
    # 查找最符合的路線全名
    best_match_name = line_name
    for key, value in normalized_map.items():
        if key in line_name.lower():
            best_match_name = value
            break
            
    line_details = routing_manager.get_line_details(best_match_name)
    
    return json.dumps(line_details, ensure_ascii=False, indent=2)

# ✨✨✨ START: 新增的工具 ✨✨✨
@tool
def list_all_metro_lines() -> str:
    """
    【捷運路線盤點專家】
    當使用者詢問「有哪些捷運線？」或要求列出所有路線時使用此工具。
    它會回傳一個包含所有捷運線的名稱、代號和顏色的完整列表。
    """
    logger.info("🗺️ [路網查詢] 正在列出所有捷運路線...")
    all_lines = routing_manager.list_all_lines()
    return json.dumps(all_lines, ensure_ascii=False, indent=2)
# ✨✨✨ END: 新增的工具 ✨✨✨

@tool
def list_all_stations() -> str:
    """
    【捷運車站盤點專家】
    當使用者詢問「有哪些捷運站？」或要求列出所有車站時使用此工具。
    """
    logger.info("🚉 [車站查詢] 正在列出所有捷運車站...")
    station_names = station_manager.get_all_station_names()
    
    if not station_names:
        return json.dumps({"error": "無法獲取車站列表。"}, ensure_ascii=False)
        
    return json.dumps({
        "count": len(station_names),
        "stations": station_names,
        "message": f"台北捷運系統目前共有 {len(station_names)} 個車站。"
    }, ensure_ascii=False, indent=2)
# ✨✨✨ END: 新增的工具 ✨✨✨

@tool
def get_best_car_for_exit(station_name: str, direction: str, exit_number: int) -> str:
    """
    【最佳車廂推薦專家】
    當使用者到達某個捷運站，並想知道前往特定出口（例如3號出口）應該從哪個車廂下車最快時，使用此工具。
    你需要提供車站名稱、列車的行駛方向（終點站名稱），以及使用者想去的出口號碼。
    """
    logger.info(f" optimizing [最佳車廂推薦] 正在為「{station_name}」站，往「{direction}」方向，查詢靠近「{exit_number}」號出口的車廂。")

    # 1. 載入車廂出口對應資料
    car_exit_data = local_data_manager.car_exit_map
    if not car_exit_data:
        return json.dumps({"error": "車廂出口對應資料尚未載入。"}, ensure_ascii=False)

    # 2. 標準化站名以便搜尋
    norm_station = normalize_station_name(station_name)
    
    # 3. 尋找符合的車站、路線與方向
    found_cars = []
    station_info = None
    for item in car_exit_data:
        if normalize_station_name(item.get("station")) == norm_station:
            station_info = item
            break
            
    if not station_info:
        return json.dumps({"error": f"找不到「{station_name}」的車廂出口資料。"}, ensure_ascii=False)

    # 4. 尋找最匹配的方向 (處理 "往動物園" vs "動物園" 的情況)
    direction_data = None
    for dir_key, dir_value in station_info.get("Directions", {}).items():
        if direction in dir_key or dir_key in direction:
            direction_data = dir_value
            break
            
    if not direction_data:
         return json.dumps({"error": f"在「{station_name}」站找不到往「{direction}」方向的列車資訊。"}, ensure_ascii=False)

    # 5. 遍歷車廂列表，找出包含目標出口的車廂
    for car_info in direction_data.get("list", []):
        if exit_number in car_info.get("exits", []):
            found_cars.append(str(car_info.get("car")))

    # 6. 格式化回傳訊息
    if not found_cars:
        message = f"很抱歉，在「{station_name}」站往「{direction}」方向的列車，資料中沒有特別標示靠近 {exit_number} 號出口的車廂。建議您在月台留意出口指示圖。"
        return json.dumps({"station": station_name, "exit_number": exit_number, "found": False, "message": message}, ensure_ascii=False)
    
    car_str = "、".join(found_cars)
    message = f"好的！在「{station_name}」站下車後，若要前往 {exit_number} 號出口，建議您搭乘第 **{car_str}** 節車廂會最快抵達！"
    
    return json.dumps({
        "station": station_name,
        "direction": direction,
        "exit_number": exit_number,
        "recommended_cars": found_cars,
        "message": message
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
    search_lost_and_found,
    search_mrt_food,
    list_available_food_maps,
    get_metro_line_info,
    list_all_metro_lines,
    list_all_stations, 
    get_best_car_for_exit,
]
