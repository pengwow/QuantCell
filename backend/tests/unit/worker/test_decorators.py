"""
异常处理装饰器单元测试

验证 handle_worker_exceptions 装饰器：
- 正确处理 WorkerNotFoundException
- 正确处理 WorkerAlreadyRunningException
- 正确处理 WorkerOperationException
- 正确处理通用 Exception
- 正确处理 HTTPException 直接传递
- 同步和异步函数都能正常工作
"""

import asyncio

import pytest
from fastapi import HTTPException

from worker.decorators import handle_worker_exceptions
from worker.exceptions import (
    WorkerAlreadyRunningException,
    WorkerNotFoundException,
    WorkerOperationException,
)


class TestHandleWorkerExceptions:
    """测试异常处理装饰器"""

    def test_async_worker_not_found_exception(self):
        """异步函数：WorkerNotFoundException → 404"""

        @handle_worker_exceptions("测试操作")
        async def async_func():
            raise WorkerNotFoundException(123)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(async_func())
        assert exc_info.value.status_code == 404
        assert "123" in exc_info.value.detail
        assert "不存在" in exc_info.value.detail

    def test_async_worker_already_running_exception(self):
        """异步函数：WorkerAlreadyRunningException → 409"""

        @handle_worker_exceptions("测试操作")
        async def async_func():
            raise WorkerAlreadyRunningException(456)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(async_func())
        assert exc_info.value.status_code == 409
        assert "456" in exc_info.value.detail
        assert "运行" in exc_info.value.detail

    def test_async_worker_operation_exception(self):
        """异步函数：WorkerOperationException → 400"""

        @handle_worker_exceptions("测试操作")
        async def async_func():
            msg = "update"
            raise WorkerOperationException(msg, worker_id=789)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(async_func())
        assert exc_info.value.status_code == 400
        assert "789" in exc_info.value.detail
        assert "update" in exc_info.value.detail

    def test_async_unexpected_exception(self):
        """异步函数：未预期异常 → 500"""

        @handle_worker_exceptions("测试操作")
        async def async_func():
            msg = "未知错误"
            raise ValueError(msg)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(async_func())
        assert exc_info.value.status_code == 500
        assert "未知错误" in exc_info.value.detail

    def test_async_http_exception_passthrough(self):
        """异步函数：HTTPException 直接传递"""

        @handle_worker_exceptions("测试操作")
        async def async_func():
            raise HTTPException(status_code=403, detail="权限不足")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(async_func())
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "权限不足"

    def test_sync_worker_not_found_exception(self):
        """同步函数：WorkerNotFoundException → 404"""

        @handle_worker_exceptions("测试操作")
        def sync_func():
            raise WorkerNotFoundException(111)

        with pytest.raises(HTTPException) as exc_info:
            sync_func()
        assert exc_info.value.status_code == 404

    def test_sync_unexpected_exception(self):
        """同步函数：未预期异常 → 500"""

        @handle_worker_exceptions("测试操作")
        def sync_func():
            msg = "同步函数错误"
            raise RuntimeError(msg)

        with pytest.raises(HTTPException) as exc_info:
            sync_func()
        assert exc_info.value.status_code == 500

    def test_successful_async_function(self):
        """异步函数：成功执行，不抛异常"""

        @handle_worker_exceptions("测试操作")
        async def async_func():
            return {"result": "success"}

        result = asyncio.run(async_func())
        assert result == {"result": "success"}

    def test_successful_sync_function(self):
        """同步函数：成功执行，不抛异常"""

        @handle_worker_exceptions("测试操作")
        def sync_func():
            return [1, 2, 3]

        result = sync_func()
        assert result == [1, 2, 3]

    def test_uses_default_operation_name(self):
        """不传 operation_name 时使用函数名"""

        @handle_worker_exceptions()
        async def my_custom_function():
            raise WorkerNotFoundException(1)

        # 装饰器应能正常工作，不抛 NameError 等错误
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(my_custom_function())
        assert exc_info.value.status_code == 404

    def test_backward_compatibility_old_error_classes(self):
        """向后兼容：旧异常类名（WorkerNotFoundError）能正确处理"""
        from worker.exceptions import WorkerNotFoundError

        @handle_worker_exceptions("测试操作")
        async def async_func():
            raise WorkerNotFoundError(999)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(async_func())
        assert exc_info.value.status_code == 404
        assert "999" in exc_info.value.detail


class TestAxonQuantErrorMapping:
    """验证装饰器自动映射 axon_quant 异常为语义化 HTTP 状态码"""

    def test_data_error_maps_to_400(self):
        """DataError → HTTP 400"""
        from axon_quant import DataError

        @handle_worker_exceptions("数据操作")
        def func():
            raise DataError("invalid symbol")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "data_error"
        assert "invalid symbol" in exc_info.value.detail["message"]

    def test_oms_error_maps_to_409(self):
        """OmsError → HTTP 409"""
        from axon_quant import OmsError

        @handle_worker_exceptions("订单操作")
        def func():
            raise OmsError("duplicate idempotency key")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "oms_conflict"

    def test_exchange_error_maps_to_502(self):
        """ExchangeError → HTTP 502"""
        from axon_quant import ExchangeError

        @handle_worker_exceptions("交易所操作")
        def func():
            raise ExchangeError("binance api timeout")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 502
        assert exc_info.value.detail["code"] == "exchange_error"

    def test_risk_error_maps_to_403(self):
        """RiskError → HTTP 403"""
        from axon_quant.risk import RiskError

        @handle_worker_exceptions("风控操作")
        def func():
            raise RiskError("position limit exceeded")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "risk_rejected"

    def test_backtest_error_maps_to_500(self):
        """BacktestError → HTTP 500"""
        from axon_quant import BacktestError

        @handle_worker_exceptions("回测操作")
        def func():
            raise BacktestError("engine crashed")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "backtest_error"

    def test_axon_error_base_maps_to_500(self):
        """AxonError 基类 → HTTP 500 (兜底)"""
        from axon_quant import AxonError

        @handle_worker_exceptions("通用操作")
        def func():
            raise AxonError("unknown axon error")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "axon_error"

    def test_inference_error_maps_to_500(self):
        """InferenceError → HTTP 500"""
        from axon_quant import InferenceError

        @handle_worker_exceptions("推理操作")
        def func():
            raise InferenceError("model not loaded")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "inference_error"

    def test_defi_error_maps_to_500(self):
        """DefiError → HTTP 500"""
        from axon_quant import DefiError

        @handle_worker_exceptions("DeFi操作")
        def func():
            raise DefiError("protocol error")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "defi_error"

    def test_non_axon_quant_exception_still_500(self):
        """非 axon_quant 异常仍走通用 500"""

        @handle_worker_exceptions("测试操作")
        def func():
            raise ValueError("plain python error")

        with pytest.raises(HTTPException) as exc_info:
            func()
        assert exc_info.value.status_code == 500
        # 非 axon_quant 异常 detail 为纯字符串(非映射格式)
        assert "plain python error" in exc_info.value.detail

    def test_async_data_error_maps_to_400(self):
        """异步函数：DataError → HTTP 400"""
        from axon_quant import DataError

        @handle_worker_exceptions("异步数据操作")
        async def async_func():
            raise DataError("async bad request")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(async_func())
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "data_error"
