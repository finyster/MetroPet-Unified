# services/vector_search_service.py

import json
import faiss
from sentence_transformers import SentenceTransformer
import numpy as np
import config
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class VectorSearchService:
    def __init__(self):
        logger.info("--- [VectorSearch] 正在初始化向量搜尋服務... ---")
        self.is_ready = False
        self._load_model_and_index()

    def _load_model_and_index(self):
        """載入預訓練模型、FAISS 索引和站名列表。"""
        faiss_index_path = os.path.join(config.DATA_DIR, 'station_vector.index')
        names_path = os.path.join(config.DATA_DIR, 'station_names.json')

        if not os.path.exists(faiss_index_path) or not os.path.exists(names_path):
            logger.warning("--- ⚠️ [VectorSearch] 找不到索引檔案，向量搜尋功能將無法使用。 ---")
            logger.warning("請先執行 build_vector_index.py 來建立索引。")
            return
        
        try:
            logger.info("--- [VectorSearch] 正在載入語意模型... ---")
            self.model = SentenceTransformer('distiluse-base-multilingual-cased-v1')
            logger.info("--- [VectorSearch] 正在載入 FAISS 索引... ---")
            self.index = faiss.read_index(faiss_index_path)
            with open(names_path, 'r', encoding='utf-8') as f:
                self.station_names = json.load(f)
            self.is_ready = True
            logger.info("--- ✅ [VectorSearch] 向量搜尋服務已準備就緒。 ---")
        except Exception as e:
            logger.error(f"--- ❌ [VectorSearch] 載入模型或索引時發生錯誤: {e} ---", exc_info=True)

    def find_most_similar(self, query: str, top_k: int = 1) -> Optional[Tuple[str, float]]:
        """
        將查詢字串轉換為向量，並在 FAISS 索引中找到最相似的站名。
        
        Returns:
            一個元組 (最相似的站名, 相似度分數)，如果服務未就緒則返回 None。
        """
        if not self.is_ready:
            return None
        
        query_embedding = self.model.encode([query])
        query_embedding = np.array(query_embedding).astype('float32')

        # 進行搜尋，D 是距離，I 是索引
        distances, indices = self.index.search(query_embedding, top_k)
        
        if len(indices) > 0:
            # distances[0][0] 是 L2 距離，我們可將其轉換為 0-1 的相似度分數 (非線性)
            # 這裡用一個簡單的方式轉換，距離越小分數越高
            score = 1 / (1 + distances[0][0])
            best_match_index = indices[0][0]
            best_match_name = self.station_names[best_match_index]
            return (best_match_name, score)
        
        return None

# 建立單一實例供整個應用程式使用
vector_search_service = VectorSearchService()