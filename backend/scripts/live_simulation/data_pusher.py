"""
数据推送引擎

支持精确控制数据推送速度，模拟真实市场数据流入。
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from loguru import logger

from .models import KlineData, MarketDataMessage, DataType, SimulationState
from .config import PushConfig


@dataclass
class PushMetrics:
    """推送指标"""
    total_data_points: int = 0
    pushed_data_points: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    current_speed: float = 1.0
    avg_latency_ms: float = 0.0
    
    @property
    def progress_percent(self) -> float:
        if self.total_data_points == 0:
            return 0.0
        return (self.pushed_data_points / self.total_data_points) * 100
    
    @property
    def elapsed_seconds(self) -> float:
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()


class DataPusher:
    """数据推送引擎"""
    
    def __init__(self, config: PushConfig):
        self.config = config
        self._data_queue: List[KlineData] = []
        self._state = SimulationState.IDLE
        self._metrics = PushMetrics()
        self._handlers: List[Callable[[MarketDataMessage], None]] = []
        self._task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._current_index = 0
        self._speed_multiplier = config.speed
        
    def register_handler(self, handler: Callable[[MarketDataMessage], None]):
        """注册数据处理器"""
        self._handlers.append(handler)
        
    def unregister_handler(self, handler: Callable[[MarketDataMessage], None]):
        """注销数据处理器"""
        if handler in self._handlers:
            self._handlers.remove(handler)
            
    def load_data(self, data: List[KlineData]):
        """加载数据"""
        # 按时间排序
        self._data_queue = sorted(data, key=lambda x: x.timestamp)
        self._metrics.total_data_points = len(self._data_queue)
        self._current_index = 0
        logger.info(f"Loaded {len(data)} data points for pushing")
        
    def load_multiple_data(self, data_dict: Dict[str, List[KlineData]]):
        """加载多个交易对的数据并合并排序"""
        all_data = []
        for symbol_data in data_dict.values():
            all_data.extend(symbol_data)
        
        # 按时间排序
        self._data_queue = sorted(all_data, key=lambda x: x.timestamp)
        self._metrics.total_data_points = len(self._data_queue)
        self._current_index = 0
        logger.info(f"Loaded {len(self._data_queue)} total data points from {len(data_dict)} symbols")
        
    async def start(self):
        """开始推送"""
        if self._state == SimulationState.RUNNING:
            logger.warning("Data pusher is already running")
            return
            
        if not self._data_queue:
            raise ValueError("No data loaded")
            
        self._state = SimulationState.RUNNING
        self._metrics.start_time = datetime.now()
        self._pause_event.set()
        self._stop_event.clear()
        
        self._task = asyncio.create_task(self._push_loop())
        logger.info(f"Data pusher started with speed {self._speed_multiplier}x")
        
    async def stop(self):
        """停止推送"""
        if self._state != SimulationState.RUNNING:
            return
            
        self._state = SimulationState.STOPPING
        self._stop_event.set()
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
        self._state = SimulationState.STOPPED
        self._metrics.end_time = datetime.now()
        logger.info("Data pusher stopped")
        
    async def pause(self):
        """暂停推送"""
        if self._state == SimulationState.RUNNING:
            self._state = SimulationState.PAUSED
            self._pause_event.clear()
            logger.info("Data pusher paused")
            
    async def resume(self):
        """恢复推送"""
        if self._state == SimulationState.PAUSED:
            self._state = SimulationState.RUNNING
            self._pause_event.set()
            logger.info("Data pusher resumed")
            
    def set_speed(self, speed: float):
        """设置推送速度"""
        if speed <= 0:
            raise ValueError("Speed must be positive")
        self._speed_multiplier = speed
        self._metrics.current_speed = speed
        logger.info(f"Push speed changed to {speed}x")
        
    def jump_to(self, index: int):
        """跳转到指定索引"""
        if index < 0 or index >= len(self._data_queue):
            raise ValueError(f"Invalid index: {index}")
        self._current_index = index
        logger.info(f"Jumped to index {index}")
        
    def jump_to_time(self, timestamp: datetime):
        """跳转到指定时间"""
        for i, data in enumerate(self._data_queue):
            if data.timestamp >= timestamp:
                self._current_index = i
                logger.info(f"Jumped to time {timestamp}")
                return
        logger.warning(f"Timestamp {timestamp} not found in data")
        
    async def _push_loop(self):
        """推送主循环"""
        try:
            while self._current_index < len(self._data_queue) and not self._stop_event.is_set():
                # 等待暂停恢复
                await self._pause_event.wait()
                
                if self._stop_event.is_set():
                    break
                    
                # 获取当前数据点
                kline = self._data_queue[self._current_index]
                
                # 创建市场数据消息
                message = MarketDataMessage.from_kline(kline, source="simulation")
                
                # 推送数据（失败不中断）
                try:
                    await self._push_data(message)
                    self._metrics.pushed_data_points += 1
                except Exception as e:
                    logger.warning(f"Failed to push data point {self._current_index}: {e}")
                
                self._current_index += 1
                
                # 计算下一次推送的延迟
                if self._current_index < len(self._data_queue):
                    delay = self._calculate_delay(kline, self._data_queue[self._current_index])
                    if delay > 0:
                        try:
                            await asyncio.wait_for(
                                self._stop_event.wait(),
                                timeout=delay
                            )
                        except asyncio.TimeoutError:
                            pass  # 正常超时，继续推送
                            
        except asyncio.CancelledError:
            logger.info("Push loop cancelled")
        except Exception as e:
            logger.error(f"Push loop error: {e}")
            self._state = SimulationState.ERROR
        finally:
            self._metrics.end_time = datetime.now()
            if self._current_index >= len(self._data_queue):
                self._state = SimulationState.COMPLETED
                logger.info(f"Data push completed. Total: {self._metrics.pushed_data_points}/{self._metrics.total_data_points}")
            
    def _calculate_delay(self, current: KlineData, next_data: KlineData) -> float:
        """计算两个数据点之间的延迟"""
        if self.config.realtime:
            # 按实际时间间隔
            time_diff = (next_data.timestamp - current.timestamp).total_seconds()
            return time_diff / self._speed_multiplier
        else:
            # 按配置间隔
            return self.config.batch_interval_ms / 1000.0 / self._speed_multiplier
            
    async def _push_data(self, message: MarketDataMessage):
        """推送单个数据"""
        start_time = time.time()
        
        # 调用所有处理器
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                
        # 计算延迟
        latency = (time.time() - start_time) * 1000
        self._metrics.avg_latency_ms = (
            self._metrics.avg_latency_ms * 0.9 + latency * 0.1
        )
        
    def get_metrics(self) -> PushMetrics:
        """获取推送指标"""
        return self._metrics
        
    def get_state(self) -> SimulationState:
        """获取当前状态"""
        return self._state
        
    def get_current_data(self) -> Optional[KlineData]:
        """获取当前数据点"""
        if 0 <= self._current_index < len(self._data_queue):
            return self._data_queue[self._current_index]
        return None
        
    def get_progress(self) -> Dict[str, Any]:
        """获取进度信息"""
        return {
            "state": self._state.value,
            "current_index": self._current_index,
            "total_points": self._metrics.total_data_points,
            "pushed_points": self._metrics.pushed_data_points,
            "progress_percent": self._metrics.progress_percent,
            "speed": self._speed_multiplier,
            "elapsed_seconds": self._metrics.elapsed_seconds,
        }


class BatchDataPusher(DataPusher):
    """批量数据推送引擎"""
    
    def __init__(self, config: PushConfig):
        super().__init__(config)
        self._batch_size = config.batch_size
        
    async def _push_loop(self):
        """批量推送主循环"""
        try:
            while self._current_index < len(self._data_queue) and not self._stop_event.is_set():
                await self._pause_event.wait()
                
                if self._stop_event.is_set():
                    break
                    
                # 获取一批数据
                batch_end = min(self._current_index + self._batch_size, len(self._data_queue))
                batch = self._data_queue[self._current_index:batch_end]
                
                # 批量推送
                await self._push_batch(batch)
                
                self._current_index = batch_end
                self._metrics.pushed_data_points += len(batch)
                
                # 批次间隔
                if self._current_index < len(self._data_queue):
                    delay = self.config.batch_interval_ms / 1000.0 / self._speed_multiplier
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=delay
                    )
                    
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            logger.info("Batch push loop cancelled")
        except Exception as e:
            logger.error(f"Batch push loop error: {e}")
            self._state = SimulationState.ERROR
        finally:
            self._metrics.end_time = datetime.now()
            
    async def _push_batch(self, batch: List[KlineData]):
        """推送一批数据"""
        for kline in batch:
            message = MarketDataMessage.from_kline(kline, source="simulation")
            await self._push_data(message)


def create_data_pusher(config: PushConfig) -> DataPusher:
    """创建数据推送引擎"""
    if config.batch_size > 1:
        return BatchDataPusher(config)
    return DataPusher(config)
