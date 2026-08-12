"""异步桥接装饰器。

axon_quant 内部用 tokio::block_on 转同步,会阻塞 Python 主线程。
此模块提供:
- async_wrap(fn): 把单函数包装为 async 函数(走 asyncio.to_thread)
- async_class(cls): 对类的所有 public 方法应用 async_wrap

注意: 这是装饰器,被包装的方法在调用时会自动变成 async 协程。
调用方需用 `await obj.method(...)` 而非 `obj.method(...)`。
"""
import asyncio
import functools
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def async_wrap(fn: Callable[..., T]) -> Callable[..., "asyncio.Future[T]"]:
    """把 axon_quant 同步阻塞方法包成 asyncio 协程。"""
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(fn, *args, **kwargs)
    return wrapper


def async_class(cls: type) -> type:
    """类装饰器:对类的所有 public 方法应用 async_wrap。"""
    for name in list(dir(cls)):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name, None)
        if callable(attr):
            setattr(cls, name, async_wrap(attr))
    return cls
