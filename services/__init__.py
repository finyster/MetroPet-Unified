# services/__init__.py

from .fare_service import FareService
from .routing_service import RoutingManager 
from .station_service import StationManager 
from .local_data_service import LocalDataManager 
from .lost_and_found_service import LostAndFoundService
from .metro_soap_service import MetroSoapService # 統一使用 MetroSoapService
from data.data_loader import load_all_mrt_data
from utils.exceptions import ServiceInitializationError
import config
import logging
# 修正：直接从 tdx_service 导入 tdx_api 实例
from services.tdx_service import tdx_api

logger = logging.getLogger(__name__)

class ServiceRegistry:
    """
    一个集中管理所有业务服务实例的注册中心。
    采用单例模式，确保整个应用程序共享同一组服务实例。
    """
    _instance = None
    _is_initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            # 确保只初始化一次
            if not cls._instance._is_initialized:
                cls._instance._initialize_services()
                cls._instance._is_initialized = True
        return cls._instance

    def _initialize_services(self):
        """
        在应用启动时，载入所有资料并初始化所有服务。
        """
        logger.info("Initializing services...")
        try:
            # 1. 初始化无依赖或基础服务
            self.local_data_manager = LocalDataManager()
            self.station_manager = StationManager(config.STATION_DATA_PATH)
            self.tdx_api = tdx_api
            
            # 2. 初始化需要配置的服务 (如 SOAP Service)
            self.metro_soap_service = MetroSoapService(
                username=config.METRO_API_USERNAME,
                password=config.METRO_API_PASSWORD
            )

            # 3. 初始化依赖其他服务的服务
            self.fare_service = FareService(
                fare_data=self.local_data_manager.fares,
                station_id_map=self.local_data_manager.stations
            )
            
            # --- 【最终修正】将 tdx_api 也注入到 RoutingManager ---
            self.routing_manager = RoutingManager(
                station_manager_instance=self.station_manager,
                tdx_api_instance=self.tdx_api, # 加入这个缺失的依赖
                metro_soap_service_instance=self.metro_soap_service
            )
            
            # 初始化 LostAndFoundService，并注入 MetroSoapService
            self.lost_and_found_service = LostAndFoundService(
                metro_soap_service=self.metro_soap_service
            )

            logger.info("Services initialized successfully.")
        except Exception as e:
            logger.error(f"服务初始化失败: {e}", exc_info=True)
            raise ServiceInitializationError(f"核心服务初始化失败: {e}")

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

# 方便外部引用的单一实例
service_registry = ServiceRegistry()