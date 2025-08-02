# services/station_service.py

import logging
logger = logging.getLogger(__name__)
import json
import os
import re
import config
from services.tdx_service import tdx_api
from utils.station_name_normalizer import normalize_station_name # 導入標準化工具
from typing import Union, Dict, List, Any  # 新增 Any



class StationManager:
    def __init__(self, station_data_path: str):
        self.station_data_path = station_data_path
        self.station_map = self._load_or_create_station_data()

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
                    print(f"--- ✅ 已從 {os.path.basename(self.station_data_path)} 載入站點資料 ---")
                    return data
            except json.JSONDecodeError as e:
                print(f"--- ⚠️ 讀取站點資料失敗 (JSON 解碼錯誤: {e})，將重新生成。 ---")
            except Exception as e:
                print(f"--- ⚠️ 讀取站點資料失敗 ({e})，將重新生成。 ---")
        
        print(f"--- ⚠️ 本地站點資料不存在、損毀或為空，正在從 TDX API 重新生成... ---")
        return self.update_station_data()

    # 移除 _normalize_name 函式，改用 utils.station_name_normalizer.normalize_station_name

    def update_station_data(self) -> dict:
        """
        從 TDX API 獲取所有捷運站點資訊，處理別名，並儲存為 JSON 檔案。
        """
        all_stations_data = tdx_api.get_all_stations_of_route()
        if not all_stations_data:
            print("--- ❌ 無法從 TDX API 獲取車站資料 ---")
            return {}

        station_map = {}
        # 這裡可以擴展更多的站名別名
        alias_map = {"北車": "台北車站", "台車": "台北車站", "101": "台北101/世貿", "西門": "西門", "淡水": "淡水"}

        for route in all_stations_data:
            for station in route.get('Stations', []):
                zh_name = station.get('StationName', {}).get('Zh_tw')
                en_name = station.get('StationName', {}).get('En')
                station_id = station.get('StationID')

                if not (zh_name and station_id):
                    continue

                # 使用新的標準化函式
                keys_to_add = {normalize_station_name(zh_name)} # 這裡需要注意 normalize_station_name 的行為
                if en_name:
                    keys_to_add.add(normalize_station_name(en_name))
                
                # 處理預設別名
                for alias, primary in alias_map.items():
                    if normalize_station_name(zh_name) == normalize_station_name(primary):
                        keys_to_add.add(normalize_station_name(alias))

                for key in keys_to_add:
                    if key: # 確保標準化後的鍵不為 None 或空字串
                        if key not in station_map:
                            station_map[key] = set()
                        station_map[key].add(station_id)

        # 將 set 轉換為 list 並排序，以便 JSON 序列化
        station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
        
        os.makedirs(os.path.dirname(self.station_data_path), exist_ok=True)
        with open(self.station_data_path, 'w', encoding='utf-8') as f:
            json.dump(station_map_list, f, ensure_ascii=False, indent=2)
        print(f"--- ✅ 站點資料已成功建立於 {self.station_data_path} ---")
        return station_map_list

    def get_station_ids(self, station_name: str) -> Union[List[str], Dict[str, Any], None]:
        """
        【✨最終智慧版✨】
        1. 優先精準比對。
        2. 若失敗，啟用向量語意搜尋。
        3. 若向量搜尋分數高，直接回傳結果。
        4. 若分數低但仍是最佳匹配，則回傳一個「建議物件」。
        """
        if not station_name: return None
        norm_name = normalize_station_name(station_name)
        if not norm_name: return None

        # 步驟 1: 精準比對
        if norm_name in self.station_map:
            return self.station_map[norm_name]

        # 步驟 2: 向量語意搜尋
        from services import service_registry
        logger.warning(f"--- 精準比對失敗，為「{norm_name}」啟用向量語意搜尋... ---")
        vector_service = service_registry.vector_search_service
        best_match_info = vector_service.find_most_similar(norm_name)
        if best_match_info:
            match_name, score = best_match_info
            logger.info(f"--- 向量搜尋結果: 找到最相似站名「{match_name}」，分數: {score:.4f} ---")
            if score >= 0.7:
                logger.info(f"--- 分數超過高信心門檻 0.7，直接採用「{match_name}」。 ---")
                return self.station_map[match_name]
            elif score >= 0.4:
                logger.info(f"--- 分數介於 0.4-0.7 之間，將「{match_name}」作為建議返回。 ---")
                return {"suggestion": match_name, "original_query": station_name}
        logger.error(f"--- ❌ 向量搜尋分數過低或無匹配: '{norm_name}' ---")
        return None

# 在檔案最末端，確保單一實例被正確建立
# 注意：這裡的 StationManager 實例將被 ServiceRegistry 引用
# 如果直接在這裡創建，可能會導致重複載入或初始化問題
# 為了避免循環引用，這裡暫時不直接創建實例，而是讓 ServiceRegistry 統一管理
# station_manager = StationManager(config.STATION_DATA_PATH)