# model/model_trainer.py (專業分類模型升級版)

import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import accuracy_score, classification_report # 匯入分類模型的評估工具
import numpy as np
import joblib
import os
import logging
from typing import Tuple, List
import json

# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 路徑設置 ---
MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(MODEL_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')

import sys
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

def preprocess_for_training(filepath: str, line_type: str) -> Tuple[pd.DataFrame, List[str], OneHotEncoder]:
    """
    【✨核心特徵工程升級 2.0✨】
    從原始 CSV 讀取資料，創建更豐富的時間與空間特徵，並為分類任務做準備。
    """
    logger.info(f"--- 開始預處理 {line_type} 資料從 {filepath} ---")
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"資料檔案不存在: {filepath}。請先執行 data_collector.py。")
    
    df = pd.read_csv(filepath)
    if df.empty:
        raise ValueError(f"{filepath} 為空，無法進行訓練。")

    # 1. 資料格式轉換 (Wide to Long) - 維持不變
    num_cars = 4 if line_type == 'wenhu' else 6
    value_vars = [f'car{i}_congestion' for i in range(1, num_cars + 1)]
    id_vars = ['timestamp', 'station_id', 'line_direction_cid']
    
    df_melted = df.melt(id_vars=id_vars, value_vars=value_vars, var_name='car_position', value_name='congestion')
    df_melted['car_number'] = df_melted['car_position'].str.extract(r'(\d+)').astype(int)
    
    # 清理目標變數：確保擁擠度是 1, 2, 3, 4 其中之一
    df_melted['congestion'] = pd.to_numeric(df_melted['congestion'], errors='coerce')
    df_melted.dropna(subset=['congestion'], inplace=True)
    df_melted = df_melted[df_melted['congestion'].isin([1, 2, 3, 4])].astype({'congestion': int})

    # --- 【 ✨ 特徵工程 2.0 - 導入專家知識 ✨ 】 ---
    logger.info("      -> 正在創建 2.0 版特徵...")
    df_melted['timestamp'] = pd.to_datetime(df_melted['timestamp'])
    
    # (A) 更豐富的時間特徵
    df_melted['hour'] = df_melted['timestamp'].dt.hour
    df_melted['day_of_week'] = df_melted['timestamp'].dt.dayofweek
    df_melted['is_weekend'] = (df_melted['day_of_week'] >= 5).astype(int)
    # 新增：是否為尖峰時段 (早上 7-9 點, 傍晚 17-19 點)，這是影響人流的關鍵因子
    df_melted['is_peak_hour'] = df_melted['hour'].isin([7, 8, 17, 18, 19]).astype(int)

    # (B) 結合捷運路網的空間特徵 (Domain Knowledge)
    with open(os.path.join(DATA_DIR, 'mrt_station_info.json'), 'r', encoding='utf-8') as f:
        station_info = json.load(f)
    
    # 最終修正：遍歷字典的 .values()，並用 isinstance 檢查確保健壯性
    transfer_stations = {sid for info in station_info.values() if isinstance(info, dict) for sid in info.get('station_ids', []) if info.get('is_transfer')}
    df_melted['is_transfer_station'] = df_melted['station_id'].isin(transfer_stations).astype(int)
    
    # (C) 滯後特徵 (維持不變，但未來可強化)
    df_melted = df_melted.sort_values(by=['station_id', 'line_direction_cid', 'car_number', 'timestamp'])
    df_melted['lag_5min_congestion'] = df_melted.groupby(['station_id', 'line_direction_cid', 'car_number'])['congestion'].shift(1)
    df_melted['lag_1hr_congestion'] = df_melted.groupby(['station_id', 'line_direction_cid', 'car_number'])['congestion'].shift(12)
    df_melted.fillna(0, inplace=True)
    
    # 3. 類別特徵編碼 - 維持不變
    categorical_features = ['station_id', 'line_direction_cid']
    df_melted[categorical_features] = df_melted[categorical_features].astype(str)
    
    encoder = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    encoded_data = encoder.fit_transform(df_melted[categorical_features])
    encoded_df = pd.DataFrame(encoded_data, columns=encoder.get_feature_names_out(categorical_features), index=df_melted.index)
    
    # 4. 組合最終特徵
    numeric_features = [
        'hour', 'day_of_week', 'is_weekend', 'is_peak_hour', 'is_transfer_station',
        'car_number', 'lag_5min_congestion', 'lag_1hr_congestion'
    ]
    final_df = pd.concat([df_melted[numeric_features].reset_index(drop=True), encoded_df.reset_index(drop=True), df_melted['congestion'].reset_index(drop=True)], axis=1)
    feature_columns = numeric_features + list(encoder.get_feature_names_out(categorical_features))
    
    logger.info(f"--- 預處理完成，共生成 {len(final_df)} 筆有效訓練樣本，使用 {len(feature_columns)} 個特徵。")
    return final_df, feature_columns, encoder

def train_and_save_model(df: pd.DataFrame, feature_columns: list, line_type: str, encoder: OneHotEncoder):
    """
    【✨模型訓練升級✨】
    使用 XGBoost 分類器，並評估分類模型的效能指標。
    """
    logger.info(f"--- 開始訓練 {line_type} 分類模型... ---")
    
    X = df[feature_columns]
    
    # --- 【 ✨ 核心修改：目標變數轉換為 0-indexed ✨ 】 ---
    # 原始標籤是 1, 2, 3, 4。XGBoost 分類器需要從 0 開始的標籤。
    # 所以我們將所有標籤減 1，變成 0, 1, 2, 3。
    y = df['congestion'] - 1
    
    # 使用 stratify=y 確保訓練集和測試集中的各類別比例與原始數據相同
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # --- 【 ✨ 核心修改：更換為 XGBClassifier 分類模型 ✨ 】 ---
    model = xgb.XGBClassifier(
        objective='multi:softmax',  # 目標函數改為多分類
        num_class=4,                # 告知模型總共有 4 個類別 (0, 1, 2, 3)
        n_estimators=500,           # 減少樹的數量，用 early_stopping 來找最佳點
        learning_rate=0.1,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        early_stopping_rounds=30,   # 設定早停機制，防止過擬合，提升訓練效率
        n_jobs=-1,
        eval_metric='mlogloss'      # 設定評估指標
    )
    
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    y_pred = model.predict(X_test)
    
    # --- 【 ✨ 核心修改：使用分類評估指標，告別 MAPE ✨ 】 ---
    accuracy = accuracy_score(y_test, y_pred)
    logger.info(f"--- ✅ {line_type} 模型訓練完成，評估 Accuracy (準確率): {accuracy:.4f} ---")
    
    # 打印更詳細的分類報告 (Precision, Recall, F1-score)，這能告訴我們模型對每個擁擠等級的預測能力
    report = classification_report(y_test, y_pred, target_names=['舒適(1)', '正常(2)', '略多(3)', '擁擠(4)'])
    logger.info(f"\n--- 分類報告 ({line_type}) ---\n{report}")
    
    # 儲存產物 - 維持不變
    output_dir = MODEL_DIR 
    model.save_model(os.path.join(output_dir, f'{line_type}_congestion_model.json'))
    joblib.dump(encoder, os.path.join(output_dir, f'{line_type}_encoder.joblib'))
    pd.DataFrame(feature_columns, columns=['feature']).to_csv(os.path.join(output_dir, f'{line_type}_feature_columns.csv'), index=False)
    
    logger.info(f"      -> 模型相關產物已保存至: {output_dir}")

if __name__ == "__main__":
    logger.warning("--- 準備開始新一輪的『分類模型』訓練，建議先手動刪除 model/ 資料夾中舊的模型檔案！ ---")
    
    for line_type in ['high_capacity', 'wenhu']:
        filepath = os.path.join(DATA_DIR, f'{line_type}_congestion.csv')
        try:
            processed_df, features, fitted_encoder = preprocess_for_training(filepath, line_type)
            train_and_save_model(processed_df, features, line_type, fitted_encoder)
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"--- ❌ {line_type} 訓練失敗: {e} ---")
            logger.error("請確保已運行 data_collector.py 並收集到足夠的資料。")
        except Exception as e:
            logger.critical(f"--- ❌ {line_type} 訓練過程中發生未知嚴重錯誤: {e} ---", exc_info=True)
    
    logger.info("\n--- 🎉 所有模型訓練流程結束！ ---")
