# services/station_id_resolver.py
import json, os, re
from typing import Optional, Dict, List

class StationIdResolver:
    def __init__(self, mapping_path: str):
        self.mapping_path = mapping_path
        self._name2sid: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.mapping_path):
            raise FileNotFoundError(f"{self.mapping_path} 不存在，請確認檔案已放置。")
        with open(self.mapping_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for row in raw:
            sid = row["SID"]
            zh  = row["SCNAME"]
            en  = row["SCODE"]        # 若你想支援英文代碼
            self._register(zh, sid)
            self._register(en, sid)
            # 額外別名可在這裡統一加：北車→台北車站⋯
        print(f"[StationIdResolver] Loaded {len(self._name2sid)} keys.")

    # ---- 內部工具 --------------------------------------------------------
    _RE_NORMALIZE = re.compile(r"[ \-_/]+")
    def _norm(self, name: str) -> str:
        return self._RE_NORMALIZE.sub("", name).lower()

    def _register(self, name: str, sid: str):
        if name:
            self._name2sid[self._norm(name)] = sid

    # ---- 外部介面 --------------------------------------------------------
    def get_sid(self, name: str) -> Optional[str]:
        return self._name2sid.get(self._norm(name))
