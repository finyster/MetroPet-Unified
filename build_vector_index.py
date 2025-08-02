# build_vector_index.py

import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import config
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_and_save_index():
    """
    讀取所有標準化後的站名，使用 SentenceTransformer 將其編碼為向量，
    然後建立一個 FAISS 索引並將其與站名列表一起保存。
    """
    logger.info("--- 🚀 開始建立向量搜尋索引 ---")

    # 1. 載入 station_manager 已處理好的站點資料
    if not os.path.exists(config.STATION_DATA_PATH):
        logger.error(f"❌ 站點資料檔案不存在: {config.STATION_DATA_PATH}")
        logger.error("請先執行 build_database.py 來生成站點資料。")
        return

    with open(config.STATION_DATA_PATH, 'r', encoding='utf-8') as f:
        station_map = json.load(f)
    
    # 我們只需要 station_map 中的「鍵」(也就是所有標準化後的站名、英文名、別名)
    station_names = list(station_map.keys())
    if not station_names:
        logger.error("❌ 站點資料中沒有可供索引的站名。")
        return
    
    logger.info(f"✅ 成功載入 {len(station_names)} 個站名/別名。")

    # 2. 載入預訓練的語意模型
    #    'distiluse-base-multilingual-cased-v1' 是一個支援多語言的優秀模型
    logger.info("⏳ 正在載入語意模型 (第一次執行會需要較長時間)...")
    model = SentenceTransformer('distiluse-base-multilingual-cased-v1')
    logger.info("✅ 語意模型載入成功。")

    # 3. 將所有站名轉換為向量
    logger.info("⏳ 正在將所有站名編碼為向量...")
    station_embeddings = model.encode(station_names, convert_to_tensor=False, show_progress_bar=True)
    
    # 確保資料格式為 float32，這是 FAISS 的要求
    station_embeddings = np.array(station_embeddings).astype('float32')
    logger.info(f"✅ 向量編碼完成，向量維度: {station_embeddings.shape}")

    # 4. 建立 FAISS 索引
    embedding_dimension = station_embeddings.shape[1]
    index = faiss.IndexFlatL2(embedding_dimension) # 使用 L2 距離作為相似度度量
    index.add(station_embeddings)
    logger.info(f"✅ FAISS 索引建立完成，共索引 {index.ntotal} 個向量。")

    # 5. 儲存索引和對應的站名列表
    #    我們需要同時儲存索引和站名列表，才能在搜尋後知道找到的是哪個站名
    faiss_index_path = os.path.join(config.DATA_DIR, 'station_vector.index')
    names_path = os.path.join(config.DATA_DIR, 'station_names.json')

    faiss.write_index(index, faiss_index_path)
    with open(names_path, 'w', encoding='utf-8') as f:
        json.dump(station_names, f, ensure_ascii=False, indent=2)

    logger.info(f"--- 🎉 成功！向量索引已儲存至 {faiss_index_path} ---")
    logger.info(f"--- 🎉 成功！站名列表已儲存至 {names_path} ---")

if __name__ == "__main__":
    build_and_save_index()