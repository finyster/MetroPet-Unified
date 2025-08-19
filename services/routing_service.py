# services/routing_service.py

import json
import networkx as nx
import config
import re
from services.tdx_service import tdx_api
from utils.exceptions import StationNotFoundError, RouteNotFoundError
from utils.station_name_normalizer import normalize_station_name
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class RoutingManager:
    def __init__(self, station_manager_instance):
        logger.info("--- [Routing Service] 正在初始化並建立智慧捷運路網圖... ---")

        self.station_manager = station_manager_instance
        self.station_id_to_name = self._load_station_id_map(self.station_manager.station_map)

        self.line_details: Dict[str, Dict[str, Any]] = {}

        self.graph = self._build_metro_graph()
        self.is_graph_ready = (self.graph is not None and self.graph.number_of_nodes() > 0)

        if self.is_graph_ready:
            logger.info("--- ✅ [Routing Service] 路網圖已成功初始化並準備就緒。 ---")
        else:
            logger.error("--- ❌ [Routing Service] 路網圖初始化失敗或為空。 ---")

    def _load_station_id_map(self, station_map: dict) -> dict:
        id_to_name = {}
        # 優先使用無英文/數字的作為官方中文名
        for name, ids in station_map.items():
            if not re.search('[a-zA-Z0-9]', name):
                for station_id in ids:
                    if station_id not in id_to_name:
                        id_to_name[station_id] = name.replace("臺", "台") + "站"
        
        # 補全可能因別名而遺漏的ID
        for name, ids in station_map.items():
            for station_id in ids:
                if station_id not in id_to_name:
                    # 使用標準化後的名稱作為備用
                    id_to_name[station_id] = name.replace("臺", "台") + "站"
        return id_to_name

    def _get_line_name_and_color(self, line_code: str) -> tuple[str, str]:
        line_map = {
            'BL': ('板南線', '藍線'), 'BR': ('文湖線', '棕線'), 'R': ('淡水信義線', '紅線'),
            'G': ('松山新店線', '綠線'), 'O': ('中和新蘆線', '橘線'), 'Y': ('環狀線', '黃線')
        }
        return line_map.get(line_code, (line_code, '未知顏色'))

    def _build_metro_graph(self) -> nx.Graph:
        # ... 此方法與上一版相同，為節省篇幅省略 ...
        # (請保留您檔案中此方法的完整程式碼)
        G = nx.Graph()
        all_routes_data = tdx_api.get_all_stations_of_route()
        if not all_routes_data:
            logger.error("--- ❌ [Routing] 無法從 TDX 獲取所有路線的站點資料，路網圖建立失敗。 ---")
            return G

        for route_info in all_routes_data:
            for station in route_info.get("Stations", []):
                station_id = station.get('StationID')
                if station_id and station_id not in G:
                    G.add_node(station_id, name=self.station_id_to_name.get(station_id, station_id))

        for route_info in all_routes_data:
            stations_on_this_route = route_info.get("Stations", [])
            if not stations_on_this_route:
                continue
            route_id = route_info.get('RouteID', '')
            line_code_match = re.match(r"([A-Z]+)", route_id)
            if not line_code_match:
                continue
            line_code = line_code_match.group(1)
            line_name, line_color = self._get_line_name_and_color(line_code)

            if line_name not in self.line_details:
                terminus1_id = stations_on_this_route[0]['StationID']
                terminus2_id = stations_on_this_route[-1]['StationID']
                self.line_details[line_name] = {
                    "color": line_color,
                    "stations": [s['StationID'] for s in stations_on_this_route],
                    "terminus": [terminus1_id, terminus2_id]
                }

            for i in range(len(stations_on_this_route) - 1):
                u_id = stations_on_this_route[i]['StationID']
                v_id = stations_on_this_route[i+1]['StationID']
                if G.has_node(u_id) and G.has_node(v_id):
                     # 允許重複添加邊，但更新為ride類型和正確的line_name
                    G.add_edge(u_id, v_id, weight=3, type='ride', line_name=line_name)

        try:
            with open(config.TRANSFER_DATA_PATH, 'r', encoding='utf-8') as f:
                transfer_data = json.load(f)
            for transfer in transfer_data:
                u, v = transfer['FromStationID'], transfer['ToStationID']
                if G.has_node(u) and G.has_node(v):
                    G.add_edge(u, v, weight=5, type='transfer') # 轉乘權重較高
        except Exception as e:
            logger.warning(f"--- ⚠️ [Routing] 處理轉乘資訊時發生錯誤: {e} ---")

        logger.info(f"--- ✅ [Routing] 智慧捷運路網圖建立完成！共 {G.number_of_nodes()} 個站點，{G.number_of_edges()} 條連線。 ---")
        return G

    def _generate_directions_from_ids(self, path_ids: List[str]) -> List[str]:
        """
        【✨最終修正版 v2✨】根據車站ID列表，透過偵測「路線變化」來生成轉乘指引。
        """
        if not path_ids or len(path_ids) < 2:
            return ["路徑資訊不足，無法生成指引。"]

        directions = []
        
        # 1. 起點指引
        start_node_name = self.station_id_to_name.get(path_ids[0], path_ids[0])
        directions.append(f"從「{start_node_name}」站上車。")

        # 2. 路線搭乘與轉乘指引
        current_line = None
        for i in range(len(path_ids) - 1):
            u_id, v_id = path_ids[i], path_ids[i+1]
            
            if not self.graph.has_edge(u_id, v_id): continue
            edge_data = self.graph.get_edge_data(u_id, v_id)
            
            # 我們只關心 'ride' 類型的邊，因為 'transfer' 邊不會出現在API路徑中
            if edge_data.get('type') == 'ride':
                line_name = edge_data.get('line_name')
                
                # 如果路線發生變化，代表這是一個轉乘點
                if line_name != current_line:
                    # 如果不是第一段路程，就產生轉乘提示
                    if current_line is not None:
                        transfer_station_name = self.station_id_to_name.get(u_id, u_id)
                        line_info = self.line_details.get(line_name)
                        line_color = line_info['color'] if line_info else '未知顏色'
                        directions.append(f"在「{transfer_station_name}」站，轉乘【{line_name} ({line_color})】。")

                    current_line = line_name
                    
                    # 產生搭乘方向指引
                    line_info = self.line_details.get(current_line)
                    if line_info:
                        line_color = line_info['color']
                        terminus1, terminus2 = line_info['terminus']
                        try:
                            dist_u_t1 = nx.shortest_path_length(self.graph, source=u_id, target=terminus1)
                            dist_v_t1 = nx.shortest_path_length(self.graph, source=v_id, target=terminus1)
                            direction_station_id = terminus1 if dist_v_t1 < dist_u_t1 else terminus2
                            direction_station_name = self.station_id_to_name.get(direction_station_id, direction_station_id)
                            directions.append(f"搭乘【{current_line} ({line_color})】，往「{direction_station_name}」方向。")
                        except (nx.NetworkXNoPath, nx.NodeNotFound):
                            directions.append(f"搭乘【{current_line} ({line_color})】。")
                    else:
                        directions.append(f"搭乘【{current_line}】。")

        # 3. 終點指引
        end_node_name = self.station_id_to_name.get(path_ids[-1], path_ids[-1])
        directions.append(f"在「{end_node_name}」站下車，抵達目的地。")

        return list(dict.fromkeys(directions)) # 移除重複語句

    # ... find_shortest_path 和 generate_directions_from_path 方法與上一版相同 ...
    # ... 為節省篇幅省略，請保留您檔案中這兩個方法的完整程式碼 ...
    def find_shortest_path(self, start_station_name: str, end_station_name: str) -> dict:
        if not self.is_graph_ready:
            raise RouteNotFoundError("抱歉，路網圖尚未準備好。")
        start_ids = self.station_manager.get_station_ids(start_station_name)
        end_ids = self.station_manager.get_station_ids(end_station_name)
        if not start_ids: raise StationNotFoundError(f"找不到起點站「{start_station_name}」。")
        if not end_ids: raise StationNotFoundError(f"找不到終點站「{end_station_name}」。")
        shortest_path_ids = None
        min_weight = float('inf')
        for s_id in start_ids:
            for e_id in end_ids:
                if self.graph.has_node(s_id) and self.graph.has_node(e_id):
                    try:
                        path_ids = nx.dijkstra_path(self.graph, source=s_id, target=e_id, weight='weight')
                        path_weight = nx.dijkstra_path_length(self.graph, source=s_id, target=e_id, weight='weight')
                        if path_weight < min_weight:
                            min_weight = path_weight
                            shortest_path_ids = path_ids
                    except nx.NetworkXNoPath:
                        continue
        if not shortest_path_ids:
            raise RouteNotFoundError(f"無法從「{start_station_name}」規劃到「{end_station_name}」。")
        final_path_description = self._generate_directions_from_ids(shortest_path_ids)
        estimated_time = round(min_weight)
        return {
            "start_station": start_station_name,
            "end_station": end_station_name,
            "path_details": final_path_description,
            "estimated_time_minutes": estimated_time,
            "message": f"從「{start_station_name}」到「{end_station_name}」的預估時間約為 {estimated_time} 分鐘。詳細路線：\n" + "\n".join(final_path_description)
        }

    def generate_directions_from_path(self, station_names: List[str]) -> List[str]:
        path_ids = []
        for name in station_names:
            norm_name = normalize_station_name(name)
            ids = self.station_manager.get_station_ids(norm_name)
            if ids and isinstance(ids, list):
                path_ids.append(ids[0])
            else:
                logger.warning(f"在從官方API路徑生成指引時，找不到站名 '{name}' (normalized: {norm_name}) 的ID。")
        
        if len(path_ids) < 2:
            logger.error(f"無法從官方路徑 '{station_names}' 解析出有效的ID路徑。")
            return ["抱歉，解析官方建議路線時發生錯誤。"]
            
        return self._generate_directions_from_ids(path_ids)