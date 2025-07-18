# utils/exceptions.py

class MrtAgentBaseError(Exception):
    """應用程式所有自定義錯誤的基類。"""
    pass

class StationNotFoundError(MrtAgentBaseError):
    """當找不到指定的車站時引發。"""
    pass

class RouteNotFoundError(MrtAgentBaseError):
    """當找不到指定的路徑時引發。"""
    pass

class DataValidationError(MrtAgentBaseError):
    """當資料完整性驗證失敗時引發。"""
    pass

class ServiceInitializationError(MrtAgentBaseError):
    """當服務初始化失敗時引發。"""
    pass