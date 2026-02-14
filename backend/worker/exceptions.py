# -*- coding: utf-8 -*-
"""
Worker模块异常定义
"""

from typing import Optional, Any, Dict


class WorkerException(Exception):
    """Worker基础异常"""
    
    def __init__(self, message: str, code: int = 500, details: Optional[Dict[str, Any]] = None):
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
            details={"worker_id": worker_id}
        )


class WorkerAlreadyExistsException(WorkerException):
    """Worker已存在异常"""
    
    def __init__(self, name: str):
        super().__init__(
            message=f"Worker '{name}' 已存在",
            code=409,
            details={"name": name}
        )


class WorkerAlreadyRunningException(WorkerException):
    """Worker已在运行异常"""
    
    def __init__(self, worker_id: int):
        super().__init__(
            message=f"Worker {worker_id} 已在运行中",
            code=400,
            details={"worker_id": worker_id, "status": "running"}
        )


class WorkerNotRunningException(WorkerException):
    """Worker未在运行异常"""
    
    def __init__(self, worker_id: int):
        super().__init__(
            message=f"Worker {worker_id} 未在运行",
            code=400,
            details={"worker_id": worker_id, "status": "stopped"}
        )


class WorkerStartFailedException(WorkerException):
    """Worker启动失败异常"""
    
    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"Worker {worker_id} 启动失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason}
        )


class WorkerStopFailedException(WorkerException):
    """Worker停止失败异常"""
    
    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"Worker {worker_id} 停止失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason}
        )


class StrategyValidationException(WorkerException):
    """策略验证失败异常"""
    
    def __init__(self, errors: list):
        super().__init__(
            message="策略代码验证失败",
            code=400,
            details={"errors": errors}
        )


class StrategyDeployException(WorkerException):
    """策略部署失败异常"""
    
    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"策略部署到Worker {worker_id} 失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason}
        )


class BacktestException(WorkerException):
    """回测执行异常"""
    
    def __init__(self, worker_id: int, reason: str):
        super().__init__(
            message=f"Worker {worker_id} 回测执行失败: {reason}",
            code=500,
            details={"worker_id": worker_id, "reason": reason}
        )


class PermissionDeniedException(WorkerException):
    """权限不足异常"""
    
    def __init__(self, message: str = "权限不足"):
        super().__init__(
            message=message,
            code=403
        )


class InvalidParameterException(WorkerException):
    """参数无效异常"""
    
    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"参数 '{field}' 无效: {message}",
            code=400,
            details={"field": field, "message": message}
        )
