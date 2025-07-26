import pandas as pd
import xgboost as xgb
import joblib
import os
import logging
import json
from typing import Dict, Any, Optional, Tuple

# --- 動態路徑設置 ---
# 這是為了確保無論如何執行，都能找到專案根目錄下的模組
import sys
# 獲取當前腳本 prediction_service.py 的絕對路徑
# os.path.abspath(__file__) -> D:\...\services\prediction_service.py
# os.path.dirname(...)      -> D:\...\services
# os.path.dirname(...)      -> D:\...\ (專案根目錄)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 現在可以安全地從根目錄匯入
from services.station_service import StationManager
import config # 假設 config.py 在根目錄

# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ... (您的 CongestionPredictor 類別定義維持不變) ...

class CongestionPredictor:
    def __init__(self, station_manager_instance: StationManager):
        logger.info("--- [Predictor] 正在初始化人流預測服務... ---")
        self.station_manager = station_manager_instance
        self.models: Dict[str, xgb.XGBRegressor] = {}
        self.encoders: Dict[str, any] = {}
        self.feature_columns: Dict[str, list] = {}
        self.is_ready = self._load_all_models()

        if self.is_ready:
            logger.info("--- ✅ 預測服務已成功載入模型並準備就緒。 ---")
        else:
            logger.error("--- ❌ 預測服務初始化失敗，部分模型或檔案缺失。 ---")

    def _load_all_models(self) -> bool:
        """載入所有線路類型的模型、編碼器和特徵列表。"""
        all_loaded = True
        for line_type in ['high_capacity', 'wenhu']:
            data_dir = os.path.join(project_root, 'data')
            model_path = os.path.join(data_dir, f'{line_type}_congestion_model.json')
            encoder_path = os.path.join(data_dir, f'{line_type}_encoder.joblib')
            features_path = os.path.join(data_dir, f'{line_type}_feature_columns.csv')
            
            if not all(os.path.exists(p) for p in [model_path, encoder_path, features_path]):
                logger.warning(f"--- ⚠️ 找不到 {line_type} 的模型檔案，請先運行 model_trainer.py。 ---")
                all_loaded = False
                continue
            
            self.models[line_type] = xgb.XGBRegressor()
            self.models[line_type].load_model(model_path)
            self.encoders[line_type] = joblib.load(encoder_path)
            self.feature_columns[line_type] = pd.read_csv(features_path)['feature'].tolist()
            logger.info(f"--- ✅ 已成功載入 {line_type} 模型。 ---")
        return all_loaded

    def _get_line_type_and_id(self, station_name: str) -> Optional[Tuple[str, str]]:
        """根據站名獲取線路類型和標準站點 ID。"""
        # 修正：呼叫正確的方法 get_station_ids，它會返回一個 ID 列表
        station_ids = self.station_manager.get_station_ids(station_name)
        
        # 如果找不到 ID 或列表為空，則記錄警告並返回
        if not station_ids:
            logger.warning(f"無法在 StationManager 中找到站名 '{station_name}' 的任何 ID。")
            return None, None
            
        # 策略：使用列表中的第一個 ID 來判斷路線類型和進行後續預測。
        # 對於轉乘站（如：南京復興 BR11, G16），取第一個 ID (BR11) 已足夠。
        station_id = station_ids[0]
        
        # 簡易判斷：文湖線 ID 以 'BR' 開頭
        if station_id.startswith('BR'):
            return 'wenhu', station_id
        return 'high_capacity', station_id

    def _create_prediction_features(self, station_id: str, line_direction_cid: int, line_type: str) -> pd.DataFrame:
        """
        【核心預測特徵創建】
        為單次預測創建與訓練時完全一致的特徵。
        注意：這裡的滯後特徵是簡化處理的，真實上線系統需要 feature store。
        """
        now = pd.Timestamp.now()
        
        # 模擬滯後特徵，這裡用 0 作為簡化
        # 在真實系統中，這裡應該從快取或資料庫中讀取最近的真實擁擠度
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
                'car_number': car_num,
                'lag_5min_congestion': lag_5min_congestion,
                'lag_1hr_congestion': lag_1hr_congestion
            })
        
        df_raw = pd.DataFrame(records)
        
        # 使用已載入的編碼器進行 OneHot 編碼
        encoder = self.encoders[line_type]
        categorical_features = ['station_id', 'line_direction_cid']
        encoded_data = encoder.transform(df_raw[categorical_features])
        encoded_df = pd.DataFrame(encoded_data, columns=encoder.get_feature_names_out(categorical_features))
        
        # 組合所有特徵
        numeric_features = ['hour', 'day_of_week', 'is_weekend', 'car_number', 'lag_5min_congestion', 'lag_1hr_congestion']
        final_df = pd.concat([df_raw[numeric_features].reset_index(drop=True), encoded_df], axis=1)
        
        # 確保特徵順序與訓練時完全一致
        final_df = final_df.reindex(columns=self.feature_columns[line_type], fill_value=0)
        
        return final_df

    def predict_for_station(self, station_name: str, direction: str) -> Dict[str, Any]:
        """
        【對外預測介面】
        接收使用者易於理解的站名和方向，返回預測結果。
        """
        if not self.is_ready:
            return {"error": "預測服務尚未準備就緒，請檢查模型檔案是否存在。"}

        line_type, station_id = self._get_line_type_and_id(station_name)
        if not line_type:
            return {"error": f"無法識別車站 '{station_name}'，請確認站名是否正確。"}
            
        # 將方向文字轉換為數字 ID (上行/下行)，這裡需要一個明確的映射規則
        # 假設: 上行=1, 下行=2。這需要根據 API 的實際定義調整。
        direction_map = {"上行": 1, "往南港展覽館": 1, "往動物園": 1, "下行": 2, "往頂埔": 2, "往象山": 2}
        line_direction_cid = direction_map.get(direction, 1) # 預設為1

        logger.info(f"開始為車站 '{station_name}' (ID: {station_id}, 方向: {line_direction_cid}) 進行預測...")
        
        try:
            X_pred = self._create_prediction_features(station_id, line_direction_cid, line_type)
            model = self.models[line_type]
            predictions = model.predict(X_pred)
            
            # 將結果格式化為友善的輸出
            congestion_map = {1: "舒適", 2: "正常", 3: "略多", 4: "擁擠", 5: "非常擁擠"}
            results = []
            for i, pred in enumerate(predictions):
                # 將預測值限制在 1-5 之間並取整
                level = max(1, min(5, round(float(pred))))
                results.append({
                    "car_number": i + 1,
                    "congestion_level": level,
                    "congestion_text": congestion_map.get(level, "未知")
                })

            return {
                "station_name": station_name,
                "direction": direction,
                "prediction_time": pd.Timestamp.now().isoformat(),
                "congestion_by_car": results,
                "message": f"預測「{station_name}」站往「{direction}」方向的列車，各車廂擁擠度如下。"
            }

        except Exception as e:
            logger.error(f"為 '{station_name}' 進行預測時發生錯誤: {e}", exc_info=True)
            return {"error": f"預測時發生內部錯誤，請檢查日誌。"}

# --- 如何在主應用中整合 ---
# 1. 在 services/__init__.py 的 ServiceRegistry 中:
#    from .prediction_service import CongestionPredictor
#    self.congestion_predictor = CongestionPredictor(station_manager_instance=self.station_manager)
#
# 2. 在 agent/function_tools.py 中建立工具:
#    @tool
#    def predict_congestion(station_name: str, direction: str) -> str:
#        """預測指定車站、指定方向的列車車廂擁擠程度。"""
#        predictor = service_registry_instance.get_congestion_predictor()
#        result = predictor.predict_for_station(station_name, direction)
#        return json.dumps(result, ensure_ascii=False)
# ==============================================================================
# --- 主程式執行區塊 ---
# ==============================================================================
if __name__ == "__main__":
    """
    這個區塊讓 prediction_service.py 可以被直接執行以進行測試。
    它會模擬建立依賴物件、初始化預測器，並呼叫預測功能。
    """
    logger.info("--- [主程式] 開始執行預測服務獨立測試 ---")
    
    # 1. 定義必要的檔案路徑 (相對於專案根目錄)
    #    project_root 已在檔案頂部定義
    station_info_path = os.path.join(project_root, 'data', 'mrt_station_info.json')

    logger.info(f"--- [主程式] 使用站點資料路徑: {station_info_path}")

    if not os.path.exists(station_info_path):
        logger.error(f"--- ❌ [主程式] 致命錯誤: 找不到站點資料檔案 '{station_info_path}'。")
    else:
        try:
            # 2. 建立 StationManager 的實例
            #    假設 StationManager 的 __init__ 需要 station_data_path
            station_manager = StationManager(station_data_path=station_info_path)
            logger.info("--- ✅ [主程式] StationManager 實例建立成功。 ---")

            # 3. 建立 CongestionPredictor 的實例
            predictor = CongestionPredictor(station_manager_instance=station_manager)
            
            # 4. 檢查預測器是否已準備就緒 (模型是否都載入成功)
            if predictor.is_ready:
                logger.info("--- ✅ [主程式] CongestionPredictor 實例建立成功並準備就緒。 ---")
                
                # 5. ✨✨✨ 執行預測！ ✨✨✨
                print("\n" + "="*60)
                print("                     🚇 MetroPet 即時預測範例 🚇")
                print("="*60 + "\n")
                
                # --- 測試案例 1: 高運量車站 (板南線) ---
                station_1 = "市政府"
                direction_1 = "往南港展覽館"
                logger.info(f"--- [預測 1] 正在預測 [{station_1}] 往 [{direction_1}] 方向...")
                prediction_1 = predictor.predict_for_station(station_1, direction_1)
                print(json.dumps(prediction_1, indent=2, ensure_ascii=False))

                print("\n" + "-"*60 + "\n")

                # --- 測試案例 2: 文湖線車站 ---
                station_2 = "南京復興"
                direction_2 = "往動物園"
                logger.info(f"--- [預測 2] 正在預測 [{station_2}] 往 [{direction_2}] 方向...")
                prediction_2 = predictor.predict_for_station(station_2, direction_2)
                print(json.dumps(prediction_2, indent=2, ensure_ascii=False))
                
                print("\n" + "="*60)
                logger.info("--- [主程式] 所有預測範例執行完畢。 ---")
            else:
                logger.error("--- ❌ [主程式] 預測器未準備就緒。請檢查 data 資料夾中的模型相關檔案。")

        except Exception as e:
            import traceback
            logger.error(f"--- ❌ [主程式] 執行過程中發生未預期錯誤: {e} ---")
            traceback.print_exc()