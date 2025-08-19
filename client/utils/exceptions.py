# utils/exceptions.py

class ServiceInitializationError(Exception):
    """應用程式服務初始化失敗時拋出的自訂例外。"""
    pass

class StationNotFoundError(Exception):
    """當查詢的車站名稱不存在或無法解析時拋出的自訂例外。"""
    pass

class RouteNotFoundError(Exception):
    """當無法找到起點到終點的有效路線時拋出的自訂例外。"""
    pass

class DataLoadError(Exception):
    """當數據載入（例如從文件或外部源）失敗時拋出的自訂例外。"""
    pass

class ExternalAPIError(Exception):
    """當呼叫外部 API 失敗或返回非預期響應時拋出的自訂例外。"""
    pass

class PredictorError(Exception):
    """當預測模型執行失敗或返回無效結果時拋出的自訂例外。"""
    pass

class InvalidTimeFormatError(Exception):
    """當時間格式無法解析時拋出的自訂例外。"""
    pass
