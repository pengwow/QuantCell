"""
Worker 异常处理装饰器

提供统一的异常处理装饰器，自动捕获 Worker 异常并转换为 HTTP 响应。
支持同步和异步函数，自动处理日志记录和错误追踪。

使用示例:
    from .decorators import handle_worker_exceptions
    from .exceptions import WorkerNotFoundException

    @router.get("/{worker_id}")
    @handle_worker_exceptions("获取Worker详情")
    async def get_worker(worker_id: int):
        result = await worker_core_service.async_get_worker(worker_id)
        return result
"""

import asyncio
import functools
import traceback
from typing import TYPE_CHECKING

from fastapi import HTTPException

from utils.logger import LogType, get_logger

from .exceptions import (
    WorkerAlreadyRunningException,
    WorkerException,
    WorkerNotFoundException,
    WorkerOperationException,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__, LogType.APPLICATION)


def _handle_exception(operation_name: str, exc: Exception) -> HTTPException:
    """
    统一处理异常的辅助函数

    Args:
        operation_name: 操作名称
        exc: 捕获的异常

    Returns:
        HTTPException: 转换后的HTTP异常
    """
    # 已知 Worker 异常：使用异常自带的 HTTP 状态码
    if isinstance(exc, WorkerNotFoundException):
        logger.warning(f"{operation_name}: {exc.message}")
        return HTTPException(status_code=exc.code, detail=exc.message)

    if isinstance(exc, WorkerAlreadyRunningException):
        logger.warning(f"{operation_name}: {exc.message}")
        return HTTPException(status_code=exc.code, detail=exc.message)

    if isinstance(exc, WorkerOperationException):
        logger.warning(f"{operation_name}: {exc.message}")
        return HTTPException(status_code=exc.code, detail=exc.message)

    if isinstance(exc, WorkerException):
        logger.error(f"{operation_name}: {exc.message}")
        return HTTPException(status_code=exc.code, detail=exc.message)

    # FastAPI 的 HTTPException 直接传递
    if isinstance(exc, HTTPException):
        return exc

    # axon_quant 异常:映射为语义化 HTTP 状态码
    # 延迟导入避免与 axon_bridge.__init__ 的重导出循环
    # 注:axon_quant 的 PyO3 异常类(DataError/OmsError 等)无继承关系,
    # 不能用 isinstance(AxonError) 统一判断,改用 map_error 返回的 code 区分
    try:
        from axon_bridge._errors import map_error

        mapped = map_error(exc)
        # 已知 axon_quant 子类会被赋予特定 code(如 data_error/oms_conflict),
        # 非 axon_quant 异常返回默认 code "axon_quant_error",由下方通用 500 处理
        if mapped.code != "axon_quant_error":
            logger.warning(f"{operation_name}: axon_quant 错误 [{mapped.code}] → HTTP {mapped.http_status}: {exc}")
            return mapped.to_http()
    except ImportError:
        pass  # axon_bridge 不可用时跳过

    # 未知异常：使用 500 状态码
    logger.error(f"{operation_name} 发生未预期异常: {exc}")
    traceback.print_exc()
    return HTTPException(status_code=500, detail=f"服务器内部错误: {exc!s}")


def handle_worker_exceptions(operation_name: str | None = None) -> Callable:
    """
    Worker 异常处理装饰器

    自动捕获 Worker 异常并转换为 HTTP 响应，统一处理日志记录。

    Args:
        operation_name: 操作名称，用于日志记录。若不传则使用被装饰函数的名称。

    支持:
        - 同步函数
        - 异步函数
        - FastAPI HTTPException 直接传递
    """

    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    raise _handle_exception(op_name, exc) from exc

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                raise _handle_exception(op_name, exc) from exc

        return sync_wrapper

    return decorator


__all__ = [
    "handle_worker_exceptions",
]
