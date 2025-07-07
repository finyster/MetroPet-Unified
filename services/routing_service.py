# services/routing_service.py
import json
import os
import networkx as nx
import config
import re 
from .station_service import station_manager
from .tdx_service import tdx_api # <-- 【關鍵修正】就是忘了這一行！

class RoutingManager:
    def __init__(self):
        print("--- [Routing Service] 正在初始化並建立捷運路網圖... ---")
        self.station_id_to_name = self._load_station_id_map()
        self.graph = self._build_metro_graph()

    def _load_station_id_map(self) -> dict:
        """從 station_manager 建立 ID -> 名稱的對照表"""
        id_to_name = {}
        for name, ids in station_manager.station_map.items():
            # 我們只用中文名來建立反向地圖
            if not re.search('[a-zA-Z]', name):
                for station_id in ids:
                    id_to_name[station_id] = name
        return id_to_name

    def _build_metro_graph(self) -> nx.Graph:
        """從 TDX API 獲取原始資料，並建立捷運路網圖"""
        G = nx.Graph()
        
        # 建立路網圖需要最原始的路線資料
        all_stations_raw_data = tdx_api.get_all_stations_of_route()
        if not all_stations_raw_data:
            print("--- ❌ [Routing] 無法建立路網圖：從 TDX 獲取車站資料失敗。 ---")
            print("--- 請先確認 `python build_database.py` 是否能成功執行。 ---")
            return G

        # 1. 加入所有車站節點
        for station_id, station_name in self.station_id_to_name.items():
            G.add_node(station_id, name=station_name)

        # 2. 加入相鄰車站之間的邊
        for route in all_stations_raw_data:
            stations_in_route = route.get("Stations", [])
            for i in range(len(stations_in_route) - 1):
                u = stations_in_route[i]['StationID']
                v = stations_in_route[i+1]['StationID']
                G.add_edge(u, v, weight=3) # 假設站間固定權重

        print("--- ✅ [Routing] 捷運路網圖建立完成！ ---")
        return G

    def find_shortest_path(self, start_name: str, end_name: str):
        """使用 Dijkstra 演算法尋找最短路徑"""
        start_id = station_manager.get_station_id(start_name)
        end_id = station_manager.get_station_id(end_name)

        if not start_id:
            return {"error": f"找不到起點站「{start_name}」"}
        if not end_id:
            return {"error": f"找不到終點站「{end_name}」"}

        try:
            # 尋找最短路徑（基於權重）
            path_ids = nx.shortest_path(self.graph, source=start_id, target=end_id, weight='weight')
            path_names = [self.station_id_to_name.get(node_id, "未知站") for node_id in path_ids]
            
            return {
                "start_station": start_name,
                "end_station": end_name,
                "path": path_names,
                "stops": len(path_names) - 1
            }
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return {"error": "在路網圖中找不到從起點到終點的路徑。"}

# 建立 RoutingManager 的單一實例
routing_manager = RoutingManager()