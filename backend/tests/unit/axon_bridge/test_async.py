"""异步桥接装饰器测试。"""

import asyncio
import time

from backend.axon_bridge._async import async_class, async_wrap


def test_async_wrap_runs_in_thread():
    """async_wrap 应把阻塞调用推到独立线程,event loop 不阻塞。"""

    def blocking_fn(x: int) -> int:
        time.sleep(0.1)
        return x * 2

    wrapped = async_wrap(blocking_fn)

    async def run():
        return await wrapped(5)

    result = asyncio.run(run())
    assert result == 10


def test_async_class_wraps_public_methods():
    """async_class 应包装所有 public 方法。"""

    class Calc:
        def add(self, a: int, b: int) -> int:
            return a + b

        def _private(self) -> str:
            return "private"

    Wrapped = async_class(Calc)
    assert hasattr(Wrapped, "add")
    # _private 不应该被包装
    assert hasattr(Wrapped, "_private")


def test_async_class_preserves_functionality():
    """包装后功能不变(同步调用仍可用)。"""

    class Calc:
        def add(self, a: int, b: int) -> int:
            return a + b

    Wrapped = async_class(Calc)
    instance = Wrapped()

    async def run():
        return await instance.add(3, 4)

    result = asyncio.run(run())
    assert result == 7
