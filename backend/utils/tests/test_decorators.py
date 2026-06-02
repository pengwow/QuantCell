
# -*- coding: utf-8 -*-
"""
装饰器模块单元测试
测试 decorators.py 中的同步和异步重试装饰器
"""

import time
import asyncio
import pytest
from unittest.mock import patch, MagicMock

from utils.decorators import deco_retry, async_deco_retry


class TestDecoRetry:
    """测试同步重试装饰器"""

    def test_successful_execution_no_retries(self):
        """测试成功执行，无需重试"""
        call_count = 0

        @deco_retry(max_retry=3, delay=0.01)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_eventual_success_after_retries(self):
        """测试在几次失败后最终成功"""
        call_count = 0
        max_failures = 2

        @deco_retry(max_retry=3, delay=0.01)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count <= max_failures:
                raise ValueError(f"Failure #{call_count}")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == max_failures + 1

    def test_failure_after_max_retries(self):
        """测试超过最大重试次数后仍失败"""
        call_count = 0
        max_retry = 3

        @deco_retry(max_retry=max_retry, delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            always_fails()
        assert call_count == max_retry

    def test_retry_delay_used(self):
        """测试是否使用了重试延迟"""
        call_count = 0
        delays = []

        @deco_retry(max_retry=2, delay=0.1)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Fail")
            return "ok"

        start = time.time()
        func()
        end = time.time()
        assert end - start >= 0.1
        assert call_count == 2


class TestAsyncDecoRetry:
    """测试异步重试装饰器"""

    @pytest.mark.asyncio
    async def test_async_successful_execution_no_retries(self):
        """测试异步函数成功执行"""
        call_count = 0

        @async_deco_retry(max_retry=3, delay=0.01)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "async success"

        result = await successful_func()
        assert result == "async success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_eventual_success_after_retries(self):
        """测试异步函数在几次失败后成功"""
        call_count = 0
        max_failures = 2

        @async_deco_retry(max_retry=3, delay=0.01)
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count <= max_failures:
                raise ValueError(f"Async failure #{call_count}")
            return "async success"

        result = await flaky_func()
        assert result == "async success"
        assert call_count == max_failures + 1

    @pytest.mark.asyncio
    async def test_async_failure_after_max_retries(self):
        """测试异步函数超过重试次数后失败"""
        call_count = 0
        max_retry = 3

        @async_deco_retry(max_retry=max_retry, delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails async")

        with pytest.raises(ValueError, match="Always fails async"):
            await always_fails()
        assert call_count == max_retry

    @pytest.mark.asyncio
    async def test_async_retry_delay_used(self):
        """测试异步函数的重试延迟"""
        call_count = 0

        @async_deco_retry(max_retry=2, delay=0.1)
        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Fail")
            return "ok"

        start = time.time()
        await func()
        end = time.time()
        assert end - start >= 0.1
        assert call_count == 2


class TestDecoratorPreservesFunctionMetadata:
    """测试装饰器是否保留函数元数据"""

    def test_sync_preserves_metadata(self):
        """测试同步装饰器保留函数元数据"""
        def original_func(x: int, y: int) -> int:
            """This is a test function"""
            return x + y

        decorated = deco_retry()(original_func)
        assert decorated.__name__ == "original_func"
        assert decorated.__doc__ == "This is a test function"

    def test_async_preserves_metadata(self):
        """测试异步装饰器保留函数元数据"""
        async def original_async_func(x: int) -> int:
            """Async test function"""
            return x * 2

        decorated = async_deco_retry()(original_async_func)
        assert decorated.__name__ == "original_async_func"
        assert decorated.__doc__ == "Async test function"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
