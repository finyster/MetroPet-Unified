import os
import pandas as pd
import time
import logging
from typing import List, Dict, Any, Optional

# 假設 metro_soap_service.py 位於 services/ 目錄下
# 為了能獨立執行此腳本，我們需要手動將專案根目錄加入 sys.path
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 現在可以安全地導入
from services.metro_soap_service import metro_soap_api

# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 【關鍵】定義我們最終想要的、標準化的資料欄位 ---
FINAL_COLUMNS = [
    'timestamp', 
    'station_id', 
    'line_direction_cid', 
    'car1_congestion', 
    'car2_congestion', 
    'car3_congestion', 
    'car4_congestion', 
    'car5_congestion', 
    'car6_congestion'
]

def process_high_capacity_data(raw_data: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
    """
    【核心轉換邏輯】處理高運量線的原始 API 資料。
    將 API 回傳的不規則欄位名，映射到我們標準化的欄位名。
    """
    if not raw_data:
        logger.warning("高運量線原始資料為空，跳過處理。")
        return None

    processed_records = []
    for item in raw_data:
        # 【關鍵】處理 'line_direction_cid' 可能為 '401/402' 的格式，我們只取第一個數字
        try:
            direction_cid_str = str(item.get('line_direction_cid', '')).split('/')[0]
            direction_cid = int(direction_cid_str)
        except (ValueError, IndexError):
            logger.warning(f"無法解析高運量線的 direction_cid: {item.get('line_direction_cid')}，跳過此筆記錄。")
            continue

        record = {
            'timestamp': item.get('update_time'),
            'station_id': item.get('station_id'),
            'line_direction_cid': direction_cid,
            'car1_congestion': item.get('car1_congestion'),
            'car2_congestion': item.get('car2_congestion'),
            'car3_congestion': item.get('car3_congestion'),
            'car4_congestion': item.get('car4_congestion'),
            'car5_congestion': item.get('car5_congestion'),
            'car6_congestion': item.get('car6_congestion')
        }
        
        # 驗證必要欄位是否存在
        if not all([record['timestamp'], record['station_id']]):
            logger.warning(f"高運量線記錄缺少必要欄位 (timestamp/station_id)，跳過: {item}")
            continue
            
        processed_records.append(record)
    
    if not processed_records:
        logger.warning("沒有成功處理任何高運量線記錄。")
        return None

    df = pd.DataFrame(processed_records)
    return df

def process_wenhu_data(raw_data: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
    """
    【核心轉換邏輯】處理文湖線的原始 API 資料。
    文湖線只有4節車廂，我們將 car5 和 car6 填充為 NaN (空值)。
    """
    if not raw_data:
        logger.warning("文湖線原始資料為空，跳過處理。")
        return None
        
    processed_records = []
    for item in raw_data:
        try:
            direction_cid = int(item.get('line_direction_cid'))
        except (ValueError, TypeError):
            logger.warning(f"無法解析文湖線的 direction_cid: {item.get('line_direction_cid')}，跳過此筆記錄。")
            continue

        record = {
            'timestamp': item.get('update_time'),
            'station_id': item.get('station_id'),
            'line_direction_cid': direction_cid,
            'car1_congestion': item.get('car1_congestion'),
            'car2_congestion': item.get('car2_congestion'),
            'car3_congestion': item.get('car3_congestion'),
            'car4_congestion': item.get('car4_congestion'),
            'car5_congestion': None,  # 文湖線沒有5號車廂
            'car6_congestion': None   # 文湖線沒有6號車廂
        }

        if not all([record['timestamp'], record['station_id']]):
            logger.warning(f"文湖線記錄缺少必要欄位 (timestamp/station_id)，跳過: {item}")
            continue
        
        processed_records.append(record)

    if not processed_records:
        logger.warning("沒有成功處理任何文湖線記錄。")
        return None

    df = pd.DataFrame(processed_records)
    return df


def collect_and_save_data():
    """收集、處理並儲存擁擠度數據。"""
    logger.info("--- [Collector] 開始新一輪資料收集 ---")
    
    # 1. 收集高運量線資料
    raw_high_capacity = metro_soap_api.get_high_capacity_car_weight_info()
    if raw_high_capacity:
        df_high = process_high_capacity_data(raw_high_capacity)
        if df_high is not None and not df_high.empty:
            output_path = os.path.join(project_root, 'data', 'high_capacity_congestion.csv')
            # 確保所有欄位都存在，且順序正確
            df_high = df_high.reindex(columns=FINAL_COLUMNS)
            df_high.to_csv(output_path, mode='a', header=not os.path.exists(output_path), index=False)
            logger.info(f"    -> ✅ 成功處理並儲存 {len(df_high)} 筆高運量線資料。")
    else:
        logger.error("    -> ❌ 從 API 獲取高運量線資料失敗。")

    # 2. 收集文湖線資料
    raw_wenhu = metro_soap_api.get_wenhu_car_weight_info()
    if raw_wenhu:
        df_wenhu = process_wenhu_data(raw_wenhu)
        if df_wenhu is not None and not df_wenhu.empty:
            output_path = os.path.join(project_root, 'data', 'wenhu_congestion.csv')
            # 確保所有欄位都存在，且順序正確
            df_wenhu = df_wenhu.reindex(columns=FINAL_COLUMNS)
            df_wenhu.to_csv(output_path, mode='a', header=not os.path.exists(output_path), index=False)
            logger.info(f"    -> ✅ 成功處理並儲存 {len(df_wenhu)} 筆文湖線資料。")
    else:
        logger.error("    -> ❌ 從 API 獲取文湖線資料失敗。")


if __name__ == "__main__":
    # 確保 data 資料夾存在
    data_dir = os.path.join(project_root, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    while True:
        try:
            collect_and_save_data()
            logger.info("--- [Collector] 資料收集完成，等待 5 分鐘後下一次更新... ---\n")
            time.sleep(300)
        except Exception as e:
            logger.critical(f"--- ❌ Collector 主迴圈發生嚴重錯誤: {e} ---", exc_info=True)
            logger.info("--- [Collector] 將在 5 分鐘後重試... ---\n")
            time.sleep(300)