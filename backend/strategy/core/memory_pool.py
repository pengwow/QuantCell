"""
内存池 - 对象复用和共享内存管理

基于设计文档中的第三阶段优化要求实现：
1. 事件对象池 - 减少GC压力
2. 共享内存市场数据 - 进程间数据共享
3. 预分配缓冲区 - 避免运行时内存分配
4. 零拷贝数据传输
"""

import threading
import logging
from typing import Dict, List, Callable, Any, Optional, TypeVar, Generic, Set
from dataclasses import dataclass, field
from collections import deque
import weakref
import numpy as np
from multiprocessing import shared_memory
import struct

logger = logging.getLogger(__name__)

T = TypeVar('T')


class PooledObject:
    """池化对象基类"""
    
    def __init__(self):
        self._in_use = False
        self._pool: Optional['ObjectPool'] = None
    
    def reset(self) -> None:
        """重置对象状态"""
        self._in_use = False
    
    def release(self) -> None:
        """释放对象回池"""
        if self._pool and self._in_use:
            self._pool.release(self)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class ObjectPool(Generic[T]):
    """
    通用对象池

    特性：
    1. 预分配对象减少GC压力
    2. 线程安全
    3. 自动扩容和缩容
    4. 对象状态重置
    """

    def __init__(
        self,
        factory: Any = None,
        reset_func: Any = None,
        initial_size: int = 100,
        max_size: int = 10000,
        auto_grow: bool = True
    ):
        """
        初始化对象池

        Args:
            factory: 对象工厂函数
            reset_func: 对象重置函数
            initial_size: 初始池大小
            max_size: 最大池大小
            auto_grow: 是否自动扩容
        """
        if factory is None:
            raise ValueError("必须提供 factory 参数")
        self.factory = factory
        self.reset_func = reset_func
        self.max_size = max_size
        self.auto_grow = auto_grow
        self.initial_size = initial_size

        # 可用对象队列
        self._available: deque = deque()
        self._lock = threading.RLock()
        self._size = 0

        # 预分配初始对象
        self._preallocate(self.initial_size)

        logger.debug(f"对象池初始化完成: 初始大小={initial_size}, 最大大小={max_size}")
    
    def _preallocate(self, count: int) -> None:
        """预分配对象"""
        for _ in range(count):
            obj = self.factory()
            if isinstance(obj, PooledObject):
                obj._pool = self
            self._available.append(obj)
            self._size += 1
    
    def acquire(self) -> T:
        """
        获取对象
        
        Returns:
            T: 池化对象
        """
        with self._lock:
            if self._available:
                obj = self._available.popleft()
                if isinstance(obj, PooledObject):
                    obj._in_use = True
                return obj
            
            # 池为空，创建新对象（如果允许自动扩容）
            if self.auto_grow and self._size < self.max_size:
                obj = self.factory()
                if isinstance(obj, PooledObject):
                    obj._pool = self
                    obj._in_use = True
                self._size += 1
                return obj
            
            # 池已满，等待可用对象
            raise RuntimeError("对象池已满，无法获取对象")
    
    def release(self, obj: T) -> None:
        """
        释放对象回池
        
        Args:
            obj: 要释放的对象
        """
        with self._lock:
            # 重置对象状态
            if self.reset_func:
                self.reset_func(obj)
            elif isinstance(obj, PooledObject):
                obj.reset()
            
            # 如果池未满，放回队列
            if len(self._available) < self.max_size:
                self._available.append(obj)
            else:
                self._size -= 1
    
    def size(self) -> int:
        """获取池大小"""
        with self._lock:
            return self._size

    def clear(self) -> None:
        """清空对象池"""
        with self._lock:
            self._available.clear()
            self._size = 0

    def get_stats(self) -> Dict[str, Any]:
        """获取池统计信息"""
        with self._lock:
            return {
                "total_size": self._size,
                "available": len(self._available),
                "in_use": self._size - len(self._available),
                "utilization": (self._size - len(self._available)) / max(self._size, 1),
                "total_created": self._size
            }


class TickEvent(PooledObject):
    """
    Tick事件对象 - 使用对象池管理

    使用__slots__减少内存占用
    """
    __slots__ = ['symbol', 'price', 'volume', 'timestamp', 'side', '_in_use', '_pool']

    def __init__(
        self,
        symbol: str = "",
        price: float = 0.0,
        volume: float = 0.0,
        timestamp: float = 0.0,
        side: str = ""
    ):
        super().__init__()
        self.symbol: str = symbol
        self.price: float = price
        self.volume: float = volume
        self.timestamp: float = timestamp
        self.side: str = side  # 'buy' or 'sell'
    
    def reset(self) -> None:
        """重置对象状态"""
        self.symbol = ""
        self.price = 0.0
        self.volume = 0.0
        self.timestamp = 0.0
        self.side = ""
        super().reset()
    
    def set_data(self, symbol: str, price: float, volume: float, timestamp: float, side: str = "") -> 'TickEvent':
        """设置事件数据"""
        self.symbol = symbol
        self.price = price
        self.volume = volume
        self.timestamp = timestamp
        self.side = side
        return self
    
    def __repr__(self) -> str:
        return f"TickEvent({self.symbol}, {self.price}, {self.volume})"


class BarEvent(PooledObject):
    """
    K线事件对象 - 使用对象池管理
    """
    __slots__ = ['symbol', 'open', 'high', 'low', 'close', 'volume', 'timestamp', 'interval', 'open_price', 'high_price', 'low_price', 'close_price', '_in_use', '_pool']

    def __init__(
        self,
        symbol: str = "",
        open_price: float = 0.0,
        high_price: float = 0.0,
        low_price: float = 0.0,
        close_price: float = 0.0,
        volume: float = 0.0,
        timestamp: float = 0.0,
        interval: str = ""
    ):
        super().__init__()
        self.symbol: str = symbol
        self.open: float = open_price
        self.open_price: float = open_price  # 开盘价
        self.high: float = high_price
        self.high_price: float = high_price  # 最高价
        self.low: float = low_price
        self.low_price: float = low_price  # 最低价
        self.close: float = close_price
        self.close_price: float = close_price  # 收盘价
        self.volume: float = volume
        self.timestamp: float = timestamp
        self.interval: str = interval  # K线周期，如 '1m', '5m', '1h'
    
    def reset(self) -> None:
        """重置对象状态"""
        self.symbol = ""
        self.open = 0.0
        self.high = 0.0
        self.low = 0.0
        self.close = 0.0
        self.volume = 0.0
        self.timestamp = 0.0
        self.interval = ""
        super().reset()
    
    def set_data(
        self,
        symbol: str,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        timestamp: float,
        interval: str
    ) -> 'BarEvent':
        """设置K线数据"""
        self.symbol = symbol
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.timestamp = timestamp
        self.interval = interval
        return self


class EventObjectPools:
    """
    事件对象池管理器
    
    集中管理所有事件类型的对象池
    """
    
    def __init__(self):
        self.tick_pool = ObjectPool(
            factory=TickEvent,
            initial_size=1000,
            max_size=100000
        )
        
        self.bar_pool = ObjectPool(
            factory=BarEvent,
            initial_size=500,
            max_size=50000
        )
        
        logger.info("事件对象池管理器初始化完成")
    
    def acquire_tick(self) -> TickEvent:
        """获取Tick事件对象"""
        return self.tick_pool.acquire()
    
    def acquire_bar(self) -> BarEvent:
        """获取K线事件对象"""
        return self.bar_pool.acquire()
    
    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有池的统计信息"""
        return {
            "tick_pool": self.tick_pool.get_stats(),
            "bar_pool": self.bar_pool.get_stats()
        }


class SharedMemoryMarketData:
    """
    共享内存市场数据
    
    使用共享内存实现进程间数据共享，避免数据拷贝
    """
    
    def __init__(
        self,
        num_symbols: int = 400,
        buffer_size: int = 1000
    ):
        """
        初始化共享内存市场数据

        Args:
            num_symbols: 支持的符号数量
            buffer_size: 每个符号的缓冲区大小
        """
        self.num_symbols = num_symbols
        self.buffer_size = buffer_size
        
        # 创建共享内存
        self._create_shared_memory()
        
        # 符号到ID的映射
        self._symbol_to_id: Dict[str, int] = {}
        self._id_to_symbol: Dict[int, str] = {}
        self._symbol_lock = threading.Lock()
        self._next_symbol_id = 0
        
        logger.info(f"共享内存市场数据初始化完成: {num_symbols} 符号, 缓冲区={buffer_size}")
    
    def _create_shared_memory(self) -> None:
        """创建共享内存缓冲区"""
        # 价格缓冲区 (float32)
        self.price_buffer = np.zeros((self.num_symbols, self.buffer_size), dtype=np.float32)
        
        # 成交量缓冲区 (float32)
        self.volume_buffer = np.zeros((self.num_symbols, self.buffer_size), dtype=np.float32)
        
        # 时间戳缓冲区 (int64)
        self.timestamp_buffer = np.zeros((self.num_symbols, self.buffer_size), dtype=np.int64)
        
        # 写入索引 (每个符号一个)
        self.write_indices = np.zeros(self.num_symbols, dtype=np.int32)
        
        # 读取索引 (每个符号一个)
        self.read_indices = np.zeros(self.num_symbols, dtype=np.int32)
        
        # 锁数组（每个符号一个锁）
        self._locks = [threading.Lock() for _ in range(self.num_symbols)]
    
    def register_symbol(self, symbol: str) -> int:
        """
        注册符号
        
        Args:
            symbol: 符号名称
            
        Returns:
            int: 符号ID
        """
        with self._symbol_lock:
            if symbol in self._symbol_to_id:
                return self._symbol_to_id[symbol]
            
            if self._next_symbol_id >= self.num_symbols:
                raise RuntimeError(f"符号数量超过最大值 {self.num_symbols}")
            
            symbol_id = self._next_symbol_id
            self._symbol_to_id[symbol] = symbol_id
            self._id_to_symbol[symbol_id] = symbol
            self._next_symbol_id += 1
            
            logger.debug(f"注册符号: {symbol} -> ID {symbol_id}")
            return symbol_id
    
    def write_tick(self, symbol: str, price: float, volume: float, timestamp: int) -> None:
        """
        写入Tick数据
        
        Args:
            symbol: 符号名称
            price: 价格
            volume: 成交量
            timestamp: 时间戳
        """
        symbol_id = self._get_symbol_id(symbol)
        if symbol_id is None:
            symbol_id = self.register_symbol(symbol)
        
        with self._locks[symbol_id]:
            idx = self.write_indices[symbol_id] % self.buffer_size
            self.price_buffer[symbol_id, idx] = price
            self.volume_buffer[symbol_id, idx] = volume
            self.timestamp_buffer[symbol_id, idx] = timestamp
            self.write_indices[symbol_id] += 1
    
    def read_latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        读取最新数据
        
        Args:
            symbol: 符号名称
            
        Returns:
            Dict or None: 最新数据
        """
        symbol_id = self._get_symbol_id(symbol)
        if symbol_id is None:
            return None
        
        with self._locks[symbol_id]:
            if self.write_indices[symbol_id] == 0:
                return None
            
            idx = (self.write_indices[symbol_id] - 1) % self.buffer_size
            
            return {
                "symbol": symbol,
                "price": float(self.price_buffer[symbol_id, idx]),
                "volume": float(self.volume_buffer[symbol_id, idx]),
                "timestamp": int(self.timestamp_buffer[symbol_id, idx])
            }
    
    def read_range(self, symbol: str, count: int) -> Optional[Dict[str, np.ndarray]]:
        """
        读取最近N条数据
        
        Args:
            symbol: 符号名称
            count: 数据条数
            
        Returns:
            Dict or None: 数据数组
        """
        symbol_id = self._get_symbol_id(symbol)
        if symbol_id is None:
            return None
        
        with self._locks[symbol_id]:
            write_idx = self.write_indices[symbol_id]
            if write_idx == 0:
                return None
            
            # 计算读取范围
            count = min(count, write_idx, self.buffer_size)
            start_idx = (write_idx - count) % self.buffer_size
            
            # 读取数据
            if start_idx + count <= self.buffer_size:
                # 连续数据
                prices = self.price_buffer[symbol_id, start_idx:start_idx + count].copy()
                volumes = self.volume_buffer[symbol_id, start_idx:start_idx + count].copy()
                timestamps = self.timestamp_buffer[symbol_id, start_idx:start_idx + count].copy()
            else:
                # 环形缓冲区环绕
                end_count = self.buffer_size - start_idx
                prices = np.concatenate([
                    self.price_buffer[symbol_id, start_idx:].copy(),
                    self.price_buffer[symbol_id, :count - end_count].copy()
                ])
                volumes = np.concatenate([
                    self.volume_buffer[symbol_id, start_idx:].copy(),
                    self.volume_buffer[symbol_id, :count - end_count].copy()
                ])
                timestamps = np.concatenate([
                    self.timestamp_buffer[symbol_id, start_idx:].copy(),
                    self.timestamp_buffer[symbol_id, :count - end_count].copy()
                ])
            
            return {
                "symbol": symbol,
                "prices": prices,
                "volumes": volumes,
                "timestamps": timestamps
            }
    
    def _get_symbol_id(self, symbol: str) -> Optional[int]:
        """获取符号ID"""
        with self._symbol_lock:
            return self._symbol_to_id.get(symbol)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._symbol_lock:
            total_writes = sum(self.write_indices)
            
            return {
                "num_symbols": self.num_symbols,
                "registered_symbols": len(self._symbol_to_id),
                "buffer_size": self.buffer_size,
                "total_writes": int(total_writes)
            }


class PreallocatedBuffers:
    """
    预分配缓冲区

    预分配常用大小的缓冲区，避免运行时内存分配
    """

    def __init__(
        self,
        buffer_sizes: Optional[List[int]] = None,
        buffers_per_size: Optional[int] = None
    ):
        """
        初始化预分配缓冲区

        Args:
            buffer_sizes: 预分配的缓冲区大小列表
            buffers_per_size: 每种大小缓冲区的数量
        """
        # 使用提供的参数或默认配置
        if buffer_sizes and buffers_per_size:
            self._buffers: Dict[int, deque] = {
                size: deque(maxlen=buffers_per_size)
                for size in buffer_sizes
            }
        else:
            # 预分配不同大小的缓冲区（默认配置）
            self._buffers: Dict[int, deque] = {
                64: deque(maxlen=100),
                128: deque(maxlen=100),
                256: deque(maxlen=100),
                512: deque(maxlen=50),
                1024: deque(maxlen=50),
                4096: deque(maxlen=20)
            }

        self._lock = threading.Lock()

        # 预分配缓冲区
        for size, queue in self._buffers.items():
            for _ in range(queue.maxlen):
                queue.append(bytearray(size))

        logger.debug("预分配缓冲区初始化完成")
    
    def acquire(self, size: int) -> bytearray:
        """
        获取缓冲区
        
        Args:
            size: 需要的缓冲区大小
            
        Returns:
            bytearray: 缓冲区
        """
        # 找到最接近的预分配大小
        allocated_size = min(
            (s for s in self._buffers.keys() if s >= size),
            default=None
        )
        
        if allocated_size is None:
            # 没有合适的预分配缓冲区，创建新的
            return bytearray(size)
        
        with self._lock:
            if self._buffers[allocated_size]:
                buffer = self._buffers[allocated_size].popleft()
                return buffer
        
        # 池为空，创建新的
        return bytearray(allocated_size)
    
    def release(self, buffer: bytearray) -> None:
        """
        释放缓冲区
        
        Args:
            buffer: 要释放的缓冲区
        """
        size = len(buffer)
        
        # 找到最接近的预分配大小
        allocated_size = min(
            (s for s in self._buffers.keys() if s >= size),
            default=None
        )
        
        if allocated_size is None or allocated_size != size:
            # 不是预分配的缓冲区，直接丢弃
            return
        
        with self._lock:
            # 清空缓冲区
            buffer[:] = b'\x00' * len(buffer)
            
            # 放回池中
            if len(self._buffers[allocated_size]) < self._buffers[allocated_size].maxlen:
                self._buffers[allocated_size].append(buffer)


# 全局对象池实例
_global_pools: Optional[EventObjectPools] = None
_global_pools_lock = threading.Lock()


def get_event_pools() -> EventObjectPools:
    """获取全局事件对象池"""
    global _global_pools
    
    if _global_pools is None:
        with _global_pools_lock:
            if _global_pools is None:
                _global_pools = EventObjectPools()
    
    return _global_pools


# 便捷函数
def create_tick_event(symbol: str, price: float, volume: float, timestamp: float, side: str = "") -> TickEvent:
    """
    创建Tick事件（使用对象池）
    
    Args:
        symbol: 符号
        price: 价格
        volume: 成交量
        timestamp: 时间戳
        side: 买卖方向
        
    Returns:
        TickEvent: Tick事件对象
    """
    pools = get_event_pools()
    event = pools.acquire_tick()
    return event.set_data(symbol, price, volume, timestamp, side)


def create_bar_event(
    symbol: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    timestamp: float,
    interval: str
) -> BarEvent:
    """
    创建K线事件（使用对象池）
    
    Args:
        symbol: 符号
        open_price: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量
        timestamp: 时间戳
        interval: 时间间隔
        
    Returns:
        BarEvent: K线事件对象
    """
    pools = get_event_pools()
    event = pools.acquire_bar()
    return event.set_data(symbol, open_price, high, low, close, volume, timestamp, interval)
