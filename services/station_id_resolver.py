# services/station_id_resolver.py
import json, os, re
from typing import Optional, Dict

# 為了讓此服務也能讀取到主要的站點資料，我們需要 config
import config

class StationIdResolver:
    def __init__(self, mapping_path: str, main_station_info_path: str):
        self.mapping_path = mapping_path
        self.main_station_info_path = main_station_info_path
        
        # _norm_to_sid: 儲存從標準化名稱到【純數字 SID】的映射
        self._norm_to_sid: Dict[str, str] = {}
        # _alias_to_norm: 儲存從【別名】到【標準化官方中文名】的映射
        self._alias_to_norm: Dict[str, str] = {}
        
        self._load()

    def _load(self) -> None:
        """
        【全新升級版載入邏輯】
        同時載入主要的站點資訊 (mrt_station_info.json) 和 SID 映射表 (stations_sid_map.json)，
        建立一個強大的、能處理別名的解析器。
        """
        # 1. 載入主要的站點資訊，建立別名 -> 官方中文名的映射
        if os.path.exists(self.main_station_info_path):
            with open(self.main_station_info_path, "r", encoding="utf-8") as f:
                station_info = json.load(f)
                # station_info 的鍵是已經標準化過的各種名稱 (中/英/別名)
                # 我們需要找到每個 ID 對應的「官方中文名」
                # 為此，我們先建立一個 ID -> 官方中文名的反向映射
                id_to_official_name = {}
                for name, ids in station_info.items():
                    # 假設沒有數字和英文的鍵是官方中文名
                    if not re.search(r'[a-zA-Z0-9]', name):
                        for station_id in ids:
                            if station_id not in id_to_official_name:
                                id_to_official_name[station_id] = name
                
                # 現在我們可以建立 別名 -> 官方中文名 的映射了
                for alias, ids in station_info.items():
                    if ids and ids[0] in id_to_official_name:
                        self._alias_to_norm[alias] = id_to_official_name[ids[0]]
        
        # 2. 載入 SID 映射表，並用【標準化官方中文名】當作 key
        if os.path.exists(self.mapping_path):
            with open(self.mapping_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for row in raw:
                sid = row.get("SID")
                zh_name = row.get("SCNAME")
                if sid and zh_name:
                    # 使用標準化後的官方中文名作為主要鍵
                    norm_zh_name = self._normalize_name(zh_name)
                    self._norm_to_sid[norm_zh_name] = sid
        
        print(f"[StationIdResolver] 新版解析器已載入，共 {len(self._norm_to_sid)} 筆 SID 映射，{len(self._alias_to_norm)} 筆別名。")

    def _normalize_name(self, name: str) -> str:
        """一個統一的內部名稱標準化工具。"""
        if not isinstance(name, str): return ""
        name = name.lower().strip().replace("臺", "台")
        name = re.sub(r"[\(（].*?[\)）]", "", name).strip()
        if name.endswith("站"): name = name[:-1]
        return name

    # ---- 外部介面 ----
    def get_sid(self, name: str) -> Optional[str]:
        """
        【全新升級版 SID 獲取邏輯】
        1. 標準化使用者輸入。
        2. 嘗試從別名映射中找到官方名稱。
        3. 使用官方名稱去查詢 SID。
        """
        norm_input = self._normalize_name(name)
        
        # 從別名映射中找到標準官方名
        official_name = self._alias_to_norm.get(norm_input, norm_input)
        
        # 使用官方名查詢 SID
        return self._norm_to_sid.get(official_name)

# --- 在 services/__init__.py 中，我們需要修改 ServiceRegistry 的初始化 ---
# 確保在建立 StationIdResolver 時傳入兩個檔案路徑