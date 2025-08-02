# build_lost_item_index.py
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import config
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_lost_item_index():
    logger.info("--- 🚀 開始建立【遺失物名稱】向量索引 ---")

    with open(config.LOST_AND_FOUND_DATA_PATH, 'r', encoding='utf-8') as f:
        lost_items_data = json.load(f)

    # 只取出所有不重複的物品名稱來建立索引
    item_names = sorted(list(set(item['col_LoseName'] for item in lost_items_data)))

    logger.info(f"✅ 成功載入 {len(item_names)} 個不重複的遺失物名稱。")

    logger.info("⏳ 正在載入語意模型...")
    model = SentenceTransformer('distiluse-base-multilingual-cased-v1')
    logger.info("✅ 語意模型載入成功。")

    logger.info("⏳ 正在將所有物品名稱編碼為向量...")
    item_embeddings = model.encode(item_names, convert_to_tensor=False, show_progress_bar=True)
    item_embeddings = np.array(item_embeddings).astype('float32')

    embedding_dimension = item_embeddings.shape[1]
    index = faiss.IndexFlatL2(embedding_dimension)
    index.add(item_embeddings)

    faiss_index_path = os.path.join(config.DATA_DIR, 'lost_item_vector.index')
    names_path = os.path.join(config.DATA_DIR, 'lost_item_names.json')

    faiss.write_index(index, faiss_index_path)
    with open(names_path, 'w', encoding='utf-8') as f:
        json.dump(item_names, f, ensure_ascii=False, indent=2)

    logger.info(f"--- 🎉 成功！遺失物向量索引已儲存。 ---")

if __name__ == "__main__":
    build_lost_item_index()