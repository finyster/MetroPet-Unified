# services/id_converter_service.py
import json
import config
import os
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class IdConverterService:
    def __init__(self):
        logger.info("--- [IdConverter] 正在初始化 ID 轉換服務... ---")
        self._tdx_to_sid_map: Dict[str, str] = {}
        self._load_map()

    def _load_map(self):
        """從 stations_sid_map.json 載入 TDX ID (SCODE) 到純數字 SID 的映射。"""
        # 假設您已在 config.py 中定義了 STATIONS_SID_MAP_PATH
        map_path = getattr(config, 'STATIONS_SID_MAP_PATH', 
                           os.path.join(config.DATA_DIR, 'stations_sid_map.json'))

        if not os.path.exists(map_path):
            logger.error(f"--- ❌ [IdConverter] 關鍵對照檔案 {map_path} 不存在！ ---")
            return
        
        with open(map_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        for item in raw_data:
            tdx_id = item.get("SCODE")
            sid = item.get("SID")
            if tdx_id and sid:
                self._tdx_to_sid_map[tdx_id] = sid
        
        logger.info(f"--- ✅ [IdConverter] ID 轉換地圖載入完成，共 {len(self._tdx_to_sid_map)} 筆對應。 ---")

    def tdx_to_sid(self, tdx_id: str) -> Optional[str]:
        """將 TDX 格式的 ID (如 'BR01') 轉換為純數字 SID (如 '019')。"""
        return self._tdx_to_sid_map.get(tdx_id)

# 建立單一實例
id_converter_service = IdConverterService()