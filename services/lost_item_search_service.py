# services/lost_item_search_service.py

import json
import faiss
from sentence_transformers import SentenceTransformer
import numpy as np
import config
import os
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

class LostItemSearchService:
    def __init__(self):
        logger.info("--- [LostItemSearch] 正在初始化遺失物名稱向量搜尋服務... ---")
        self.is_ready = False
        self.model = None
        self.index = None
        self.item_names = []
        self._load_model_and_index()

    def _load_model_and_index(self):
        """載入預訓練模型、遺失物名稱的 FAISS 索引和名稱列表。"""
        faiss_index_path = os.path.join(config.DATA_DIR, 'lost_item_vector.index')
        names_path = os.path.join(config.DATA_DIR, 'lost_item_names.json')

        if not os.path.exists(faiss_index_path) or not os.path.exists(names_path):
            logger.warning("--- ⚠️ [LostItemSearch] 找不到遺失物索引檔案，向量搜尋功能將無法使用。 ---")
            logger.warning("請先執行 build_lost_item_index.py 來建立索引。")
            return
        
        try:
            logger.info("--- [LostItemSearch] 正在載入語意模型 (此過程可能需要一些時間)... ---")
            self.model = SentenceTransformer('distiluse-base-multilingual-cased-v1')
            logger.info("--- [LostItemSearch] 正在載入 FAISS 索引... ---")
            self.index = faiss.read_index(faiss_index_path)
            with open(names_path, 'r', encoding='utf-8') as f:
                self.item_names = json.load(f)
            
            if self.index.ntotal != len(self.item_names):
                logger.error("--- ❌ [LostItemSearch] 索引數量與名稱列表數量不匹配！請重新建立索引。 ---")
                return

            self.is_ready = True
            logger.info("--- ✅ [LostItemSearch] 遺失物向量搜尋服務已準備就緒。 ---")
        except Exception as e:
            logger.error(f"--- ❌ [LostItemSearch] 載入模型或索引時發生錯誤: {e} ---", exc_info=True)

    def find_similar_items(self, query: str, top_k: int = 5, threshold: float = 0.5) -> List[str]:
        """
        將查詢字串轉換為向量，並在 FAISS 索引中找到所有相似度高於門檻的物品名稱。
        
        Returns:
            一個包含所有相似物品名稱的列表。
        """
        if not self.is_ready or not query:
            return []
        
        try:
            query_embedding = self.model.encode([query])
            query_embedding = np.array(query_embedding).astype('float32')

            # 進行搜尋，D 是距離平方(L2 distance squared)，I 是索引
            distances, indices = self.index.search(query_embedding, top_k)
            
            similar_names = []
            if len(indices) > 0:
                for i in range(len(indices[0])):
                    dist = distances[0][i]
                    # 將 L2 距離轉換為一個 0-1 之間的相似度分數 (非線性)
                    # 這個轉換公式可以根據經驗調整，但 1 / (1 + dist) 是一個常用且效果不錯的起點
                    score = 1 / (1 + dist)
                    
                    if score >= threshold:
                        best_match_index = indices[0][i]
                        if 0 <= best_match_index < len(self.item_names):
                            similar_names.append(self.item_names[best_match_index])
            
            logger.info(f"對於查詢 '{query}'，找到 {len(similar_names)} 個相似物品: {similar_names}")
            return similar_names
        
        except Exception as e:
            logger.error(f"--- ❌ [LostItemSearch] 在搜尋相似物品時發生錯誤: {e} ---", exc_info=True)
            return []

# 建立單一實例供整個應用程式使用
lost_item_search_service = LostItemSearchService()