# services/station_service.py
import json
import os
import re
import logging
from typing import List, Dict, Optional, Tuple

# --- 路徑設置 ---
import sys
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')

if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

import config
from services.tdx_service import tdx_api # 確保匯入 tdx_api
from utils.exceptions import DataLoadError, StationNotFoundError # 導入自定義例外

# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StationManager:
    def __init__(self, station_data_path: str):
        self.station_data_path = station_data_path
        
        # 【新增】站名別名映射：鍵是使用者可能輸入的別名 (已標準化)，值是官方全名 (未標準化)
        # 這裡的鍵必須是經過 _normalize_name_for_map 處理後的，以確保查找時的一致性
        self.station_aliases = {
            self._normalize_name_for_map("北車"): "台北車站",
            self._normalize_name_for_map("台車"): "台北車站",
            self._normalize_name_for_map("101"): "台北101/世貿",
            self._normalize_name_for_map("西門"): "西門",
            self._normalize_name_for_map("淡水"): "淡水",
            self._normalize_name_for_map("板橋"): "板橋", 
            self._normalize_name_for_map("市政府"): "市政府",
            self._normalize_name_for_map("東門"): "東門",
            self._normalize_name_for_map("忠孝復興"): "忠孝復興",
            self._normalize_name_for_map("動物園"): "動物園",
            self._normalize_name_for_map("南港展覽館"): "南港展覽館",
            self._normalize_name_for_map("象山"): "象山",
            self._normalize_name_for_map("頂埔"): "頂埔",
            self._normalize_name_for_map("迴龍"): "迴龍",
            self._normalize_name_for_map("蘆洲"): "蘆洲",
            self._normalize_name_for_map("新店"): "新店",
            self._normalize_name_for_map("台電大樓"): "台電大樓",
            self._normalize_name_for_map("南勢角"): "南勢角",
            self._normalize_name_for_map("大安"): "大安", # 文湖線
            self._normalize_name_for_map("木柵"): "木柵", # 文湖線
            self._normalize_name_for_map("中山國中"): "中山國中", # 文湖線
            self._normalize_name_for_map("松山機場"): "松山機場", # 文湖線
            self._normalize_name_for_map("大直"): "大直", # 文湖線
            self._normalize_name_for_map("中山"): "中山", # 確保中山站也在別名中，指向其官方名稱
            self._normalize_name_for_map("中正紀念堂"): "中正紀念堂",
            self._normalize_name_for_map("古亭"): "古亭",
            self._normalize_name_for_map("小南門"): "小南門",
            self._normalize_name_for_map("松山"): "松山",
            self._normalize_name_for_map("景美"): "景美",
            self._normalize_name_for_map("公館"): "公館",
            self._normalize_name_for_map("萬芳醫院"): "萬芳醫院",
            self._normalize_name_for_map("大坪林"): "大坪林",
            self._normalize_name_for_map("七張"): "七張",
            self._normalize_name_for_map("新店區公所"): "新店區公所",
            self._normalize_name_for_map("小碧潭"): "小碧潭",
            self._normalize_name_for_map("北投"): "北投",
            self._normalize_name_for_map("奇岩"): "奇岩",
            self._normalize_name_for_map("唭哩岸"): "唭哩岸",
            self._normalize_name_for_map("石牌"): "石牌",
            self._normalize_name_for_map("明德"): "明德",
            self._normalize_name_for_map("芝山"): "芝山",
            self._normalize_name_for_map("士林"): "士林",
            self._normalize_name_for_map("劍潭"): "劍潭",
            self._normalize_name_for_map("圓山"): "圓山",
            self._normalize_name_for_map("民權西路"): "民權西路",
            self._normalize_name_for_map("雙連"): "雙連",
            self._normalize_name_for_map("善導寺"): "善導寺",
            self._normalize_name_for_map("忠孝新生"): "忠孝新生",
            self._normalize_name_for_map("忠孝敦化"): "忠孝敦化",
            self._normalize_name_for_map("國父紀念館"): "國父紀念館",
            self._normalize_name_for_map("永春"): "永春",
            self._normalize_name_for_map("後山埤"): "後山埤",
            self._normalize_name_for_map("昆陽"): "昆陽",
            self._normalize_name_for_map("府中"): "府中",
            self._normalize_name_for_map("亞東醫院"): "亞東醫院",
            self._normalize_name_for_map("海山"): "海山",
            self._normalize_name_for_map("土城"): "土城",
            self._normalize_name_for_map("永寧"): "永寧",
            self._normalize_name_for_map("頂溪"): "頂溪",
            self._normalize_name_for_map("永安市場"): "永安市場",
            self._normalize_name_for_map("景安"): "景安",
            self._normalize_name_for_map("南勢角"): "南勢角",
            self._normalize_name_for_map("景美"): "景美",
            self._normalize_name_for_map("萬隆"): "萬隆",
            self._normalize_name_for_map("公館"): "公館",
            self._normalize_name_for_map("台電大樓"): "台電大樓",
            self._normalize_name_for_map("中正紀念堂"): "中正紀念堂",
            self._normalize_name_for_map("東門"): "東門",
            self._normalize_name_for_map("大橋頭"): "大橋頭",
            self._normalize_name_for_map("三重國小"): "三重國小",
            self._normalize_name_for_map("三和國中"): "三和國中",
            self._normalize_name_for_map("徐匯中學"): "徐匯中學",
            self._normalize_name_for_map("三民高中"): "三民高中",
            self._normalize_name_for_map("蘆洲"): "蘆洲",
            self._normalize_name_for_map("菜寮"): "菜寮",
            self._normalize_name_for_map("三重"): "三重",
            self._normalize_name_for_map("先嗇宮"): "先嗇宮",
            self._normalize_name_for_map("頭前庄"): "頭前庄",
            self._normalize_name_for_map("新莊"): "新莊",
            self._normalize_name_for_map("輔大"): "輔大",
            self._normalize_name_for_map("丹鳳"): "丹鳳",
            self._normalize_name_for_map("迴龍"): "迴龍",
            self._normalize_name_for_map("南港軟體園區"): "南港軟體園區",
            self._normalize_name_for_map("東湖"): "東湖",
            self._normalize_name_for_map("葫洲"): "葫洲",
            self._normalize_name_for_map("大湖公園"): "大湖公園",
            self._normalize_name_for_map("內湖"): "內湖",
            self._normalize_name_for_map("文德"): "文德",
            self._normalize_name_for_map("港墘"): "港墘",
            self._normalize_name_for_map("劍南路"): "劍南路",
            self._normalize_name_for_map("西湖"): "西湖",
            self._normalize_name_for_map("大直"): "大直",
            self._normalize_name_for_map("中山國中"): "中山國中",
            self._normalize_name_for_map("南京復興"): "南京復興",
            self._normalize_name_for_map("忠孝復興"): "忠孝復興",
            self._normalize_name_for_map("大安"): "大安",
            self._normalize_name_for_map("科技大樓"): "科技大樓",
            self._normalize_name_for_map("六張犁"): "六張犁",
            self._normalize_name_for_map("麟光"): "麟光",
            self._normalize_name_for_map("辛亥"): "辛亥",
            self._normalize_name_for_map("萬芳醫院"): "萬芳醫院",
            self._normalize_name_for_map("萬芳社區"): "萬芳社區",
            self._normalize_name_for_map("木柵"): "木柵",
            self._normalize_name_for_map("動物園"): "動物園",
            self._normalize_name_for_map("松山"): "松山",
            self._normalize_name_for_map("南京三民"): "南京三民",
            self._normalize_name_for_map("台北小巨蛋"): "台北小巨蛋",
            self._normalize_name_for_map("松江南京"): "松江南京",
            self._normalize_name_for_map("行天宮"): "行天宮",
            self._normalize_name_for_map("中山國小"): "中山國小",
            self._normalize_name_for_map("大橋頭"): "大橋頭",
            self._normalize_name_for_map("大橋頭站"): "大橋頭", # 確保帶「站」的別名也處理
            self._normalize_name_for_map("忠孝新生"): "忠孝新生",
            self._normalize_name_for_map("忠孝敦化"): "忠孝敦化",
            self._normalize_name_for_map("國父紀念館"): "國父紀念館",
            self._normalize_name_for_map("永春"): "永春",
            self._normalize_name_for_map("後山埤"): "後山埤",
            self._normalize_name_for_map("昆陽"): "昆陽",
            self._normalize_name_for_map("南港"): "南港", # 確保南港能被解析
        }
        # 【新增】一個反向映射，用於從標準化名稱查找原始官方名稱
        self.official_name_map: Dict[str, str] = {} 
        self.station_map = self._load_or_create_station_data()
        # 【新增】將別名也納入 station_map 的鍵中，指向其官方站名對應的 ID
        self._add_aliases_to_station_map()


    def _load_or_create_station_data(self) -> dict:
        """
        嘗試從本地檔案載入站點資料。如果檔案不存在、損壞或為空，
        則從 TDX API 重新獲取並建立資料。
        """
        if os.path.exists(self.station_data_path) and os.path.getsize(self.station_data_path) > 0:
            try:
                with open(self.station_data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data: # 確保載入的資料不為空字典
                    logger.info(f"--- ✅ 已從 {os.path.basename(self.station_data_path)} 載入站點資料 ---")
                    # 【新增】載入時也建立 official_name_map
                    self._build_official_name_map_from_loaded_data(data) # 修正：使用新方法
                    return data
            except json.JSONDecodeError as e:
                logger.warning(f"--- ⚠️ 讀取站點資料失敗 (JSON 解碼錯誤: {e})，將重新生成。 ---")
            except Exception as e:
                logger.warning(f"--- ⚠️ 讀取站點資料失敗 ({e})，將重新生成。 ---")
        
        logger.info(f"--- ⚠️ 本地站點資料不存在、損毀或為空，正在從 TDX API 重新生成... ---")
        return self.update_station_data()

    def update_station_data(self) -> dict:
        """
        從 TDX API 獲取所有捷運站點資訊，處理別名，並儲存為 JSON 檔案。
        """
        all_stations_data = tdx_api.get_all_stations_of_route()
        if not all_stations_data:
            logger.error("--- ❌ 無法從 TDX API 獲取車站資料 ---")
            return {}

        station_map = {}
        # 【新增】暫存原始站名與標準化名稱的對應
        temp_official_name_map = {}
        
        for route in all_stations_data:
            for station in route.get('Stations', []): # 確保 Stations 是列表
                zh_name = station.get('StationName', {}).get('Zh_tw')
                en_name = station.get('StationName', {}).get('En')
                station_id = station.get('StationID')

                if not (zh_name and station_id):
                    continue

                # 【修改】使用內部標準化函式來處理站名，移除「站」字，並轉換為小寫
                normalized_zh_name = self._normalize_name_for_map(zh_name)
                
                keys_to_add = {normalized_zh_name}
                if en_name:
                    keys_to_add.add(self._normalize_name_for_map(en_name)) # 英文名也轉小寫
                
                for key in keys_to_add:
                    if key: # 確保標準化後的鍵不為 None 或空字串
                        if key not in station_map:
                            station_map[key] = set()
                        station_map[key].add(station_id)
                        # 【新增】建立標準化名稱到原始中文名稱的映射
                        temp_official_name_map[key] = zh_name 

        # 將 set 轉換為 list 並排序，以便 JSON 序列化
        station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
        
        os.makedirs(os.path.dirname(self.station_data_path), exist_ok=True)
        with open(self.station_data_path, 'w', encoding='utf-8') as f:
            json.dump(station_map_list, f, ensure_ascii=False, indent=2)
        logger.info(f"--- ✅ 站點資料已成功建立於 {self.station_data_path} ---")

        # 【新增】更新實例的 official_name_map
        self.official_name_map = temp_official_name_map
        return station_map_list

    # 【新增】建立 official_name_map 的輔助方法 (從載入的資料建立)
    def _build_official_name_map_from_loaded_data(self, station_data: Dict[str, List[str]]):
        """從載入的站點資料中建立標準化名稱到原始官方名稱的映射。"""
        self.official_name_map = {}
        # 由於 station_data 只有標準化名稱和 ID，我們需要原始的 TDX 資料來建立完整的映射
        all_stations_data = tdx_api.get_all_stations_of_route()
        if not all_stations_data:
            logger.warning("--- ⚠️ 無法從 TDX API 獲取原始車站資料以建立 official_name_map。 ---")
            return

        for route in all_stations_data:
            for station in route.get('Stations', []):
                zh_name = station.get('StationName', {}).get('Zh_tw')
                if zh_name:
                    normalized_name = self._normalize_name_for_map(zh_name)
                    self.official_name_map[normalized_name] = zh_name
                    # 處理別名，確保別名也能反向查找到官方名稱
                    for alias_key, official_name_value in self.station_aliases.items():
                        if self._normalize_name_for_map(official_name_value) == normalized_name:
                            self.official_name_map[alias_key] = official_name_value # 儲存別名到官方名稱的映射

    # 【新增】從標準化名稱獲取原始官方名稱的方法
    def get_official_unnormalized_name(self, normalized_name: str) -> Optional[str]:
        """
        根據標準化後的站名，回傳其原始的官方全名 (未標準化)。
        如果找不到，則返回標準化後的名稱本身。
        """
        # 【修正】如果找不到原始名稱，則返回標準化後的名稱本身，而不是 None
        return self.official_name_map.get(normalized_name, normalized_name)

    # 【新增】內部使用的標準化函式
    def _normalize_name_for_map(self, name: str) -> str:
        """內部使用的標準化函式，用於處理站名，移除「站」字並轉小寫。"""
        if not name:
            return ""
        # 移除站字，並將全形括號替換為半形，然後轉為小寫
        # 修正正則表達式，確保能正確移除括號內容，例如 "台北車站(淡水線)" -> "台北車站"
        name = re.sub(r'[（\(][^）\)]*[）\)]', '', name) 
        return re.sub(r'站$', '', name).lower()

    # 【新增】將預設別名加入到 station_map 中
    def _add_aliases_to_station_map(self):
        """將預設別名加入到 station_map 中，指向其官方站名對應的 ID。"""
        for alias_key, official_name_value in self.station_aliases.items():
            # alias_key 已經是標準化後的別名 (例如 "北車")
            # official_name_value 是原始的官方名稱 (例如 "台北車站")
            
            # 我們需要找到官方名稱在 station_map 中的鍵 (即標準化後的官方名稱)
            normalized_official_name_key = self._normalize_name_for_map(official_name_value)
            
            if normalized_official_name_key in self.station_map:
                # 如果官方名稱已經在 map 中，則將別名指向相同的 ID 列表
                self.station_map[alias_key] = self.station_map[normalized_official_name_key]
                # 【新增】確保別名也能反向查找到官方名稱
                self.official_name_map[alias_key] = official_name_value
            else:
                logger.warning(f"--- ⚠️ 別名 '{alias_key}' 的官方名稱 '{official_name_value}' (標準化後: '{normalized_official_name_key}') 不在 station_map 中，無法建立別名映射。請檢查別名設定或 TDX 資料。 ---")

    # 【修正】resolve_station_alias 方法
    def resolve_station_alias(self, name: str) -> str:
        """
        將使用者輸入的站名（可能是別名）轉換為標準化的官方全名。
        這個方法會返回一個可以用於查詢 station_map 的標準化名稱。
        """
        if not name:
            return ""
        
        # 將輸入名稱標準化，用於在別名字典中查找
        normalized_input = self._normalize_name_for_map(name)
        
        # 如果標準化後的輸入是我們定義的別名，則返回其對應的官方名稱的標準化形式
        if normalized_input in self.station_aliases:
            # 這裡返回的仍然是標準化後的名稱，例如 "台北車"
            return self._normalize_name_for_map(self.station_aliases[normalized_input])
        
        # 如果不是別名，則直接返回標準化後的輸入名稱
        return normalized_input

    def get_station_ids(self, station_name: str) -> list[str] | None:
        """
        【關鍵修正】
        根據站名，回傳一個包含所有對應 ID 的「列表」。
        此方法現在會自動處理站名正規化與別名解析。
        """
        if not station_name:
            return None
        
        # 步驟 1：在查詢前，先呼叫 resolve_station_alias 進行正規化和別名解析
        resolved_key = self.resolve_station_alias(station_name)
        
        # 步驟 2：使用解析後的標準化鍵進行查詢
        if resolved_key:
            ids = self.station_map.get(resolved_key)
            if ids:
                # 找到了！返回 ID 列表
                return ids
            else:
                # 這個 log 很重要，可以幫助我們除錯，看到解析後的鍵到底是什麼
                logger.warning(f"--- ❌ 在 station_map 中找不到已解析的鍵: '{resolved_key}' (來自原始輸入: '{station_name}') ---")
                return None
        else:
            logger.warning(f"--- ❌ 無法處理或解析站點名稱: '{station_name}' ---")
            return None

    # 【新增】resolve_direction 方法
    def resolve_direction(self, station_name: str, direction_query: str) -> List[str]:
        """
        根據使用者查詢的站名和方向，解析出可能的官方終點站名稱 (已標準化)。
        例如：在「中山」站問往「北車」，應該返回 [ '松山', '象山' ] (標準化後)
        """
        # 將輸入的站名和方向查詢標準化
        resolved_station_name = self.resolve_station_alias(station_name)
        normalized_direction_query = self._normalize_name_for_map(direction_query)

        # 簡易的別名對應 (鍵和值都應是標準化後的名稱)
        # 這裡的別名是針對方向查詢的，例如 "往中山" -> "松山"
        direction_aliases = {
            self._normalize_name_for_map("北車"): self._normalize_name_for_map("台北車站"),
            self._normalize_name_for_map("往北車"): self._normalize_name_for_map("台北車站"),
            self._normalize_name_for_map("往中山"): self._normalize_name_for_map("松山"), # 綠線方向
            self._normalize_name_for_map("往動物園"): self._normalize_name_for_map("動物園"),
            self._normalize_name_for_map("往南港"): self._normalize_name_for_map("南港展覽館"),
            self._normalize_name_for_map("往南港展覽館"): self._normalize_name_for_map("南港展覽館"),
            self._normalize_name_for_map("往頂埔"): self._normalize_name_for_map("頂埔"),
            self._normalize_name_for_map("往淡水"): self._normalize_name_for_map("淡水"),
            self._normalize_name_for_map("往象山"): self._normalize_name_for_map("象山"),
            self._normalize_name_for_map("往新店"): self._normalize_name_for_map("新店"),
            self._normalize_name_for_map("往迴龍"): self._normalize_name_for_map("迴龍"),
            self._normalize_name_for_map("往蘆洲"): self._normalize_name_for_map("蘆洲"),
            self._normalize_name_for_map("往南勢角"): self._normalize_name_for_map("南勢角"),
            self._normalize_name_for_map("往大安"): self._normalize_name_for_map("大安"),
            self._normalize_name_for_map("往木柵"): self._normalize_name_for_map("木柵"),
            self._normalize_name_for_map("往台電大樓"): self._normalize_name_for_map("台電大樓"),
            self._normalize_name_for_map("往西門"): self._normalize_name_for_map("西門"),
            self._normalize_name_for_map("往松山"): self._normalize_name_for_map("松山"),
            # 確保終點站本身也在別名中，指向自己
            self._normalize_name_for_map("南港展覽館"): self._normalize_name_for_map("南港展覽館"),
            self._normalize_name_for_map("動物園"): self._normalize_name_for_map("動物園"),
            self._normalize_name_for_map("頂埔"): self._normalize_name_for_map("頂埔"),
            self._normalize_name_for_map("迴龍"): self._normalize_name_for_map("迴龍"),
            self._normalize_name_for_map("蘆洲"): self._normalize_name_for_map("蘆洲"),
            self._normalize_name_for_map("淡水"): self._normalize_name_for_map("淡水"),
            self._normalize_name_for_map("新店"): self._normalize_name_for_map("新店"),
            self._normalize_name_for_map("象山"): self._normalize_name_for_map("象山"),
            self._normalize_name_for_map("台北車站"): self._normalize_name_for_map("台北車站"),
            self._normalize_name_for_map("大安"): self._normalize_name_for_map("大安"),
            self._normalize_name_for_map("木柵"): self._normalize_name_for_map("木柵"),
            self._normalize_name_for_map("松山"): self._normalize_name_for_map("松山"),
            self._normalize_name_for_map("南勢角"): self._normalize_name_for_map("南勢角"),
            self._normalize_name_for_map("台電大樓"): self._normalize_name_for_map("台電大樓"),
            self._normalize_name_for_map("西門"): self._normalize_name_for_map("西門"),
        }

        # 優先從別名中查找明確的終點站
        if normalized_direction_query in direction_aliases:
            return [self._normalize_name_for_map(direction_aliases[normalized_direction_query])]

        # 如果 direction_query 本身就是一個標準化後的站名，則返回它自己
        if normalized_direction_query in self.station_map:
            return [normalized_direction_query]

        # 如果是模糊查詢 (如 "any" 或空字串)，則返回該站點所有線路的所有可能終點站
        if not direction_query or normalized_direction_query == 'any':
            return self.get_terminal_stations_for(resolved_station_name)

        # 如果方向查詢是包含「往」字的，嘗試提取後面的站名並解析
        match_wang = re.match(r'^往(.+)$', normalized_direction_query)
        if match_wang:
            potential_dest_name = match_wang.group(1)
            # 再次嘗試用這個潛在終點站名進行別名解析
            resolved_potential_dest = self.resolve_station_alias(potential_dest_name)
            if resolved_potential_dest in self.station_map:
                return [resolved_potential_dest]
        
        # 如果都無法解析，則返回空列表
        logger.warning(f"無法解析方向查詢 '{direction_query}' (標準化後: '{normalized_direction_query}') 對於車站 '{resolved_station_name}'。")
        return []


    def get_terminal_stations_for(self, station_name: str) -> List[str]:
        """
        根據站名，回傳該站點所有可能的終點站方向 (標準化後的名稱)。
        這是一個簡化的實作，您可以根據 mrt_station_info.json 建立更完整的路線方向對應表。
        """
        # 這裡需要根據您的實際路網數據來實現
        # 由於目前沒有完整的路網圖數據來動態判斷，這裡先提供一個簡化/模擬的邏輯
        
        # 為了演示目的，先提供一些常見的終點站 (鍵和值都應是標準化後的名稱)
        common_terminals = {
            self._normalize_name_for_map("南港展覽館"): [self._normalize_name_for_map("南港展覽館")],
            self._normalize_name_for_map("動物園"): [self._normalize_name_for_map("動物園")],
            self._normalize_name_for_map("頂埔"): [self._normalize_name_for_map("頂埔")],
            self._normalize_name_for_map("迴龍"): [self._normalize_name_for_map("迴龍")],
            self._normalize_name_for_map("蘆洲"): [self._normalize_name_for_map("蘆洲")],
            self._normalize_name_for_map("淡水"): [self._normalize_name_for_map("淡水")],
            self._normalize_name_for_map("新店"): [self._normalize_name_for_map("新店")],
            self._normalize_name_for_map("象山"): [self._normalize_name_for_map("象山")],
            
            # 針對主要轉乘站和線路，列出其所有可能的終點站
            self._normalize_name_for_map("台北車站"): [
                self._normalize_name_for_map("南港展覽館"), 
                self._normalize_name_for_map("頂埔"), 
                self._normalize_name_for_map("象山"), 
                self._normalize_name_for_map("淡水"), 
                self._normalize_name_for_map("新店"), 
                self._normalize_name_for_map("迴龍"), 
                self._normalize_name_for_map("蘆洲"), 
                self._normalize_name_for_map("動物園")
            ], 
            self._normalize_name_for_map("中山"): [
                self._normalize_name_for_map("南港展覽館"), # 松山新店線往南港
                self._normalize_name_for_map("象山"), # 淡水信義線往象山
                self._normalize_name_for_map("淡水"), # 淡水信義線往淡水
                self._normalize_name_for_map("新店") # 松山新店線往新店
            ], 
            self._normalize_name_for_map("板橋"): [
                self._normalize_name_for_map("南港展覽館"), 
                self._normalize_name_for_map("頂埔")
            ], 
            self._normalize_name_for_map("西門"): [
                self._normalize_name_for_map("南港展覽館"), 
                self._normalize_name_for_map("頂埔"),
                self._normalize_name_for_map("松山"), # 綠線
                self._normalize_name_for_map("新店") # 綠線
            ], 
            self._normalize_name_for_map("忠孝復興"): [
                self._normalize_name_for_map("南港展覽館"), 
                self._normalize_name_for_map("動物園"), 
                self._normalize_name_for_map("頂埔"), 
                self._normalize_name_for_map("象山")
            ], 
            self._normalize_name_for_map("中正紀念堂"): [
                self._normalize_name_for_map("淡水"),
                self._normalize_name_for_map("象山"),
                self._normalize_name_for_map("松山"),
                self._normalize_name_for_map("新店")
            ],
            self._normalize_name_for_map("古亭"): [
                self._normalize_name_for_map("淡水"),
                self._normalize_name_for_map("象山"),
                self._normalize_name_for_map("松山"),
                self._normalize_name_for_map("新店"),
                self._normalize_name_for_map("南勢角"),
                self._normalize_name_for_map("迴龍"),
                self._normalize_name_for_map("蘆洲")
            ],
            self._normalize_name_for_map("東門"): [
                self._normalize_name_for_map("迴龍"),
                self._normalize_name_for_map("蘆洲"),
                self._normalize_name_for_map("象山"),
                self._normalize_name_for_map("淡水")
            ],
            self._normalize_name_for_map("大安"): [
                self._normalize_name_for_map("動物園"),
                self._normalize_name_for_map("南港展覽館"),
                self._normalize_name_for_map("淡水"),
                self._normalize_name_for_map("象山")
            ],
            self._normalize_name_for_map("南京復興"): [
                self._normalize_name_for_map("南港展覽館"),
                self._normalize_name_for_map("動物園"),
                self._normalize_name_for_map("松山"),
                self._normalize_name_for_map("新店")
            ],
            self._normalize_name_for_map("松江南京"): [
                self._normalize_name_for_map("松山"),
                self._normalize_name_for_map("新店"),
                self._normalize_name_for_map("南港展覽館"),
                self._normalize_name_for_map("動物園")
            ],
            # ... 更多站點和其對應的終點站
        }
        
        # 【修改】這裡也需要先解析別名，因為 get_terminal_stations_for 可能也會被呼叫
        # resolve_station_alias 返回的是標準化後的名稱，可以直接用於字典查找
        resolved_name = self.resolve_station_alias(station_name) 
        return common_terminals.get(resolved_name, [])

# 在檔案最末端，確保單一實例被正確建立
# 根據服務註冊機制的設計，這裡需要確保 station_manager 實例被創建
# 如果 config.STATION_DATA_PATH 路徑有問題，請確保其指向正確的 JSON 檔案位置
station_manager = StationManager(config.STATION_DATA_PATH)