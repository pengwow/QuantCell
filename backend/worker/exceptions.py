"""
Worker模块异常定义
"""

from typing import Any


class WorkerException(Exception):
    """Worker基础异常"""

    def __init__(self, message: str, code: int = 500, details: dict[str, Any] | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class WorkerNotFoundException(WorkerException):
    """Worker不存在异常"""

    def __init__(self, worker_id: int):
        super().__init__(
            message=f"Worker {worker_id} 不存在",
            code=404,
            details={"worker_id": worker_id},
        )


class WorkerAlreadyExistsException(WorkerException):
    """Worker已存在异常"""

    def __init__(self, name: str):
        super().__init__(message=f"Worker '{name}' 已存在", code=409, details={"name": name})


class WorkerAlreadyRunningException(WorkerException):
    """Worker已在运行异常"""

    def __init__(self, worker_id: int):
        super().__init__(
            message=f"Worker {worker_id} 已在运行中",
            code=409,
            details={"worker_id": worker_id, "status": "running"},
        )


class WorkerNotRunningException(WorkerException):
    """Worker未在运行异常"""

    def __init__(self, worker_id: int):
        super().__init__(
            message=f"Worker {worker_id} 未在运行",
            code=400,
            details={"worker_id": worker_id, "status": "stopped"},
        )


class WorkerStartFailedException(WorkerException):
    """Worker启动失败异常"""

    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"Worker {worker_id} 启动失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason},
        )


class WorkerStopFailedException(WorkerException):
    """Worker停止失败异常"""

    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"Worker {worker_id} 停止失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason},
        )


class StrategyValidationException(WorkerException):
    """策略验证失败异常"""

    def __init__(self, errors: list):
        super().__init__(message="策略代码验证失败", code=400, details={"errors": errors})


class StrategyDeployException(WorkerException):
    """策略部署失败异常"""

    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"策略部署到Worker {worker_id} 失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason},
        )


class BacktestException(WorkerException):
    """回测执行异常"""

    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"Worker {worker_id} 回测执行失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason},
        )


class PermissionDeniedException(WorkerException):
    """权限不足异常"""

    def __init__(self, message: str = "权限不足"):
        super().__init__(message=message, code=403)


class WorkerOperationException(WorkerException):
    """Worker操作失败异常（通用业务异常）"""

    def __init__(self, operation: str, worker_id: int | None = None, message: str | None = None):
        self.operation = operation
        self.worker_id = worker_id
        if worker_id:
            message = message or f"Worker {worker_id} {operation} 操作失败"
        else:
            message = message or f"{operation} 操作失败"
        super().__init__(
            message=message,
            code=400,
            details={"operation": operation, "worker_id": worker_id},
        )


class WorkerOperationError(WorkerOperationException):
    """向后兼容别名：旧代码使用 WorkerOperationError 的场景"""

    def __init__(self, operation: str, worker_id: int | None = None, message: str | None = None):
        super().__init__(operation=operation, worker_id=worker_id, message=message)


class WorkerNotFoundError(WorkerNotFoundException):
    """向后兼容别名：旧代码使用 WorkerNotFoundError 的场景"""

    def __init__(self, worker_id: int, message: str | None = None):
        super().__init__(worker_id=worker_id)
        if message:
            self.message = message
            self.details["custom_message"] = message


class WorkerAlreadyRunningError(WorkerAlreadyRunningException):
    """向后兼容别名：旧代码使用 WorkerAlreadyRunningError 的场景"""

    def __init__(self, worker_id: int, message: str | None = None):
        super().__init__(worker_id=worker_id)
        if message:
            self.message = message
            self.details["custom_message"] = message


class LogQueryException(WorkerOperationException):
    """日志查询失败"""

    def __init__(self, worker_id: int | None = None, message: str | None = None):
        super().__init__("日志查询", worker_id, message or "日志查询失败")


class MetricsException(WorkerOperationException):
    """性能指标获取失败"""

    def __init__(self, worker_id: int | None = None, message: str | None = None):
        super().__init__("性能指标", worker_id, message or "获取性能指标失败")


class LogQueryError(LogQueryException):
    """向后兼容别名"""

    def __init__(self, worker_id: int | None = None, message: str | None = None):
        super().__init__(worker_id=worker_id, message=message)


class MetricsError(MetricsException):
    """向后兼容别名"""

    def __init__(self, worker_id: int | None = None, message: str | None = None):
        super().__init__(worker_id=worker_id, message=message)
