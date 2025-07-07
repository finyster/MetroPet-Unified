# services/local_data_service.py

import pandas as pd
import json
import os
from typing import Optional, Dict, List

# --- 定義所有資料檔案的路徑 ---
DATA_PATH = "data"
FARE_FILE = os.path.join(DATA_PATH, "臺北捷運系統票價資料(1090301).csv")
EXIT_FILE = os.path.join(DATA_PATH, "臺北捷運車站出入口座標.csv")
STATIONS_FILE = os.path.join(DATA_PATH, "stations (1).json")
TRAVEL_TIME_FILE = os.path.join(DATA_PATH, "臺北捷運相鄰兩站間之行駛時間及停靠站時間 (1).csv")

class LocalDataManager:
    def __init__(self):
        # 載入所有資料檔案
        self.fare_df = self._load_csv(FARE_FILE, encoding='cp950')
        self.exit_df = self._load_csv(EXIT_FILE, encoding='cp950')
        self.travel_time_df = self._load_csv(TRAVEL_TIME_FILE, encoding='cp950')
        
        # ---【核心升級】: 載入 JSON 並建立路網資料結構 ---
        stations_json = self._load_json(STATIONS_FILE)
        self.line_stations, self.station_info = self._process_stations_data(stations_json)
        
        print("\n--- 本地捷運資料庫已成功載入！所有資料集均已整合。 ---\n")

    def _load_csv(self, file_path: str, encoding: str) -> Optional[pd.DataFrame]:
        if not os.path.exists(file_path):
            print(f"!!! 警告：在 data 資料夾中找不到 {os.path.basename(file_path)} !!!")
            return None
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            df.columns = df.columns.str.strip() # 清理欄位名稱的隱形空格
            print(f"檔案 '{os.path.basename(file_path)}' 已載入並清理。")
            return df
        except Exception as e:
            print(f"!!! 讀取檔案 {os.path.basename(file_path)} 時發生錯誤: {e} !!!")
            return None

    def _load_json(self, file_path: str) -> Optional[Dict]:
        if not os.path.exists(file_path):
            print(f"!!! 警告：在 data 資料夾中找不到 {os.path.basename(file_path)} !!!")
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"檔案 '{os.path.basename(file_path)}' 已成功載入。")
                return data
        except Exception as e:
            print(f"!!! 讀取檔案 {os.path.basename(file_path)} 時發生錯誤: {e} !!!")
            return None

    def _process_stations_data(self, stations_json: Optional[Dict]) -> (Dict, Dict):
        """處理 stations.json，建立路線與站點的對照表。"""
        if not stations_json:
            return {}, {}
        
        line_stations = {}
        station_info = {}

        for line_code, line_data in stations_json.items():
            line_name = line_data.get('name')
            stations = line_data.get('stations', [])
            
            if not line_name or not stations: continue
            
            station_sequence = [station.get('name') for station in stations if station.get('name')]
            line_stations[line_name] = station_sequence

            for station in stations:
                st_name = station.get('name')
                if not st_name: continue
                if st_name not in station_info:
                    station_info[st_name] = {"lines": []}
                station_info[st_name]["lines"].append(line_name)
        
        print("路網資料結構已建立，『車站大腦』已上線！")
        return line_stations, station_info

    def get_fare(self, start_station: str, end_station: str) -> Optional[int]:
        if self.fare_df is None: return None
        try:
            start_clean = start_station.replace("站", "")
            end_clean = end_station.replace("站", "")
            result = self.fare_df[(self.fare_df['起站'].str.contains(start_clean)) & (self.fare_df['訖站'].str.contains(end_clean))]
            if not result.empty: return result.iloc[0]['全票票價']
        except KeyError as e: print(f"!!! 票價查詢錯誤：找不到欄位 {e}。")
        return None

    def get_exits_by_station(self, station_name: str) -> Optional[str]:
        if self.exit_df is None: return None
        try:
            station_clean = station_name.replace("站", "")
            results = self.exit_df[self.exit_df['出入口名稱'].str.contains(station_clean)]
            if not results.empty:
                exit_list = [f"{station_name} 的出口資訊如下："]
                for _, row in results.iterrows():
                    exit_list.append(f"- 出口 {row['出入口編號']}")
                return "\n".join(exit_list)
        except KeyError as e: print(f"!!! 出口查詢錯誤：找不到欄位 {e}。")
        return None

    def calculate_travel_time(self, start_station: str, end_station: str) -> Optional[str]:
        """計算同一條路線上，任意兩站的總行駛時間。"""
        if self.travel_time_df is None or not self.station_info:
            return "錯誤：缺少路網或時間資料，無法計算。"
        
        start_clean = start_station.replace("站", "")
        end_clean = end_station.replace("站", "")

        if start_clean not in self.station_info or end_clean not in self.station_info:
            return f"抱歉，我找不到 '{start_station}' 或 '{end_station}' 的車站資訊。"

        common_lines = list(set(self.station_info[start_clean]['lines']) & set(self.station_info[end_clean]['lines']))
        if not common_lines:
            return "抱歉，這兩站不在同一條直達路線上，跨路線轉乘時間計算功能尚未開放。"
        
        line_to_use = common_lines[0]
        station_list = self.line_stations[line_to_use]
        
        try:
            start_index = station_list.index(start_clean)
            end_index = station_list.index(end_clean)
        except ValueError: return "錯誤：在路線上找不到車站索引。"

        path_stations = station_list[min(start_index, end_index) : max(start_index, end_index) + 1]
        
        total_seconds = 0
        for i in range(len(path_stations) - 1):
            station_A = path_stations[i]
            station_B = path_stations[i+1]
            
            result = self.travel_time_df[
                ((self.travel_time_df['本站'] == station_A) & (self.travel_time_df['鄰站'] == station_B)) |
                ((self.travel_time_df['本站'] == station_B) & (self.travel_time_df['鄰站'] == station_A))
            ]
            if not result.empty:
                total_seconds += result.iloc[0]['行駛時間(秒)']
                if i > 0: total_seconds += result.iloc[0]['停靠時間(秒)']
        
        minutes, seconds = divmod(total_seconds, 60)
        return f"從 {start_station} 到 {end_station} (搭乘{line_to_use})，預估總行駛時間約為 {int(minutes)} 分 {int(seconds)} 秒。"

local_data_manager = LocalDataManager()