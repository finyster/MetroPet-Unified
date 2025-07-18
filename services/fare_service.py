# services/fare_service.py

from typing import Dict, Any # 修正：導入 Any 類型
from utils.exceptions import StationNotFoundError
from utils.station_name_normalizer import normalize_station_name # 導入標準化工具
import logging

logger = logging.getLogger(__name__)

class FareService:
    """
    負責處理所有與票價相關的業務邏輯。
    此服務在初始化時會載入票價資料，並提供查詢功能。
    """
    def __init__(self, fare_data: Dict[str, Dict[str, int]], station_id_map: Dict[str, list]):
        # 透過依賴注入的方式傳入票價資料和站點ID映射
        self._fare_data = fare_data
        self._station_id_map = station_id_map # {normalized_name: [StationID1, StationID2]}
        logger.info("FareService initialized.")

    def _get_station_ids_from_name(self, station_name: str) -> list[str]:
        """
        根據站名（或別名）取得所有對應的 station_id。
        使用 normalize_station_name 進行標準化處理。
        """
        norm_name = normalize_station_name(station_name)
        if norm_name and norm_name in self._station_id_map:
            return self._station_id_map[norm_name]
        return []

    def get_fare(self, start_station_name: str, end_station_name: str) -> Dict[str, Any]:
        """
        根據使用者輸入的站名查詢票價。

        Args:
            start_station_name (str): 使用者輸入的起點站名。
            end_station_name (str): 使用者輸入的終點站名。

        Returns:
            Dict: 包含票價金額的字典 (全票, 兒童票)。

        Raises:
            StationNotFoundError: 如果任一站名無法識別或找不到票價。
        """
        logger.info(f"查詢票價: {start_station_name} -> {end_station_name}")

        start_ids = self._get_station_ids_from_name(start_station_name)
        end_ids = self._get_station_ids_from_name(end_station_name)

        if not start_ids:
            logger.warning(f"無法識別起點站名稱：'{start_station_name}'")
            raise StationNotFoundError(f"無法識別起點站名稱：'{start_station_name}'")
        if not end_ids:
            logger.warning(f"無法識別終點站名稱：'{end_station_name}'")
            raise StationNotFoundError(f"無法識別終點站名稱：'{end_station_name}'")

        found_fare_info = None
        for s_id in start_ids:
            for e_id in end_ids:
                key1, key2 = f"{s_id}-{e_id}", f"{e_id}-{s_id}"
                if key1 in self._fare_data:
                    found_fare_info = self._fare_data[key1]
                    break
                if key2 in self._fare_data:
                    found_fare_info = self._fare_data[key2]
                    break
            if found_fare_info:
                break
        
        if found_fare_info is None:
            logger.warning(f"找不到從 '{start_station_name}' 到 '{end_station_name}' 的票價資訊。")
            raise StationNotFoundError(f"找不到從 '{start_station_name}' 到 '{end_station_name}' 的票價資訊。")
            
        return {
            "full_fare": found_fare_info.get('全票', '未知'),
            "child_fare": found_fare_info.get('兒童票', '未知')
        }
