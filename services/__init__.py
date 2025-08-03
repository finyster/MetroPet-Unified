# services/service_registry.py (或 services/__init__.py)

import logging
import config
from utils.exceptions import ServiceInitializationError
from data.data_loader import load_all_mrt_data
from services.tdx_service import tdx_api

# --- 服務類別 Import ---
from .fare_service import FareService
from .routing_service import RoutingManager 
from .station_service import StationManager 
from .local_data_service import LocalDataManager 
from .lost_and_found_service import LostAndFoundService
from .metro_soap_service import MetroSoapService
from .prediction_service import CongestionPredictor # <--- 新增

# 設定日誌記錄器
logger = logging.getLogger(__name__)

class ServiceRegistry:
    """
    一個集中管理所有業務服務實例的註冊中心。
    採用單例模式，確保整個應用程式共享同一組服務實例。
    """
    _instance = None
    _is_initialized = False

    def __new__(cls):
        # 維持您原始的單例模式結構
        if cls._instance is None:
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            # 這裡的寫法會在第一次建立實例時就初始化，後續不再重複
            if not cls._is_initialized:
                 cls._instance._initialize_services()
                 cls._is_initialized = True
        return cls._instance

    def _initialize_services(self):
        """
        在應用啟動時，載入所有資料並初始化所有服務。
        """
        logger.info("Initializing services...")
        try:
            # 1. 初始化無依賴或基礎服務
            self.local_data_manager = LocalDataManager()
            self.station_manager = StationManager(config.STATION_DATA_PATH)
            self.tdx_api = tdx_api
            
            # 2. 初始化需要配置的服務 (如 SOAP Service)
            self.metro_soap_service = MetroSoapService(
                username=config.METRO_API_USERNAME,
                password=config.METRO_API_PASSWORD
            )

            # 3. 初始化依賴其他服務的服務
            self.fare_service = FareService(
                fare_data=self.local_data_manager.fares,
                station_id_map=self.local_data_manager.stations
            )
            
            # 【修正】初始化 RoutingManager，補上缺失的 tdx_api_instance 參數
            self.routing_manager = RoutingManager(
                station_manager_instance=self.station_manager,
                metro_soap_service_instance=self.metro_soap_service,
                tdx_api_instance=self.tdx_api  # <--- 修正這個 Bug
            )
            
            # 初始化 LostAndFoundService，並注入 MetroSoapService
            self.lost_and_found_service = LostAndFoundService(
                metro_soap_service=self.metro_soap_service
            )

            # --- 【 ✨✨✨ 新增 ✨✨✨ 】 ---
            # 初始化擁擠度預測服務，它需要 StationManager
            self.congestion_predictor = CongestionPredictor(
                station_manager_instance=self.station_manager
            )

            logger.info("All services initialized successfully.")
        except Exception as e:
            logger.error(f"服務初始化失敗: {e}", exc_info=True)
            raise ServiceInitializationError(f"核心服務初始化失敗: {e}")

    # --- (所有 get_* 方法) ---
    def get_fare_service(self) -> FareService:
        return self.fare_service

    def get_routing_manager(self) -> RoutingManager:
        return self.routing_manager
    
    def get_station_manager(self) -> StationManager:
        return self.station_manager

    def get_local_data_manager(self) -> LocalDataManager:
        return self.local_data_manager

    def get_tdx_api(self):
        return self.tdx_api

    def get_lost_and_found_service(self) -> LostAndFoundService:
        return self.lost_and_found_service

    def get_metro_soap_service(self) -> MetroSoapService:
        return self.metro_soap_service

    # --- 【 ✨✨✨ 新增 ✨✨✨ 】 ---
    def get_congestion_predictor(self) -> CongestionPredictor:
        """返回擁擠度預測服務的實例。"""
        return self.congestion_predictor

# --- 全局單一實例 ---
# 應用程式的其他部分可以從這裡導入並使用 service_registry 來獲取任何需要的服務。
service_registry = ServiceRegistry()