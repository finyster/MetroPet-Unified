# services/lost_and_found_service.py

import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class LostAndFoundService:
    def __init__(self):
        self.api_url = "https://data.metro.taipei/api/v1/List/LostAndFound"
        logger.info("LostAndFoundService initialized.")

    def query_items(self, station_name: str | None = None, item_name: str | None = None, days_ago: int = 7) -> list:
        """
        查詢捷運遺失物。

        Args:
            station_name (str, optional): 拾獲車站名稱. Defaults to None.
            item_name (str, optional): 物品名稱關鍵字. Defaults to None.
            days_ago (int, optional): 查詢過去幾天內的資料. Defaults to 7.

        Returns:
            list: 符合條件的遺失物列表。
        """
        logger.info(f"--- [LostAndFoundService] 查詢遺失物: 車站={station_name}, 物品={item_name}, 過去={days_ago}天 ---")
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            all_items = response.json()

            # 篩選日期: 確保 'laDate' 存在且格式正確
            target_date = datetime.now().date() - timedelta(days=days_ago)
            filtered_items = [
                item for item in all_items
                if 'laDate' in item and datetime.strptime(item['laDate'], '%Y-%m-%d').date() >= target_date
            ]

            # 篩選車站: 確保 'laPlace' 存在
            if station_name:
                filtered_items = [
                    item for item in filtered_items
                    if 'laPlace' in item and station_name.lower() in item['laPlace'].lower()
                ]

            # 篩選物品名稱: 確保 'laName' 存在
            if item_name:
                filtered_items = [
                    item for item in filtered_items
                    if 'laName' in item and item_name.lower() in item['laName'].lower()
                ]
            
            logger.info(f"--- [LostAndFoundService] 找到 {len(filtered_items)} 筆符合條件的遺失物。 ---")
            return filtered_items[:20] # 最多返回 20 筆，避免過多資料

        except requests.RequestException as e:
            logger.error(f"--- ❌ [LostAndFoundService] API 請求失敗: {e} ---", exc_info=True)
            return [] # 發生錯誤時返回空列表
        except Exception as e:
            logger.error(f"--- ❌ [LostAndFoundService] 處理遺失物查詢時發生未知錯誤: {e} ---", exc_info=True)
            return []