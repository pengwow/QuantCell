"""
异常模拟器

模拟真实交易场景中的各类异常情况，如网络延迟、数据中断、策略错误等。
"""

import asyncio
import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
from loguru import logger

from .config import ExceptionSimulationConfig


class ExceptionType(Enum):
    """异常类型枚举"""
    NETWORK_DELAY = auto()      # 网络延迟
    DISCONNECT = auto()         # 连接断开
    DATA_CORRUPTION = auto()    # 数据损坏
    STRATEGY_ERROR = auto()     # 策略错误
    TIMEOUT = auto()            # 超时


@dataclass
class SimulatedException:
    """模拟的异常"""
    exception_type: ExceptionType
    timestamp: float
    description: str
    duration_ms: int = 0
    recovered: bool = False


class ExceptionSimulator:
    """异常模拟器"""
    
    def __init__(self, config: ExceptionSimulationConfig):
        self.config = config
        self._running = False
        self._exceptions_history: List[SimulatedException] = []
        self._active_exceptions: Set[ExceptionType] = set()
        self._tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        
        # 回调函数
        self._exception_handlers: Dict[ExceptionType, List[Callable]] = {
            exc_type: [] for exc_type in ExceptionType
        }
        
    def register_exception_handler(
        self, 
        exc_type: ExceptionType, 
        handler: Callable[[SimulatedException], None]
    ):
        """注册异常处理器"""
        self._exception_handlers[exc_type].append(handler)
        
    def unregister_exception_handler(
        self, 
        exc_type: ExceptionType, 
        handler: Callable[[SimulatedException], None]
    ):
        """注销异常处理器"""
        if handler in self._exception_handlers[exc_type]:
            self._exception_handlers[exc_type].remove(handler)
            
    async def start(self):
        """启动异常模拟"""
        if self._running or not self.config.enabled:
            return
            
        self._running = True
        self._stop_event.clear()
        
        # 启动各类异常模拟任务
        if self.config.network_delay_probability > 0:
            self._tasks.append(asyncio.create_task(self._network_delay_simulator()))
            
        if self.config.disconnect_interval_ms > 0:
            self._tasks.append(asyncio.create_task(self._disconnect_simulator()))
            
        if self.config.data_corruption_probability > 0:
            self._tasks.append(asyncio.create_task(self._data_corruption_simulator()))
            
        if self.config.strategy_error_probability > 0:
            self._tasks.append(asyncio.create_task(self._strategy_error_simulator()))
            
        logger.info("Exception simulator started")
        
    async def stop(self):
        """停止异常模拟"""
        if not self._running:
            return
            
        self._running = False
        self._stop_event.set()
        
        # 取消所有任务
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        
        logger.info("Exception simulator stopped")
        
    async def _network_delay_simulator(self):
        """网络延迟模拟器"""
        while not self._stop_event.is_set():
            try:
                # 随机等待
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=random.uniform(1.0, 5.0)
                )
            except asyncio.TimeoutError:
                # 检查是否应该触发延迟
                if random.random() < self.config.network_delay_probability:
                    await self._trigger_network_delay()
                    
    async def _trigger_network_delay(self):
        """触发网络延迟"""
        delay_ms = self.config.network_delay_ms
        
        exc = SimulatedException(
            exception_type=ExceptionType.NETWORK_DELAY,
            timestamp=time.time(),
            description=f"Network delay: {delay_ms}ms",
            duration_ms=delay_ms,
        )
        
        self._exceptions_history.append(exc)
        self._active_exceptions.add(ExceptionType.NETWORK_DELAY)
        
        logger.warning(f"Simulating network delay: {delay_ms}ms")
        
        # 通知处理器
        await self._notify_handlers(exc)
        
        # 模拟延迟
        await asyncio.sleep(delay_ms / 1000.0)
        
        exc.recovered = True
        self._active_exceptions.discard(ExceptionType.NETWORK_DELAY)
        
        logger.info("Network delay recovered")
        
    async def _disconnect_simulator(self):
        """连接断开模拟器"""
        while not self._stop_event.is_set():
            try:
                # 等待断开间隔
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.disconnect_interval_ms / 1000.0
                )
            except asyncio.TimeoutError:
                await self._trigger_disconnect()
                
    async def _trigger_disconnect(self):
        """触发连接断开"""
        duration_ms = self.config.disconnect_duration_ms
        
        exc = SimulatedException(
            exception_type=ExceptionType.DISCONNECT,
            timestamp=time.time(),
            description=f"Connection disconnected for {duration_ms}ms",
            duration_ms=duration_ms,
        )
        
        self._exceptions_history.append(exc)
        self._active_exceptions.add(ExceptionType.DISCONNECT)
        
        logger.warning(f"Simulating connection disconnect for {duration_ms}ms")
        
        # 通知处理器
        await self._notify_handlers(exc)
        
        # 模拟断开时间
        await asyncio.sleep(duration_ms / 1000.0)
        
        exc.recovered = True
        self._active_exceptions.discard(ExceptionType.DISCONNECT)
        
        logger.info("Connection recovered")
        
    async def _data_corruption_simulator(self):
        """数据损坏模拟器"""
        while not self._stop_event.is_set():
            try:
                # 随机等待
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=random.uniform(0.5, 2.0)
                )
            except asyncio.TimeoutError:
                # 检查是否应该触发数据损坏
                if random.random() < self.config.data_corruption_probability:
                    await self._trigger_data_corruption()
                    
    async def _trigger_data_corruption(self):
        """触发数据损坏"""
        exc = SimulatedException(
            exception_type=ExceptionType.DATA_CORRUPTION,
            timestamp=time.time(),
            description="Data corruption detected",
            duration_ms=0,
        )
        
        self._exceptions_history.append(exc)
        
        logger.warning("Simulating data corruption")
        
        # 通知处理器
        await self._notify_handlers(exc)
        
    async def _strategy_error_simulator(self):
        """策略错误模拟器"""
        while not self._stop_event.is_set():
            try:
                # 随机等待
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=random.uniform(5.0, 30.0)
                )
            except asyncio.TimeoutError:
                # 检查是否应该触发策略错误
                if random.random() < self.config.strategy_error_probability:
                    await self._trigger_strategy_error()
                    
    async def _trigger_strategy_error(self):
        """触发策略错误"""
        error_types = [
            "Calculation error",
            "Division by zero",
            "Index out of range",
            "Invalid parameter",
            "Memory limit exceeded",
        ]
        
        exc = SimulatedException(
            exception_type=ExceptionType.STRATEGY_ERROR,
            timestamp=time.time(),
            description=f"Strategy error: {random.choice(error_types)}",
            duration_ms=0,
        )
        
        self._exceptions_history.append(exc)
        self._active_exceptions.add(ExceptionType.STRATEGY_ERROR)
        
        logger.warning(f"Simulating strategy error: {exc.description}")
        
        # 通知处理器
        await self._notify_handlers(exc)
        
        # 策略错误通常需要手动恢复
        # 这里模拟自动恢复
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        exc.recovered = True
        self._active_exceptions.discard(ExceptionType.STRATEGY_ERROR)
        
        logger.info("Strategy error recovered")
        
    async def _notify_handlers(self, exc: SimulatedException):
        """通知异常处理器"""
        handlers = self._exception_handlers.get(exc.exception_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(exc)
                else:
                    handler(exc)
            except Exception as e:
                logger.error(f"Exception handler error: {e}")
                
    def should_corrupt_data(self) -> bool:
        """检查是否应该损坏数据（供数据推送使用）"""
        if not self.config.enabled:
            return False
        return random.random() < self.config.data_corruption_probability
        
    def corrupt_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """损坏数据（模拟数据错误）"""
        corrupted = data.copy()
        
        # 随机选择损坏方式
        corruption_type = random.choice([
            "price_zero",
            "price_negative",
            "volume_zero",
            "timestamp_invalid",
            "missing_field",
        ])
        
        if corruption_type == "price_zero":
            if "close" in corrupted:
                corrupted["close"] = 0
        elif corruption_type == "price_negative":
            if "close" in corrupted:
                corrupted["close"] = -abs(corrupted.get("close", 100))
        elif corruption_type == "volume_zero":
            if "volume" in corrupted:
                corrupted["volume"] = 0
        elif corruption_type == "timestamp_invalid":
            if "timestamp" in corrupted:
                corrupted["timestamp"] = "invalid_timestamp"
        elif corruption_type == "missing_field":
            if corrupted:
                key = random.choice(list(corrupted.keys()))
                del corrupted[key]
                
        return corrupted
        
    def get_active_exceptions(self) -> Set[ExceptionType]:
        """获取当前活跃的异常"""
        return self._active_exceptions.copy()
        
    def get_exception_history(self) -> List[SimulatedException]:
        """获取异常历史"""
        return self._exceptions_history.copy()
        
    def get_summary(self) -> Dict[str, Any]:
        """获取异常模拟摘要"""
        total_exceptions = len(self._exceptions_history)
        
        by_type = {}
        for exc in self._exceptions_history:
            exc_type = exc.exception_type.name
            by_type[exc_type] = by_type.get(exc_type, 0) + 1
            
        return {
            "enabled": self.config.enabled,
            "total_exceptions": total_exceptions,
            "active_exceptions": len(self._active_exceptions),
            "by_type": by_type,
        }
        
    def clear_history(self):
        """清除异常历史"""
        self._exceptions_history.clear()


class DelayInjector:
    """延迟注入器"""
    
    def __init__(self, simulator: ExceptionSimulator):
        self.simulator = simulator
        
    async def inject_delay(self):
        """注入延迟"""
        if ExceptionType.NETWORK_DELAY in self.simulator.get_active_exceptions():
            # 已经在延迟中，等待恢复
            while ExceptionType.NETWORK_DELAY in self.simulator.get_active_exceptions():
                await asyncio.sleep(0.1)
        elif self.simulator.config.enabled and random.random() < self.simulator.config.network_delay_probability:
            # 触发新的延迟
            delay_ms = self.simulator.config.network_delay_ms
            await asyncio.sleep(delay_ms / 1000.0)
            
    def should_disconnect(self) -> bool:
        """检查是否应该断开连接"""
        if not self.simulator.config.enabled:
            return False
        return ExceptionType.DISCONNECT in self.simulator.get_active_exceptions()
