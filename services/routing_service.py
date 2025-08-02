# services/routing_service.py 

import json
import networkx as nx
import config
import re
from services.tdx_service import tdx_api
from utils.station_name_normalizer import normalize_station_name
from utils.exceptions import StationNotFoundError, RouteNotFoundError
import logging

logger = logging.getLogger(__name__)

class RoutingManager:
    def __init__(self, station_manager_instance): 
        logger.info("--- [Routing Service] 正在初始化並建立智慧捷運路網圖... ---")
        
        self.station_manager = station_manager_instance 

        # 【✨核心修正✨】在建立ID對照表時，傳入 station_manager 已載入的 station_map
        self.station_id_to_name = self._load_station_id_map(self.station_manager.station_map)
        self.graph = self._build_metro_graph()
        self.is_graph_ready = (self.graph is not None and self.graph.number_of_nodes() > 0)
        
        if self.is_graph_ready:
            logger.info("--- ✅ [Routing Service] 路網圖已成功初始化並準備就緒。 ---")
        else:
            logger.error("--- ❌ [Routing Service] 路網圖初始化失敗或為空。 ---")

    def _load_station_id_map(self, station_map: dict) -> dict:
        """
        【✨核心修正✨】
        從 station_map 建立一個絕對準確的「ID -> 官方中文站名」的對照表。
        """
        id_to_name = {}
        # 為了找到最「正統」的中文名（不含別名、英文名），我們進行篩選
        
        # 遍歷所有名稱，只挑選出不含英文和數字的，作為我們的「官方中文名」候選
        for name, ids in station_map.items():
            if not re.search('[a-zA-Z0-9]', name):
                for station_id in ids:
                    # 只有當這個 ID 還沒有被賦值時，才賦予它官方中文名
                    # 這避免了後續的別名（如果別名剛好也是中文）覆蓋掉真正的官方名稱
                    if station_id not in id_to_name:
                        id_to_name[station_id] = name
                        
        logger.info(f"--- ✅ [Routing] ID->站名對照表建立完成，共 {len(id_to_name)} 筆。")
        return id_to_name

    def _get_line_name_and_code(self, line_id_prefix: str) -> tuple[str, str]:
        """根據路線ID前綴獲取中文路線名稱和路線代碼。"""
        line_map = {
            'BL': ('板南線', '藍'), 'BR': ('文湖線', '棕'), 'R': ('淡水信義線', '紅'),
            'G': ('松山新店線', '綠'), 'O': ('中和新蘆線', '橘'), 'Y': ('環狀線', '黃')
        }
        # 如果找不到對應的路線，直接返回路線ID本身，避免顯示「未知路線」
        return line_map.get(line_id_prefix, (line_id_prefix, '未知'))

    def _build_metro_graph(self) -> nx.Graph:
        """
        從 TDX API 的 StationOfRoute 資料，建立一個帶有權重（時間）的捷運路網圖。
        """
        G = nx.Graph()
        
        all_routes_data = tdx_api.get_all_stations_of_route() 
        if not all_routes_data:
            logger.error("--- ❌ [Routing] 無法從 TDX 獲取所有路線的站點資料，路網圖建立失敗。 ---")
            return G
        
        # 建立節點 (Nodes)
        for route_info in all_routes_data:
            for station in route_info.get("Stations", []):
                station_id = station.get('StationID')
                # 使用我們清洗過的 station_id_to_name 來命名節點
                if station_id and station_id not in G: 
                    G.add_node(station_id, name=self.station_id_to_name.get(station_id, station_id))
        
        # 建立路線連線 (Ride Edges)
        for route_info in all_routes_data:
            line_id_prefix = route_info.get('RouteID', '') 
            line_name, _ = self._get_line_name_and_code(line_id_prefix)
            stations_on_this_route = route_info.get("Stations", [])
            for i in range(len(stations_on_this_route) - 1):
                u_id = stations_on_this_route[i]['StationID']
                v_id = stations_on_this_route[i+1]['StationID']
                if G.has_node(u_id) and G.has_node(v_id) and not G.has_edge(u_id, v_id): 
                    G.add_edge(u_id, v_id, weight=3, type='ride', line_name=line_name)

        # 建立轉乘連線 (Transfer Edges)
        try:
            with open(config.TRANSFER_DATA_PATH, 'r', encoding='utf-8') as f:
                transfer_data = json.load(f)
            for transfer in transfer_data:
                u, v = transfer['FromStationID'], transfer['ToStationID']
                transfer_time = 5 
                if G.has_node(u) and G.has_node(v):
                    if not G.has_edge(u, v) or G.get_edge_data(u, v)['weight'] > transfer_time:
                        G.add_edge(u, v, weight=transfer_time, type='transfer')
        except Exception as e:
            logger.warning(f"--- ⚠️ [Routing] 處理轉乘資訊時發生錯誤: {e} ---")

        logger.info(f"--- ✅ [Routing] 智慧捷運路網圖建立完成！共 {G.number_of_nodes()} 個站點，{G.number_of_edges()} 條連線。 ---")
        return G

    def find_shortest_path(self, start_station_name: str, end_station_name: str) -> dict:
        """
        【強化版】尋找兩個站點之間的最短路徑，並提供詳細、準確的路線指引。
        """
        if not self.is_graph_ready:
            logger.error("--- 錯誤: 路網圖尚未準備就緒，無法執行路徑規劃。 ---")
            raise RouteNotFoundError("抱歉，路網圖尚未準備好，無法為您規劃路線。")

        start_ids = self.station_manager.get_station_ids(start_station_name)
        end_ids = self.station_manager.get_station_ids(end_station_name)

        if not start_ids: raise StationNotFoundError(f"抱歉，我找不到起點站「{start_station_name}」。")
        if not end_ids: raise StationNotFoundError(f"抱歉，我找不到終點站「{end_station_name}」。")

        shortest_path = None
        min_weight = float('inf')
        
        for s_id in start_ids:
            for e_id in end_ids:
                if self.graph.has_node(s_id) and self.graph.has_node(e_id):
                    try:
                        path = nx.dijkstra_path(self.graph, source=s_id, target=e_id, weight='weight')
                        path_weight = nx.dijkstra_path_length(self.graph, source=s_id, target=e_id, weight='weight')
                        if path_weight < min_weight:
                            min_weight = path_weight
                            shortest_path = path
                    except nx.NetworkXNoPath:
                        continue
        
        if not shortest_path:
            raise RouteNotFoundError(f"抱歉，無法從「{start_station_name}」規劃到「{end_station_name}」的捷運路線。")

        # --- 【✨最終版】全新、更可靠的路徑描述產生邏輯 ---
        formatted_path = []
        current_line = None
        
        start_node_name = self.station_id_to_name.get(shortest_path[0], shortest_path[0])
        formatted_path.append(f"從「{start_node_name}」站出發。")

        for i in range(len(shortest_path) - 1):
            u_id, v_id = shortest_path[i], shortest_path[i+1]
            edge_data = self.graph.get_edge_data(u_id, v_id)
            
            if not edge_data: continue

            edge_type = edge_data.get('type')
            
            if edge_type == 'ride':
                edge_line_name = edge_data.get('line_name')
                if current_line != edge_line_name:
                    current_line = edge_line_name
                    line_to_take = current_line or "未知路線"
                    next_station_name = self.station_id_to_name.get(v_id, v_id)
                    formatted_path.append(f"搭乘【{line_to_take}】，往「{next_station_name}」方向。")
            
            elif edge_type == 'transfer':
                from_station_name = self.station_id_to_name.get(u_id, u_id)
                formatted_path.append(f"在「{from_station_name}」站進行轉乘。")
                current_line = None
        
        end_node_name = self.station_id_to_name.get(shortest_path[-1], shortest_path[-1])
        formatted_path.append(f"最終抵達「{end_node_name}」站。")
        
        final_path_description = list(dict.fromkeys(formatted_path))
        estimated_time = round(min_weight)

        return {
            "start_station": start_station_name,
            "end_station": end_station_name,
            "path_details": final_path_description,
            "estimated_time_minutes": estimated_time,
            "message": f"從「{start_station_name}」到「{end_station_name}」的預估時間約為 {estimated_time} 分鐘。詳細路線：\n" + "\n".join(final_path_description)
        }