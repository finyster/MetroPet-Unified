# services/prediction_service.py

import pandas as pd
import xgboost as xgb
import joblib
import os
import logging
import json
from typing import Dict, Any, Optional, Tuple

# --- 路徑設置 ---
import sys
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')

if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from services.station_service import StationManager
from services.metro_soap_service import metro_soap_api # 確保匯入 metro_soap_api
import config

# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CongestionPredictor:
    def __init__(self, station_manager_instance: StationManager):
        logger.info("--- [Predictor] 正在初始化人流預測服務... ---")
        self.station_manager = station_manager_instance
        self.models: Dict[str, xgb.XGBClassifier] = {}
        self.encoders: Dict[str, any] = {}
        self.scalers: Dict[str, any] = {}
        self.feature_columns: Dict[str, list] = {}
        self.is_ready = self._load_all_models()

        if self.is_ready:
            logger.info("--- ✅ 預測服務已成功載入模型並準備就緒。 ---")
        else:
            logger.error("--- ❌ 預測服務初始化失敗，部分模型或檔案缺失。 ---")

    def _load_all_models(self) -> bool:
        all_loaded = True
        for line_type in ['high_capacity', 'wenhu']:
            model_path = os.path.join(MODEL_DIR, f'{line_type}_congestion_model.json')
            encoder_path = os.path.join(MODEL_DIR, f'{line_type}_encoder.joblib')
            scaler_path = os.path.join(MODEL_DIR, f'{line_type}_scaler.joblib')
            features_path = os.path.join(MODEL_DIR, f'{line_type}_feature_columns.csv')
            
            if not all(os.path.exists(p) for p in [model_path, encoder_path, scaler_path, features_path]):
                logger.warning(f"--- ⚠️ 在路徑 '{MODEL_DIR}' 中找不到 {line_type} 的模型檔案，請先運行 model_trainer.py。 ---")
                all_loaded = False
                continue
            
            try:
                self.models[line_type] = xgb.XGBClassifier()
                self.models[line_type].load_model(model_path)
                self.encoders[line_type] = joblib.load(encoder_path)
                self.scalers[line_type] = joblib.load(scaler_path)
                self.feature_columns[line_type] = pd.read_csv(features_path)['feature'].tolist()
                logger.info(f"--- ✅ 已成功從 '{MODEL_DIR}' 載入 {line_type} 模型。 ---")
            except Exception as e:
                logger.error(f"載入 {line_type} 模型時發生錯誤: {e}", exc_info=True)
                all_loaded = False
        return all_loaded

    def _get_line_type_and_id(self, station_name: str) -> Optional[Tuple[str, str]]:
        station_ids = self.station_manager.get_station_ids(station_name)
        if not station_ids:
            logger.warning(f"無法在 StationManager 中找到站名 '{station_name}' 的任何 ID。")
            return None, None
        station_id = station_ids[0]
        if station_id.startswith('BR'):
            return 'wenhu', station_id
        return 'high_capacity', station_id

    def _create_prediction_features(self, station_id: str, line_direction_cid: int, line_type: str) -> pd.DataFrame:
        now = pd.Timestamp.now() # 這裡仍然使用現在時間來創建特徵，因為是通用預測
        
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
                'minute': now.minute, # 新增 minute 特徵
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
        
        # 組合最終特徵
        numeric_features = [
            'hour', 'minute', 'day_of_week', 'is_weekend', 'is_peak_hour', 'is_transfer_station',
            'car_number', 'lag_5min_congestion', 'lag_1hr_congestion'
        ]
        
        final_df = pd.concat([df_raw[numeric_features].reset_index(drop=True), encoded_df.reset_index(drop=True)], axis=1)
        
        # 使用 scaler 進行標準化
        scaler = self.scalers[line_type]
        final_df[numeric_features] = scaler.transform(final_df[numeric_features])
        
        final_df = final_df.reindex(columns=self.feature_columns[line_type], fill_value=0)
        
        return final_df

    def predict_for_station(self, station_name: str, direction: str) -> Dict[str, Any]:
        """
        為指定車站和方向提供通用的車廂擁擠度預測。
        """
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
            predictions = model.predict(X_pred)
            
            congestion_map = {1: "舒適", 2: "正常", 3: "略多", 4: "擁擠"}
            results = []
            for i, pred_class in enumerate(predictions):
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

    def predict_next_train_congestion(self, station_name: str, direction: str) -> Dict[str, Any]:
        """
        結合即時列車資訊與擁擠度預測模型，為使用者提供即將到站列車的預測結果。
        此版本將返回所有匹配方向的列車資訊，並為用戶查詢的車站提供擁擠度預測。
        
        :param station_name: 使用者所在的車站名稱。
        :param direction: 使用者詢問的行駛方向或終點站。
        :return: 包含即將到站列車資訊與擁擠度預測結果的字典，如果失敗則包含錯誤訊息。
        """
        if not self.is_ready:
            return {"error": "預測服務尚未準備就緒，請檢查模型檔案是否存在。"}

        logger.info(f"--- 🚀 正在從 Metro API 獲取即時列車資訊以查找車站 '{station_name}' 往 '{direction}' 方向 ---")
        try:
            all_train_info = metro_soap_api.get_realtime_track_info()
        except Exception as e:
            logger.error(f"獲取即時列車資訊時發生錯誤: {e}", exc_info=True)
            return {"error": "無法從 Metro API 獲取即時列車資訊，請檢查服務連線。"}

        # 獲取針對使用者查詢車站的通用擁擠度預測
        congestion_prediction_for_station = self.predict_for_station(station_name, direction)

        if "error" in congestion_prediction_for_station:
            return {"error": congestion_prediction_for_station["error"]}

        # 過濾出所有開往指定方向的列車
        relevant_trains = []
        if all_train_info:
            for train in all_train_info:
                # 使用 'in' 進行彈性匹配，例如 '北車' 包含在 '台北車站'
                if direction in train.get('DestinationName', ''):
                    relevant_trains.append(train)

            # 根據 CountDown 進行排序，將即將抵達的列車排在前面
            def parse_countdown_to_seconds(countdown_str):
                if countdown_str == '列車進站':
                    return 0 # "列車進站" 優先
                if '分' in countdown_str and '秒' in countdown_str:
                    parts = countdown_str.replace(' 分鐘 ', ' ').replace(' 秒', '').split(' ')
                    if len(parts) == 2:
                        try:
                            minutes = int(parts[0])
                            seconds = int(parts[1])
                            return minutes * 60 + seconds
                        except ValueError:
                            return float('inf') # 無法解析則排在後面
                return float('inf') # 預設值，確保排序

            relevant_trains.sort(key=lambda x: parse_countdown_to_seconds(x.get('CountDown', '未知')))

        return {
            "station_name": station_name,
            "direction": direction,
            "prediction_time": pd.Timestamp.now().isoformat(),
            "relevant_trains_info": relevant_trains, # 返回所有相關列車的資訊
            "congestion_prediction_for_station": congestion_prediction_for_station # 通用擁擠度預測
        }