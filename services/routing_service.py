# services/routing_service.py 

import json
import networkx as nx
import config
import re
# from .station_service import station_manager # 不再直接導入，改從 ServiceRegistry 獲取
from services.tdx_service import tdx_api
from utils.station_name_normalizer import normalize_station_name # 導入標準化工具
from utils.exceptions import StationNotFoundError, RouteNotFoundError
import logging

logger = logging.getLogger(__name__)

class RoutingManager:
    # 修正：__init__ 方法現在接受 station_manager 作為參數
    def __init__(self, station_manager_instance): 
        logger.info("--- [Routing Service] 正在初始化並建立智慧捷運路網圖... ---")
        
        # 將傳入的 station_manager 實例賦值給 self.station_manager
        self.station_manager = station_manager_instance 

        self.station_id_to_name = self._load_station_id_map()
        self.graph = self._build_metro_graph()
        self.is_graph_ready = (self.graph is not None and self.graph.number_of_nodes() > 0)
        if self.is_graph_ready:
            logger.info("--- ✅ [Routing Service] 路網圖已成功初始化並準備就緒。 ---")
        else:
            logger.error("--- ❌ [Routing Service] 路網圖初始化失敗或為空。 ---")


    def _load_station_id_map(self) -> dict:
        """從 station_manager 建立 ID -> 名稱的對照表，用於路網圖節點命名。"""
        id_to_name = {}
        if not isinstance(self.station_manager.station_map, dict):
            logger.warning("--- ⚠️ [Routing] StationManager 的 station_map 不是有效的字典。 ---")
            return {}
        
        for name, ids in self.station_manager.station_map.items():
            # 過濾掉英文站名，避免覆蓋，確保中文站名優先
            if not re.search('[a-zA-Z]', name): # 這裡假設中文站名不含英文字母
                for station_id in ids:
                    id_to_name[station_id] = name
        logger.debug(f"--- Debug: station_id_to_name map built with {len(id_to_name)} entries. ---")
        return id_to_name

    def _get_line_name_and_code(self, line_id_prefix: str) -> tuple[str, str]:
        """根據路線ID前綴獲取中文路線名稱和路線代碼。"""
        line_map = {
            'BL': ('板南線', '藍'), 'BR': ('文湖線', '棕'), 'R': ('淡水信義線', '紅'),
            'G': ('松山新店線', '綠'), 'O': ('中和新蘆線', '橘'), 'Y': ('環狀線', '黃')
        }
        return line_map.get(line_id_prefix, ('未知路線', '未知'))

    def _build_metro_graph(self) -> nx.Graph:
        """
        從 TDX API 的 StationOfRoute 資料，建立一個帶有權重（時間）的捷運路網圖。
        確保邊的 'line' 屬性正確反映該段路線的名稱。
        """
        G = nx.Graph()
        
        all_routes_data = tdx_api.get_all_stations_of_route() 
        if not all_routes_data:
            logger.error("--- ❌ [Routing] 無法從 TDX 獲取所有路線的站點資料，路網圖建立失敗。 ---")
            return G
        
        logger.debug(f"--- Debug: all_routes_data received from TDX: {len(all_routes_data)} routes. ---")
        if all_routes_data:
            logger.debug(f"--- Debug: First route in all_routes_data: {all_routes_data[0].get('RouteID')}, stations: {len(all_routes_data[0].get('Stations', []))} ---")

        node_count = 0
        edge_count = 0
        for route_info in all_routes_data:
            line_id_prefix = route_info.get('RouteID', '') 
            line_name, line_color = self._get_line_name_and_code(line_id_prefix)
            stations_on_this_route = route_info.get("Stations", [])
            
            if not stations_on_this_route:
                logger.warning(f"--- ⚠️ Skipping route {line_id_prefix} as it has no stations. ---")
                continue

            for station in stations_on_this_route:
                station_id = station.get('StationID')
                if station_id and station_id not in G: 
                    G.add_node(station_id, name=self.station_id_to_name.get(station_id, station_id))
                    node_count += 1
            
            for i in range(len(stations_on_this_route) - 1):
                u_id = stations_on_this_route[i]['StationID']
                v_id = stations_on_this_route[i+1]['StationID']
                
                if G.has_node(u_id) and G.has_node(v_id): 
                    if not G.has_edge(u_id, v_id): 
                        G.add_edge(u_id, v_id, weight=3, type='ride', line_name=line_name, line_color=line_color, line_id=line_id_prefix)
                        edge_count += 1
                else:
                    logger.debug(f"--- ⚠️ Skipping ride edge {u_id}-{v_id} as one or both nodes not in graph. ---")

        logger.debug(f"--- Debug: After adding nodes and ride edges from all routes, graph has {G.number_of_nodes()} nodes and {G.number_of_edges()} edges. ---")


        try:
            with open(config.TRANSFER_DATA_PATH, 'r', encoding='utf-8') as f:
                transfer_data = json.load(f)
            logger.debug(f"--- Debug: Loaded {len(transfer_data)} transfer entries. ---")

            transfer_edge_count = 0
            for transfer in transfer_data:
                u, v = transfer['FromStationID'], transfer['ToStationID']
                transfer_time = 5 
                
                if G.has_node(u) and G.has_node(v):
                    if not G.has_edge(u, v) or G.get_edge_data(u, v)['weight'] > transfer_time:
                        G.add_edge(u, v, weight=transfer_time, type='transfer')
                        transfer_edge_count += 1
                else:
                    logger.debug(f"--- Debug: Skipping transfer {u}-{v} as one or both nodes not in graph. ---")
            logger.debug(f"--- Debug: Added {transfer_edge_count} transfer edges. ---")

        except FileNotFoundError:
            logger.warning(f"--- ⚠️ [Routing] 轉乘資料檔案 {config.TRANSFER_DATA_PATH} 不存在。 ---")
        except Exception as e:
            logger.warning(f"--- ⚠️ [Routing] 讀取或處理轉乘資訊時發生錯誤: {e} ---")

        logger.info(f"--- ✅ [Routing] 智慧捷運路網圖建立完成！共 {G.number_of_nodes()} 個站點，{G.number_of_edges()} 條連線。 ---")
        return G

    def find_shortest_path(self, start_station_name: str, end_station_name: str) -> dict:
        """
        尋找兩個站點之間的最短路徑，並提供詳細的路線指引。
        """
        if not self.is_graph_ready:
            logger.error("--- 錯誤: 路網圖尚未準備就緒，無法執行路徑規劃。 ---")
            raise RouteNotFoundError("抱歉，路網圖尚未準備好，無法為您規劃路線。請稍後再試。")

        # 使用標準化工具獲取站點ID
        start_norm_name = normalize_station_name(start_station_name)
        end_norm_name = normalize_station_name(end_station_name)

        if not start_norm_name:
            raise StationNotFoundError(f"抱歉，我找不到起點站「{start_station_name}」。")
        if not end_norm_name:
            raise StationNotFoundError(f"抱歉，我找不到終點站「{end_station_name}」。")

        # 這裡直接使用 self.station_manager
        start_ids = self.station_manager.get_station_ids(start_norm_name)
        end_ids = self.station_manager.get_station_ids(end_norm_name)

        if not start_ids:
            raise StationNotFoundError(f"抱歉，我找不到起點站「{start_station_name}」。")
        if not end_ids:
            raise StationNotFoundError(f"抱歉，我找不到終點站「{end_station_name}」。")

        shortest_path = None
        min_weight = float('inf')
        
        for s_id in start_ids:
            for e_id in end_ids:
                if not self.graph.has_node(s_id):
                    logger.debug(f"--- Debug: 起點站ID '{s_id}' 不在路網圖中。 ---")
                    continue
                if not self.graph.has_node(e_id):
                    logger.debug(f"--- Debug: 終點站ID '{e_id}' 不在路網圖中。 ---")
                    continue

                try:
                    path = nx.dijkstra_path(self.graph, source=s_id, target=e_id, weight='weight')
                    path_weight = nx.dijkstra_path_length(self.graph, source=s_id, target=e_id, weight='weight')

                    if path_weight < min_weight:
                        min_weight = path_weight
                        shortest_path = path

                except nx.NetworkXNoPath:
                    logger.debug(f"--- Debug: 從 {s_id} 到 {e_id} 無法找到路徑。 ---")
                    continue 
                except Exception as e:
                    logger.error(f"--- 錯誤: 路徑規劃時發生未知錯誤: {e} ---", exc_info=True)
                    raise RouteNotFoundError("路徑規劃時發生內部錯誤。")

        if not shortest_path:
            raise RouteNotFoundError(f"抱歉，無法從「{start_station_name}」規劃到「{end_station_name}」的捷運路線。")

        formatted_path = []
        current_line = None
        
        formatted_path.append(f"從「{self.station_id_to_name.get(shortest_path[0], shortest_path[0])}」出發。")

        for i in range(len(shortest_path) - 1):
            u_id = shortest_path[i]
            v_id = shortest_path[i+1]
            edge_data = self.graph.get_edge_data(u_id, v_id)

            if edge_data:
                edge_type = edge_data.get('type')
                edge_line_name = edge_data.get('line_name') 

                if edge_type == 'ride':
                    if current_line != edge_line_name: 
                        if current_line: 
                            formatted_path.append(f"抵達「{self.station_id_to_name.get(u_id, u_id)}」。")
                            formatted_path.append(f"轉乘 {edge_line_name}。")
                        else: 
                            formatted_path.append(f"搭乘 {edge_line_name}。")
                        current_line = edge_line_name
                elif edge_type == 'transfer':
                    if current_line: 
                        formatted_path.append(f"抵達「{self.station_id_to_name.get(u_id, u_id)}」。")
                    formatted_path.append(f"在「{self.station_id_to_name.get(u_id, u_id)}」轉乘。")
                    current_line = None 

        formatted_path.append(f"最終抵達「{self.station_id_to_name.get(shortest_path[-1], shortest_path[-1])}」。")
        
        estimated_time = min_weight

        return {
            "start_station": start_station_name,
            "end_station": end_station_name,
            "path_details": formatted_path,
            "estimated_time_minutes": estimated_time,
            "message": f"從「{start_station_name}」到「{end_station_name}」的預估時間約為 {estimated_time} 分鐘。詳細路線：{' '.join(formatted_path)}"
        }

# 這裡不再直接創建 routing_manager 實例，而是讓 ServiceRegistry 統一管理
# routing_manager = RoutingManager()