# services/routing_service.py 

import json
import networkx as nx
import config
import re
import logging
from bs4 import BeautifulSoup
from services.tdx_service import tdx_api
from services.metro_soap_service import MetroSoapService # 修正：導入 Class
from utils.station_name_normalizer import normalize_station_name
from utils.exceptions import StationNotFoundError, RouteNotFoundError

logger = logging.getLogger(__name__)

class RoutingManager:
    def __init__(self, station_manager_instance, tdx_api_instance, metro_soap_service_instance):
        logger.info("--- [Routing Service] 正在初始化... ---")
        self.station_manager = station_manager_instance
        self.tdx_api = tdx_api_instance
        self.metro_soap_service = metro_soap_service_instance
        
        self.station_id_to_name = self._load_station_id_map()
        self.graph = self._build_metro_graph()
        self.is_graph_ready = (self.graph is not None and self.graph.number_of_nodes() > 0)
        if self.is_graph_ready:
            logger.info("--- ✅ [Routing Service] 路網圖已成功初始化。 ---")
        else:
            logger.error("--- ❌ [Routing Service] 路網圖初始化失敗。 ---")

    def _load_station_id_map(self) -> dict:
        id_to_name = {}
        if not isinstance(self.station_manager.station_map, dict): return {}
        for name, ids in self.station_manager.station_map.items():
            if not re.search('[a-zA-Z]', name):
                for station_id in ids:
                    id_to_name[station_id] = name
        return id_to_name

    def _get_line_name_and_code(self, line_id_prefix: str) -> tuple[str, str]:
        line_map = {
            'BL': ('板南線', '藍'), 'BR': ('文湖線', '棕'), 'R': ('淡水信義線', '紅'),
            'G': ('松山新店線', '綠'), 'O': ('中和新蘆線', '橘'), 'Y': ('環狀線', '黃')
        }
        return line_map.get(line_id_prefix, ('未知路線', '未知'))

    def _build_metro_graph(self) -> nx.Graph:
        G = nx.Graph()
        all_routes_data = self.tdx_api.get_all_stations_of_route()
        if not all_routes_data:
            logger.error("--- ❌ [Routing] 無法從 TDX 獲取路網資料。 ---")
            return G
            
        line_map_keys = ['BL', 'BR', 'R', 'G', 'O', 'Y']

        for route_info in all_routes_data:
            route_id_raw = route_info.get('RouteID', '')
            
            # --- 【⭐ 核心修正 ⭐】 ---
            # 聰明地從複雜的 RouteID (如 TRTC-R) 中提取出我們需要的縮寫 (R)
            line_id_prefix = ''
            for key in line_map_keys:
                if key in route_id_raw:
                    line_id_prefix = key
                    break
            # --- 【修正結束】 ---

            line_name, _ = self._get_line_name_and_code(line_id_prefix)
            stations = route_info.get("Stations", [])
            for station in stations:
                sid = station.get('StationID')
                if sid and sid not in G:
                    G.add_node(sid, name=self.station_id_to_name.get(sid, sid))
            for i in range(len(stations) - 1):
                u_id, v_id = stations[i]['StationID'], stations[i+1]['StationID']
                if G.has_node(u_id) and G.has_node(v_id) and not G.has_edge(u_id, v_id):
                    G.add_edge(u_id, v_id, weight=3, type='ride', line_name=line_name)
        try:
            with open(config.TRANSFER_DATA_PATH, 'r', encoding='utf-8') as f:
                transfer_data = json.load(f)
            for transfer in transfer_data:
                u, v = transfer['FromStationID'], transfer['ToStationID']
                if G.has_node(u) and G.has_node(v):
                    G.add_edge(u, v, weight=transfer.get('TransferTime', 5), type='transfer')
        except FileNotFoundError:
            logger.warning(f"--- ⚠️ [Routing] 轉乘資料檔案不存在。 ---")
        return G

    def _format_path_details(self, path: list) -> list[str]:
        if len(path) < 2: return ["路徑資訊不足。"]
        steps = [f"從「{self.station_id_to_name.get(path[0], path[0])}」站出發。"]
        i = 0
        while i < len(path) - 1:
            start_node_id = path[i]
            edge_data = self.graph.get_edge_data(start_node_id, path[i+1])
            if not edge_data or edge_data.get('type') == 'transfer':
                i += 1
                continue
            current_line = edge_data.get('line_name', '未知路線')
            segment_end_index = i + 1
            while segment_end_index < len(path) - 1:
                next_edge = self.graph.get_edge_data(path[segment_end_index], path[segment_end_index+1])
                if not next_edge or next_edge.get('line_name') != current_line or next_edge.get('type') == 'transfer':
                    break
                segment_end_index += 1
            end_of_segment_id = path[segment_end_index]
            stop_count = segment_end_index - i
            steps.append(f"搭乘【{current_line}】，經過 {stop_count} 站，抵達「{self.station_id_to_name.get(end_of_segment_id, end_of_segment_id)}」站。")
            i = segment_end_index
        final_station_name = self.station_id_to_name.get(path[-1], path[-1])
        if not steps[-1].__contains__(final_station_name):
            steps.append(f"您已抵達目的地「{final_station_name}」站。")
        return steps

    def find_shortest_path(self, start_station_name: str, end_station_name: str) -> dict:
        if not self.is_graph_ready: raise RouteNotFoundError("路網圖尚未準備好。")
        start_ids = self.station_manager.get_station_ids(start_station_name)
        end_ids = self.station_manager.get_station_ids(end_station_name)
        if not start_ids: raise StationNotFoundError(f"找不到起點站「{start_station_name}」。")
        if not end_ids: raise StationNotFoundError(f"找不到終點站「{end_station_name}」。")
        shortest_path, min_weight = None, float('inf')
        for s_id in start_ids:
            for e_id in end_ids:
                if self.graph.has_node(s_id) and self.graph.has_node(e_id):
                    try:
                        path = nx.dijkstra_path(self.graph, source=s_id, target=e_id, weight='weight')
                        path_weight = nx.dijkstra_path_length(self.graph, source=s_id, target=e_id, weight='weight')
                        if path_weight < min_weight:
                            min_weight, shortest_path = path_weight, path
                    except nx.NetworkXNoPath: continue
        if not shortest_path: raise RouteNotFoundError(f"無法從「{start_station_name}」規劃到「{end_station_name}」的路線。")
        formatted_path = self._format_path_details(shortest_path)
        return {
            "start_station": start_station_name, "end_station": end_station_name,
            "path_details": formatted_path, "estimated_time_minutes": round(min_weight),
            "message": f"從「{start_station_name}」到「{end_station_name}」的預估時間約為 {round(min_weight)} 分鐘。詳細路線：\n" + "\n".join(formatted_path)
        }

    def find_path_with_soap(self, start_station_name: str, end_station_name: str) -> dict:
        start_sid = self.station_manager.get_sid(start_station_name)
        end_sid = self.station_manager.get_sid(end_station_name)
        if not start_sid: raise StationNotFoundError(f"找不到起點站「{start_station_name}」的 SID。")
        if not end_sid: raise StationNotFoundError(f"找不到終點站「{end_station_name}」的 SID。")
        route_info = self.metro_soap_service.get_recommand_route_soap(start_sid, end_sid)
        if not route_info: raise RouteNotFoundError("無法從官方 API 獲取路線建議。")
        try:
            path_details, total_time = [], 0
            routes = route_info.get('Route', [])
            if not isinstance(routes, list): routes = [routes]
            for route in routes:
                from_station, to_station, line = route.get('FromStation'), route.get('ToStation'), route.get('Line')
                time_minutes = int(route.get('Time', 0))
                total_time += time_minutes
                path_details.append(f"搭乘【{line}】從「{from_station}」到「{to_station}」，約需 {time_minutes} 分鐘。")
            if not path_details: raise RouteNotFoundError("官方 API 回應中未包含路線步驟。")
            return {
                "start_station": start_station_name, "end_station": end_station_name,
                "path_details": path_details, "estimated_time_minutes": total_time,
                "message": f"從「{start_station_name}」到「{end_station_name}」的官方建議路線預估時間約為 {total_time} 分鐘。\n" + "\n".join(path_details)
            }
        except Exception as e:
            raise RouteNotFoundError(f"解析官方路線時發生錯誤: {e}")