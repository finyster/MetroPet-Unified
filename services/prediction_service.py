# services/prediction_service.py

import pandas as pd
import xgboost as xgb
import joblib
import os
import logging
import json
from typing import Dict, Any, Optional, Tuple

# --- 路徑設置 (維持不變) ---
import sys
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')

if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from services.station_service import StationManager
import config

# --- 配置日誌 (維持不變) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CongestionPredictor:
    def __init__(self, station_manager_instance: StationManager):
        logger.info("--- [Predictor] 正在初始化人流預測服務... ---")
        self.station_manager = station_manager_instance
        self.models: Dict[str, xgb.XGBClassifier] = {} # <-- 模型現在是 XGBClassifier
        self.encoders: Dict[str, any] = {}
        self.feature_columns: Dict[str, list] = {}
        self.is_ready = self._load_all_models()

        if self.is_ready:
            logger.info("--- ✅ 預測服務已成功載入模型並準備就緒。 ---")
        else:
            logger.error("--- ❌ 預測服務初始化失敗，部分模型或檔案缺失。 ---")

    def _load_all_models(self) -> bool:
        # 這部分維持不變，它能正確載入新模型
        all_loaded = True
        for line_type in ['high_capacity', 'wenhu']:
            model_path = os.path.join(MODEL_DIR, f'{line_type}_congestion_model.json')
            encoder_path = os.path.join(MODEL_DIR, f'{line_type}_encoder.joblib')
            features_path = os.path.join(MODEL_DIR, f'{line_type}_feature_columns.csv')
            
            if not all(os.path.exists(p) for p in [model_path, encoder_path, features_path]):
                logger.warning(f"--- ⚠️ 在路徑 '{MODEL_DIR}' 中找不到 {line_type} 的模型檔案，請先運行 model_trainer.py。 ---")
                all_loaded = False
                continue
            
            try:
                self.models[line_type] = xgb.XGBClassifier() # <-- 確保載入的是分類器
                self.models[line_type].load_model(model_path)
                self.encoders[line_type] = joblib.load(encoder_path)
                self.feature_columns[line_type] = pd.read_csv(features_path)['feature'].tolist()
                logger.info(f"--- ✅ 已成功從 '{MODEL_DIR}' 載入 {line_type} 模型。 ---")
            except Exception as e:
                logger.error(f"載入 {line_type} 模型時發生錯誤: {e}", exc_info=True)
                all_loaded = False
        return all_loaded

    def _get_line_type_and_id(self, station_name: str) -> Optional[Tuple[str, str]]:
        # 維持不變
        station_ids = self.station_manager.get_station_ids(station_name)
        if not station_ids:
            logger.warning(f"無法在 StationManager 中找到站名 '{station_name}' 的任何 ID。")
            return None, None
        station_id = station_ids[0]
        if station_id.startswith('BR'):
            return 'wenhu', station_id
        return 'high_capacity', station_id

    def _create_prediction_features(self, station_id: str, line_direction_cid: int, line_type: str) -> pd.DataFrame:
        # 這部分的特徵創建邏輯與訓練時完全一致，維持不變
        now = pd.Timestamp.now()
        
        # 讀取 mrt_station_info.json 來判斷是否為轉乘站
        with open(os.path.join(DATA_DIR, 'mrt_station_info.json'), 'r', encoding='utf-8') as f:
            station_info = json.load(f)
        transfer_stations = {sid for info in station_info.values() if isinstance(info, dict) for sid in info.get('station_ids', []) if info.get('is_transfer')}
        
        # 在真實預測中，滯後特徵通常從快取或資料庫獲取，這裡我們簡化為 0
        lag_5min_congestion = 0.0
        lag_1hr_congestion = 0.0
        
        num_cars = 4 if line_type == 'wenhu' else 6
        records = []
        for car_num in range(1, num_cars + 1):
            records.append({
                'station_id': station_id,
                'line_direction_cid': str(line_direction_cid),
                'hour': now.hour,
                'day_of_week': now.dayofweek,
                'is_weekend': int(now.dayofweek >= 5),
                'is_peak_hour': int(now.hour in [7, 8, 17, 18, 19]),
                'is_transfer_station': int(station_id in transfer_stations),
                'car_number': car_num,
                'lag_5min_congestion': lag_5min_congestion,
                'lag_1hr_congestion': lag_1hr_congestion
            })
        
        df_raw = pd.DataFrame(records)
        
        encoder = self.encoders[line_type]
        categorical_features = ['station_id', 'line_direction_cid']
        encoded_data = encoder.transform(df_raw[categorical_features])
        encoded_df = pd.DataFrame(encoded_data, columns=encoder.get_feature_names_out(categorical_features))
        
        final_df = pd.concat([df_raw.drop(columns=categorical_features), encoded_df], axis=1)
        final_df = final_df.reindex(columns=self.feature_columns[line_type], fill_value=0)
        
        return final_df

    def predict_for_station(self, station_name: str, direction: str) -> Dict[str, Any]:
        if not self.is_ready:
            return {"error": "預測服務尚未準備就緒，請檢查模型檔案是否存在。"}

        line_type, station_id = self._get_line_type_and_id(station_name)
        if not line_type:
            return {"error": f"無法識別車站 '{station_name}'，請確認站名是否正確。"}
            
        direction_map = {"上行": 1, "往南港展覽館": 1, "往動物園": 1, "往迴龍": 1, "往蘆洲": 1, "往淡水":1, "往北投":1, "下行": 2, "往頂埔": 2, "往象山": 2, "往大安":2, "往南勢角":2, "往新店": 2, "往台電大樓":2, "往板橋":2}
        line_direction_cid = direction_map.get(direction, 1)

        logger.info(f"開始為車站 '{station_name}' (ID: {station_id}, 方向: {line_direction_cid}) 進行預測...")
        
        try:
            X_pred = self._create_prediction_features(station_id, line_direction_cid, line_type)
            model = self.models[line_type]
            predictions = model.predict(X_pred) # <-- 現在 predictions 會是 [0, 1, 2, 3]
            
            congestion_map = {1: "舒適", 2: "正常", 3: "略多", 4: "擁擠"}
            results = []
            for i, pred_class in enumerate(predictions):
                # --- 【 ✨✨✨ 核心修改 ✨✨✨ 】 ---
                # 1. 將模型輸出的類別 (0,1,2,3) 加 1，變回實際等級 (1,2,3,4)
                # 2. 不再需要 round() 或 min/max 限制
                level = int(pred_class) + 1
                
                results.append({
                    "car_number": i + 1,
                    "congestion_level": level,
                    "congestion_text": congestion_map.get(level, "未知")
                })

            return {
                "station_name": station_name,
                "direction": direction,
                "prediction_time": pd.Timestamp.now().isoformat(),
                "congestion_by_car": results
            }

        except Exception as e:
            logger.error(f"為 '{station_name}' 進行預測時發生錯誤: {e}", exc_info=True)
            return {"error": f"預測時發生內部錯誤，請檢查日誌。"}