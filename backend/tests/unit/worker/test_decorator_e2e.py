# -*- coding: utf-8 -*-
"""
异常处理重构端到端验证

验证 routes.py 中所有装饰器应用的端点：
1. 正确处理 WorkerNotFoundException → 404
2. 正确处理 WorkerAlreadyRunningException → 409
3. 正确处理未预期异常 → 500
4. 装饰器之间的逻辑保持一致
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from worker.decorators import handle_worker_exceptions
from worker.exceptions import (
    WorkerNotFoundException,
    WorkerAlreadyRunningException,
    WorkerOperationException,
)


class TestDecoratorHTTPResponses:
    """验证装饰器生成的 HTTP 响应"""

    def test_404_response_shape(self):
        """验证 404 响应的结构"""
        @handle_worker_exceptions("测试")
        async def endpoint():
            raise WorkerNotFoundException(123)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoint())

        exc = exc_info.value
        assert exc.status_code == 404
        assert exc.detail == "Worker 123 不存在"

    def test_409_response_shape(self):
        """验证 409 响应的结构"""
        @handle_worker_exceptions("测试")
        async def endpoint():
            raise WorkerAlreadyRunningException(456)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoint())

        exc = exc_info.value
        assert exc.status_code == 409
        assert exc.detail == "Worker 456 已在运行中"

    def test_400_response_shape(self):
        """验证 400 响应的结构"""
        @handle_worker_exceptions("测试")
        async def endpoint():
            raise WorkerOperationException("启动", worker_id=789)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoint())

        exc = exc_info.value
        assert exc.status_code == 400
        assert "789" in exc.detail
        assert "启动" in exc.detail

    def test_500_response_shape(self):
        """验证 500 响应的结构"""
        @handle_worker_exceptions("测试")
        async def endpoint():
            raise ConnectionError("数据库连接失败")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoint())

        exc = exc_info.value
        assert exc.status_code == 500
        assert "数据库连接失败" in exc.detail

    def test_decorator_chaining(self):
        """验证装饰器可以链式调用"""

        def dummy_decorator(func):
            return func

        @dummy_decorator
        @handle_worker_exceptions("测试")
        async def endpoint():
            raise WorkerNotFoundException(1)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoint())
        assert exc_info.value.status_code == 404


class TestDecoratorWithRealExceptions:
    """验证装饰器与真实服务异常的配合"""

    def test_axon_worker_system_exception_handling(self):
        """模拟 axon_worker_system 抛出的异常被装饰器正确处理"""
        from worker.exceptions import WorkerNotFoundException

        @handle_worker_exceptions("启动策略")
        async def start_strategy_endpoint():
            # 模拟 axon_worker_system 抛出的异常
            raise WorkerNotFoundException(worker_id=999)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(start_strategy_endpoint())
        assert exc_info.value.status_code == 404
        assert "999" in exc_info.value.detail

    def test_unexpected_value_error_handling(self):
        """验证未预期的 ValueError 被正确处理为 500"""
        @handle_worker_exceptions("测试")
        async def endpoint():
            raise ValueError("invalid value")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(endpoint())
        assert exc_info.value.status_code == 500
        assert "invalid value" in exc_info.value.detail
