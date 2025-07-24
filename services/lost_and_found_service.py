# services/lost_and_found_service.py

from datetime import datetime, timedelta
import logging
from .metro_soap_service import MetroSoapService

logger = logging.getLogger(__name__)

class LostAndFoundService:
    """
    負責處理所有與遺失物相關的業務邏輯。
    【已重構】此服務現在透過注入的 MetroSoapService 來獲取更全面的官方遺失物資料。
    """
    def __init__(self, metro_soap_service: MetroSoapService):
        self.metro_soap_service = metro_soap_service
        logger.info("LostAndFoundService initialized with MetroSoapService.")

    def query_items(self, station_name: str | None = None, item_name: str | None = None, days_ago: int = 7) -> list:
        """
        從官方 SOAP API 查詢捷運遺失物。

        Args:
            station_name (str, optional): 拾獲車站名稱關鍵字. Defaults to None.
            item_name (str, optional): 物品名稱關鍵字. Defaults to None.
            days_ago (int, optional): 查詢過去幾天內的資料. Defaults to 7.

        Returns:
            list: 符合條件的遺失物列表。
        """
        logger.info(f"--- [LostAndFoundService] 透過 SOAP API 查詢遺失物: 車站={station_name}, 物品={item_name}, 過去={days_ago}天 ---")
        
        try:
            # 1. 從 SOAP Service 獲取所有資料
            all_items = self.metro_soap_service.get_all_lost_items_soap()
            if not all_items:
                logger.warning("--- [LostAndFoundService] 從 SOAP API 未獲取到任何遺失物資料。 ---")
                return []

            # 2. 在記憶體中進行篩選
            # 篩選日期
            target_date = datetime.now().date() - timedelta(days=days_ago)
            
            # SOAP API 回傳的鍵名不同，需要調整
            # 例如：'get_date', 'get_place', 'ls_name'
            
            filtered_items = []
            for item in all_items:
                try:
                    # 確保日期欄位存在且格式正確
                    item_date_str = item.get('get_date')
                    if item_date_str:
                        item_date = datetime.strptime(item_date_str, '%Y/%m/%d').date()
                        if item_date < target_date:
                            continue # 日期不符，跳過此項目
                except (ValueError, TypeError):
                    # 日期格式錯誤或類型不對，跳過此項目
                    continue

                # 篩選車站
                if station_name:
                    place = item.get('get_place', '')
                    if station_name.lower() not in place.lower():
                        continue # 車站不符，跳過

                # 篩選物品名稱
                if item_name:
                    name = item.get('ls_name', '')
                    if item_name.lower() not in name.lower():
                        continue # 物品不符，跳過
                
                filtered_items.append(item)

            logger.info(f"--- [LostAndFoundService] 找到 {len(filtered_items)} 筆符合條件的遺失物。 ---")
            return filtered_items[:20]  # 最多返回 20 筆

        except Exception as e:
            logger.error(f"--- ❌ [LostAndFoundService] 處理遺失物查詢時發生未知錯誤: {e} ---", exc_info=True)
            return []