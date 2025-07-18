import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error
import numpy as np
import joblib
import os
import logging
from typing import Tuple, List

# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 動態路徑設置 ---
import sys
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

def preprocess_for_training(filepath: str, line_type: str) -> Tuple[pd.DataFrame, List[str], OneHotEncoder]:
    """
    【核心特徵工程】
    從乾淨的 CSV 讀取資料，創建時間特徵、滯後特徵，並進行編碼。
    """
    logger.info(f"--- 開始預處理 {line_type} 資料從 {filepath} ---")
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"資料檔案不存在: {filepath}。請先執行 data_collector.py。")
    
    df = pd.read_csv(filepath)
    if df.empty:
        raise ValueError(f"{filepath} 為空，無法進行訓練。")

    # 1. 資料格式轉換 (Wide to Long)
    # 將每個車廂的擁擠度變成獨立的行，這樣模型就能學習「車廂位置」這個特徵
    num_cars = 4 if line_type == 'wenhu' else 6
    value_vars = [f'car{i}_congestion' for i in range(1, num_cars + 1)]
    id_vars = ['timestamp', 'station_id', 'line_direction_cid']
    
    # 確保所有必要的欄位都存在
    for col in id_vars + value_vars:
        if col not in df.columns:
            raise ValueError(f"CSV 檔案 {filepath} 缺少必要欄位: {col}")

    df_melted = df.melt(id_vars=id_vars, value_vars=value_vars, var_name='car_position', value_name='congestion')
    df_melted['car_number'] = df_melted['car_position'].str.extract(r'(\d+)').astype(int)
    
    # 清理掉擁擠度為空的記錄 (例如文湖線的 car5, car6)
    df_melted.dropna(subset=['congestion'], inplace=True)
    df_melted['congestion'] = pd.to_numeric(df_melted['congestion'], errors='coerce')
    df_melted.dropna(subset=['congestion'], inplace=True)

    # 2. 特徵工程
    df_melted['timestamp'] = pd.to_datetime(df_melted['timestamp'])
    df_melted['hour'] = df_melted['timestamp'].dt.hour
    df_melted['day_of_week'] = df_melted['timestamp'].dt.dayofweek
    df_melted['is_weekend'] = (df_melted['day_of_week'] >= 5).astype(int)
    
    # 滯後特徵 (Lag Features) - 這是預測時間序列的關鍵
    logger.info("    -> 正在創建滯後特徵...")
    df_melted = df_melted.sort_values(by=['station_id', 'line_direction_cid', 'car_number', 'timestamp'])
    # 上一個時間點的擁擠度 (5分鐘前)
    df_melted['lag_5min_congestion'] = df_melted.groupby(['station_id', 'line_direction_cid', 'car_number'])['congestion'].shift(1)
    # 一小時前的擁擠度 (假設5分鐘收集一次，12*5=60)
    df_melted['lag_1hr_congestion'] = df_melted.groupby(['station_id', 'line_direction_cid', 'car_number'])['congestion'].shift(12)
    
    # 【關鍵修正】用 0 填充滯後特徵的缺失值，而不是刪除整行
    df_melted.fillna({
        'lag_5min_congestion': 0,
        'lag_1hr_congestion': 0
    }, inplace=True)
    
    # 3. 類別特徵編碼 (One-Hot Encoding)
    categorical_features = ['station_id', 'line_direction_cid']
    df_melted[categorical_features] = df_melted[categorical_features].astype(str)
    
    encoder = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    encoded_data = encoder.fit_transform(df_melted[categorical_features])
    encoded_df = pd.DataFrame(encoded_data, columns=encoder.get_feature_names_out(categorical_features), index=df_melted.index)
    
    # 4. 組合最終特徵
    numeric_features = ['hour', 'day_of_week', 'is_weekend', 'car_number', 'lag_5min_congestion', 'lag_1hr_congestion']
    final_df = pd.concat([df_melted[numeric_features], encoded_df, df_melted['congestion']], axis=1)
    feature_columns = numeric_features + list(encoder.get_feature_names_out(categorical_features))
    
    logger.info(f"--- 預處理完成，共生成 {len(final_df)} 筆有效訓練樣本。")
    return final_df, feature_columns, encoder

def train_and_save_model(df: pd.DataFrame, feature_columns: list, line_type: str, encoder: OneHotEncoder):
    """訓練 XGBoost 模型並保存所有必要的產物。"""
    logger.info(f"--- 開始訓練 {line_type} 模型... ---")
    
    X = df[feature_columns]
    y = df['congestion']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=7,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        early_stopping_rounds=50, # 提前停止以防過擬合
        n_jobs=-1 # 使用所有 CPU 核心
    )
    
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)  # 首先計算 MSE
    rmse = np.sqrt(mse)                      # 再對 MSE 開根號得到 RMSE
    # 【新增這行】計算 MAPE
    mape = mean_absolute_percentage_error(y_test, y_pred)
    logger.info(f"--- ✅ {line_type} 模型訓練完成，評估 RMSE: {rmse:.4f}, MAPE: {mape:.4f} ---")
    
    # 5. 保存所有產物 (模型、編碼器、特徵列表)
    data_dir = os.path.join(project_root, 'data')
    model.save_model(os.path.join(data_dir, f'{line_type}_congestion_model.json'))
    joblib.dump(encoder, os.path.join(data_dir, f'{line_type}_encoder.joblib'))
    pd.DataFrame(feature_columns, columns=['feature']).to_csv(os.path.join(data_dir, f'{line_type}_feature_columns.csv'), index=False)
    
    logger.info(f"    -> 模型已保存至: {line_type}_congestion_model.json")
    logger.info(f"    -> 編碼器已保存至: {line_type}_encoder.joblib")
    logger.info(f"    -> 特徵列表已保存至: {line_type}_feature_columns.csv")

if __name__ == "__main__":
    # 對高運量線和文湖線分別進行訓練
    for line_type in ['high_capacity', 'wenhu']:
        filepath = os.path.join(project_root, 'data', f'{line_type}_congestion.csv')
        try:
            processed_df, features, fitted_encoder = preprocess_for_training(filepath, line_type)
            train_and_save_model(processed_df, features, line_type, fitted_encoder)
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"--- ❌ {line_type} 訓練失敗: {e} ---")
            logger.error("請確保已運行 data_collector.py 並收集到足夠的資料。")
        except Exception as e:
            logger.critical(f"--- ❌ {line_type} 訓練過程中發生未知嚴重錯誤: {e} ---", exc_info=True)
    
    logger.info("\n--- 🎉 所有模型訓練流程結束！ ---")