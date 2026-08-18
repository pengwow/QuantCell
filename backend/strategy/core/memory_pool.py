"""内存池模块 — 高性能对象池和共享内存数据结构"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class PooledObject:
    """池化对象基类"""

    pass


class ObjectPool:
    """线程安全的对象池"""

    def __init__(
        self,
        factory: Callable[[], Any],
        reset_func: Callable[[Any], Any],
        initial_size: int = 10,
        max_size: int = 100,
    ):
        self.initial_size = initial_size
        self.max_size = max_size
        self._max_size = max_size
        self._factory = factory
        self._reset_func = reset_func
        self._available: deque = deque()
        self._lock = threading.Lock()
        self._total_created = 0
        self._total_acquired = 0
        self._total_released = 0

        # 预创建初始对象
        for _ in range(initial_size):
            self._available.append(factory())
        self._total_created = initial_size
        self._size = initial_size

    def acquire(self) -> Any:
        """获取对象"""
        with self._lock:
            if self._available:
                obj = self._available.popleft()
            else:
                obj = self._factory()
                self._total_created += 1
                self._size += 1
            self._total_acquired += 1
            return obj

    def release(self, obj: Any) -> None:
        """释放对象"""
        with self._lock:
            if len(self._available) < self._max_size:
                obj = self._reset_func(obj)
                self._available.append(obj)
            self._total_released += 1

    def size(self) -> int:
        """获取池大小（总容量）"""
        return self._size

    def clear(self) -> None:
        """清空池"""
        with self._lock:
            self._available.clear()

    def get_stats(self) -> dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return {
                "available": len(self._available),
                "in_use": self._total_acquired - self._total_released,
                "total_created": self._total_created,
                "total_acquired": self._total_acquired,
                "total_released": self._total_released,
            }


@dataclass(slots=True, eq=True)
class TickEvent:
    """Tick 事件"""

    symbol: str
    price: float
    volume: float
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "volume": self.volume,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TickEvent:
        return cls(
            symbol=data["symbol"],
            price=data["price"],
            volume=data["volume"],
            timestamp=data["timestamp"],
        )


@dataclass(slots=True, eq=True)
class BarEvent:
    """K 线事件"""

    symbol: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "volume": self.volume,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BarEvent:
        return cls(
            symbol=data["symbol"],
            open_price=data.get("open", data.get("open_price", 0.0)),
            high_price=data.get("high", data.get("high_price", 0.0)),
            low_price=data.get("low", data.get("low_price", 0.0)),
            close_price=data.get("close", data.get("close_price", 0.0)),
            volume=data.get("volume", 0.0),
            timestamp=data.get("timestamp", time.time()),
        )

    def typical_price(self) -> float:
        """计算典型价格"""
        return (self.high_price + self.low_price + self.close_price) / 3

    def price_range(self) -> float:
        """计算价格范围"""
        return self.high_price - self.low_price


class SharedMemoryMarketData:
    """共享内存市场数据存储"""

    def __init__(self, buffer_size: int = 1024 * 1024, num_symbols: int = 100):
        self.buffer_size = buffer_size
        self.num_symbols = num_symbols
        self._tick_data: dict[str, TickEvent] = {}
        self._bar_data: dict[str, BarEvent] = {}
        self._lock = threading.Lock()

    def write_tick(self, tick: TickEvent) -> None:
        """写入 Tick 数据"""
        with self._lock:
            self._tick_data[tick.symbol] = tick

    def read_tick(self, symbol: str) -> TickEvent | None:
        """读取 Tick 数据"""
        with self._lock:
            return self._tick_data.get(symbol)

    def write_bar(self, bar: BarEvent) -> None:
        """写入 Bar 数据"""
        with self._lock:
            self._bar_data[bar.symbol] = bar

    def read_bar(self, symbol: str) -> BarEvent | None:
        """读取 Bar 数据"""
        with self._lock:
            return self._bar_data.get(symbol)

    def get_all_symbols(self) -> list[str]:
        """获取所有交易对"""
        with self._lock:
            return list(self._tick_data.keys())

    def clear_symbol(self, symbol: str) -> None:
        """清除特定交易对数据"""
        with self._lock:
            self._tick_data.pop(symbol, None)
            self._bar_data.pop(symbol, None)

    def clear_all(self) -> None:
        """清除所有数据"""
        with self._lock:
            self._tick_data.clear()
            self._bar_data.clear()


class PreallocatedBuffers:
    """预分配缓冲区池"""

    def __init__(self, buffer_sizes: list[int], buffers_per_size: int = 10):
        self.buffer_sizes = sorted(buffer_sizes)
        self._pools: dict[int, deque] = {}
        self._lock = threading.Lock()

        for size in self.buffer_sizes:
            self._pools[size] = deque([bytearray(size) for _ in range(buffers_per_size)])

    def acquire(self, min_size: int) -> bytearray:
        """获取缓冲区"""
        with self._lock:
            for size in self.buffer_sizes:
                if size >= min_size:
                    if self._pools[size]:
                        return self._pools[size].popleft()
                    # 创建新缓冲区
                    return bytearray(size)
            # 没有匹配的大小，创建新的
            return bytearray(min_size)

    def release(self, buf: bytearray) -> None:
        """释放缓冲区"""
        with self._lock:
            buf_size = len(buf)
            if buf_size in self._pools:
                self._pools[buf_size].append(buf)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {"buffer_pools": {size: len(pool) for size, pool in self._pools.items()}}


__all__ = [
    "BarEvent",
    "ObjectPool",
    "PooledObject",
    "PreallocatedBuffers",
    "SharedMemoryMarketData",
    "TickEvent",
]
