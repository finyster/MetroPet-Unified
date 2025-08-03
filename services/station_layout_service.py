# services/station_layout_service.py

import json
import logging
import os
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class StationLayoutService:
    """
    管理和查詢捷運車站內部佈局資訊的服務，例如車廂與出口的對應關係。
    """
    def __init__(self, layout_data_path: str):
        self.layout_data_path = layout_data_path
        self.layouts = self._load_layout_data()
        if self.layouts:
            logger.info(f"--- ✅ [Station Layout] 已成功從 {layout_data_path} 載入 {len(self.layouts)} 筆車站佈局資料。 ---")
        else:
            logger.warning(f"--- ⚠️ [Station Layout] 未能從 {layout_data_path} 載入車站佈局資料，相關功能將無法使用。 ---")

    def _load_layout_data(self) -> Dict[str, Any]:
        """從 JSON 檔案載入車站佈局資料。"""
        if not os.path.exists(self.layout_data_path):
            logger.error(f"--- ❌ [Station Layout] 找不到車站佈局資料檔案: {self.layout_data_path} ---")
            return {}
        try:
            with open(self.layout_data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"--- ❌ [Station Layout] 讀取或解析車站佈局資料時發生錯誤: {e} ---", exc_info=True)
            return {}

    def get_exit_car_mapping_for_line(self, station_id: str) -> Dict[str, List[int]]:
        """
        獲取指定車站特定路線的「出口-車廂」對應關係。
        """
        # 從 StationID 中提取線路代碼 (例如 "BL", "R", "G")
        line_code = ''.join(filter(str.isalpha, station_id))
        station_layout = self.layouts.get(station_id, {})
        
        # 返回對應線路的佈局，如果沒有特定線路，則返回通用佈局
        return station_layout.get(line_code, station_layout.get("common", {}))

