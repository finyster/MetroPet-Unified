# services/__init__.py

from .fare_service import FareService
from .routing_service import RoutingManager
from .station_service import StationManager
from .local_data_service import LocalDataManager
from .station_id_resolver import StationIdResolver # 新增
from data.data_loader import load_all_mrt_data
from utils.exceptions import ServiceInitializationError
import config
import logging
from services.tdx_service import tdx_api # 確保 tdx_api 在這裡可以被訪問到，如果 RoutingManager 需要它
from services.metro_soap_service import metro_soap_api   # ★新增
from services.vector_search_service import vector_search_service  # 新增
from services.id_converter_service import id_converter_service # 新增這行

logger = logging.getLogger(__name__)

class ServiceRegistry:
    """
    一個集中管理所有業務服務實例的註冊中心。
    採用單例模式，確保整個應用程式共享同一組服務實例。
    """
    _instance = None
    _is_initialized = False 

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            cls._instance._initialize_services()
            cls._is_initialized = True
        return cls._instance

    def _initialize_services(self):
        """
        在應用啟動時，載入所有資料並初始化所有服務。
        """
        if self._is_initialized:
            logger.info("ServiceRegistry already initialized. Skipping.")
            return

        logger.info("Initializing services...")
        try:
            # 初始化 LocalDataManager (它自己會載入數據)
            self.local_data_manager = LocalDataManager() 
            
            # 初始化 StationManager
            self.station_manager = StationManager(config.STATION_DATA_PATH)

            # 初始化 FareService
            self.fare_service = FareService(
                fare_data=self.local_data_manager.fares,
                station_id_map=self.local_data_manager.stations # 傳遞站點映射
            )
            
            # 修正：初始化 RoutingManager，並將 station_manager 實例傳遞給它
            self.routing_manager = RoutingManager(station_manager_instance=self.station_manager)

            # 初始化 StationIdResolver，改用 config 參數
            self._station_id_resolver = StationIdResolver(
                mapping_path=config.STATIONS_SID_MAP_PATH,
                main_station_info_path=config.STATION_DATA_PATH
            )

            # TDX API 實例也應該由 ServiceRegistry 管理，確保單一實例
            # 這裡直接將 tdx_api 模組賦值，確保其方法可被調用
            self.tdx_api = tdx_api
            self.soap_api = metro_soap_api      # ★新增

            # 新增：向量搜尋服務
            self.vector_search_service = vector_search_service

            # 新增：ID 轉換服務
            self.id_converter_service = id_converter_service

            logger.info("Services initialized successfully.")
        except Exception as e:
            logger.error(f"服務初始化失敗: {e}", exc_info=True)
            raise ServiceInitializationError(f"核心服務初始化失敗: {e}")

    def get_fare_service(self) -> FareService:
        return self.fare_service

    def get_routing_manager(self) -> RoutingManager:
        return self.routing_manager
    
    def get_station_manager(self) -> StationManager:
        return self.station_manager

    def get_local_data_manager(self) -> LocalDataManager:
        return self.local_data_manager

    def get_tdx_api(self): # 新增方法以獲取 tdx_api 實例
        return self.tdx_api

    def get_soap_api(self):
        return self.soap_api

    def get_sid_resolver(self) -> StationIdResolver: # 新增
        return self._station_id_resolver

# 方便外部引用的單一實例
service_registry = ServiceRegistry()
