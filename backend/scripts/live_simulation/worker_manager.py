"""
Worker策略管理模块

管理策略Worker的生命周期，加载策略，收集状态信息。
"""

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from .models import WorkerStatus, WorkerState, TradeSignal, OrderInfo, PositionInfo
from .config import WorkerConfig


@dataclass
class WorkerInfo:
    """Worker信息"""
    worker_id: str
    config: WorkerConfig
    status: WorkerStatus = field(default_factory=lambda: WorkerStatus(worker_id=""))
    strategy_instance: Optional[Any] = None
    is_running: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def __post_init__(self):
        if not self.status.worker_id:
            self.status.worker_id = self.worker_id


class WorkerManager:
    """Worker管理器"""
    
    def __init__(self):
        self._workers: Dict[str, WorkerInfo] = {}
        self._status_handlers: List[Callable[[WorkerStatus], None]] = []
        self._signal_handlers: List[Callable[[TradeSignal], None]] = []
        self._order_handlers: List[Callable[[OrderInfo], None]] = []
        
    def register_worker(self, worker_id: str, config: WorkerConfig) -> bool:
        """
        注册Worker
        
        Args:
            worker_id: Worker唯一标识
            config: Worker配置
            
        Returns:
            是否注册成功
        """
        if worker_id in self._workers:
            logger.warning(f"Worker {worker_id} already exists")
            return False
            
        worker_info = WorkerInfo(
            worker_id=worker_id,
            config=config,
        )
        
        self._workers[worker_id] = worker_info
        logger.info(f"Worker {worker_id} registered")
        return True
        
    def unregister_worker(self, worker_id: str) -> bool:
        """注销Worker"""
        if worker_id not in self._workers:
            logger.warning(f"Worker {worker_id} not found")
            return False
            
        worker_info = self._workers[worker_id]
        
        # 停止Worker
        if worker_info.is_running:
            self.stop_worker(worker_id)
            
        del self._workers[worker_id]
        logger.info(f"Worker {worker_id} unregistered")
        return True
        
    async def start_worker(self, worker_id: str) -> bool:
        """
        启动Worker
        
        Args:
            worker_id: Worker标识
            
        Returns:
            是否启动成功
        """
        if worker_id not in self._workers:
            logger.error(f"Worker {worker_id} not found")
            return False
            
        worker_info = self._workers[worker_id]
        
        if worker_info.is_running:
            logger.warning(f"Worker {worker_id} is already running")
            return True
            
        try:
            # 加载策略
            strategy = await self._load_strategy(worker_info.config)
            if not strategy:
                logger.error(f"Failed to load strategy for worker {worker_id}")
                return False
                
            worker_info.strategy_instance = strategy
            worker_info.is_running = True
            worker_info.start_time = datetime.now()
            worker_info.status.update_state(WorkerState.RUNNING)
            
            # 调用策略初始化
            if hasattr(strategy, "initialize"):
                if asyncio.iscoroutinefunction(strategy.initialize):
                    await strategy.initialize()
                else:
                    strategy.initialize()
                    
            logger.info(f"Worker {worker_id} started with strategy {worker_info.config.strategy_class}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start worker {worker_id}: {e}")
            worker_info.status.update_state(WorkerState.ERROR)
            worker_info.status.last_error = str(e)
            return False
            
    def stop_worker(self, worker_id: str) -> bool:
        """停止Worker"""
        if worker_id not in self._workers:
            logger.error(f"Worker {worker_id} not found")
            return False
            
        worker_info = self._workers[worker_id]
        
        if not worker_info.is_running:
            return True
            
        try:
            # 调用策略停止
            if worker_info.strategy_instance and hasattr(worker_info.strategy_instance, "stop"):
                worker_info.strategy_instance.stop()
                
            worker_info.is_running = False
            worker_info.end_time = datetime.now()
            worker_info.status.update_state(WorkerState.STOPPED)
            worker_info.strategy_instance = None
            
            logger.info(f"Worker {worker_id} stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping worker {worker_id}: {e}")
            return False
            
    async def _load_strategy(self, config: WorkerConfig) -> Optional[Any]:
        """
        动态加载策略
        
        Args:
            config: Worker配置
            
        Returns:
            策略实例
        """
        strategy_path = Path(config.strategy_path)
        
        # 如果是相对路径，尝试从多个位置查找
        if not strategy_path.is_absolute():
            # 获取当前文件所在目录 (live_simulation)
            live_sim_dir = Path(__file__).parent
            backend_dir = live_sim_dir.parent.parent
            
            possible_paths = [
                strategy_path,  # 原始相对路径
                Path.cwd() / strategy_path,  # 从当前工作目录
                backend_dir / strategy_path,  # 从backend目录
                live_sim_dir / "strategies" / strategy_path.name,  # 从live_simulation/strategies目录
                backend_dir / "scripts" / "live_simulation" / "strategies" / strategy_path.name,  # 完整路径
            ]
            
            for p in possible_paths:
                if p.exists():
                    strategy_path = p
                    logger.debug(f"Found strategy at: {p}")
                    break
            else:
                # 记录所有尝试过的路径
                tried_paths = [str(p) for p in possible_paths]
                raise FileNotFoundError(
                    f"Strategy file not found. Tried paths:\n" + "\n".join(f"  - {p}" for p in tried_paths)
                )
        
        if not strategy_path.exists():
            raise FileNotFoundError(f"Strategy file not found: {strategy_path}")
            
        try:
            # 动态加载模块
            module_name = f"strategy_{strategy_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, strategy_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load strategy from {strategy_path}")
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # 获取策略类
            strategy_class = getattr(module, config.strategy_class, None)
            if strategy_class is None:
                # 尝试查找第一个类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and attr_name not in ["StrategyBase", "object"]:
                        strategy_class = attr
                        break
                        
            if strategy_class is None:
                raise ImportError(f"Strategy class {config.strategy_class} not found in {strategy_path}")
                
            # 实例化策略
            strategy = strategy_class(config.strategy_params)
            
            return strategy
            
        except Exception as e:
            logger.error(f"Failed to load strategy: {e}")
            raise
            
    async def handle_market_data(self, worker_id: str, data: Dict[str, Any]):
        """
        处理市场数据
        
        Args:
            worker_id: Worker标识
            data: 市场数据
        """
        if worker_id not in self._workers:
            return
            
        worker_info = self._workers[worker_id]
        
        if not worker_info.is_running or not worker_info.strategy_instance:
            return
            
        try:
            strategy = worker_info.strategy_instance
            
            # 更新统计
            worker_info.status.messages_processed += 1
            
            # 调用策略数据处理
            if hasattr(strategy, "on_data"):
                if asyncio.iscoroutinefunction(strategy.on_data):
                    result = await strategy.on_data(data)
                else:
                    result = strategy.on_data(data)
                    
                # 处理返回的信号或订单
                if result:
                    await self._handle_strategy_result(worker_id, result)
                    
            # 发送状态更新
            await self._notify_status_handlers(worker_info.status)
            
        except Exception as e:
            logger.error(f"Error handling market data for worker {worker_id}: {e}")
            worker_info.status.errors_count += 1
            worker_info.status.last_error = str(e)
            
    async def _handle_strategy_result(self, worker_id: str, result: Any):
        """处理策略返回结果"""
        if isinstance(result, TradeSignal):
            await self._notify_signal_handlers(result)
        elif isinstance(result, OrderInfo):
            await self._notify_order_handlers(result)
        elif isinstance(result, list):
            for item in result:
                await self._handle_strategy_result(worker_id, item)
                
    async def _notify_status_handlers(self, status: WorkerStatus):
        """通知状态处理器"""
        for handler in self._status_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(status)
                else:
                    handler(status)
            except Exception as e:
                logger.error(f"Status handler error: {e}")
                
    async def _notify_signal_handlers(self, signal: TradeSignal):
        """通知信号处理器"""
        for handler in self._signal_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(signal)
                else:
                    handler(signal)
            except Exception as e:
                logger.error(f"Signal handler error: {e}")
                
    async def _notify_order_handlers(self, order: OrderInfo):
        """通知订单处理器"""
        for handler in self._order_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(order)
                else:
                    handler(order)
            except Exception as e:
                logger.error(f"Order handler error: {e}")
                
    def register_status_handler(self, handler: Callable[[WorkerStatus], None]):
        """注册状态处理器"""
        self._status_handlers.append(handler)
        
    def unregister_status_handler(self, handler: Callable[[WorkerStatus], None]):
        """注销状态处理器"""
        if handler in self._status_handlers:
            self._status_handlers.remove(handler)
            
    def register_signal_handler(self, handler: Callable[[TradeSignal], None]):
        """注册信号处理器"""
        self._signal_handlers.append(handler)
        
    def unregister_signal_handler(self, handler: Callable[[TradeSignal], None]):
        """注销信号处理器"""
        if handler in self._signal_handlers:
            self._signal_handlers.remove(handler)
            
    def register_order_handler(self, handler: Callable[[OrderInfo], None]):
        """注册订单处理器"""
        self._order_handlers.append(handler)
        
    def unregister_order_handler(self, handler: Callable[[OrderInfo], None]):
        """注销订单处理器"""
        if handler in self._order_handlers:
            self._order_handlers.remove(handler)
            
    def get_worker_status(self, worker_id: str) -> Optional[WorkerStatus]:
        """获取Worker状态"""
        if worker_id in self._workers:
            return self._workers[worker_id].status
        return None
        
    def get_all_worker_status(self) -> Dict[str, WorkerStatus]:
        """获取所有Worker状态"""
        return {wid: info.status for wid, info in self._workers.items()}
        
    def get_running_workers(self) -> List[str]:
        """获取运行中的Worker列表"""
        return [wid for wid, info in self._workers.items() if info.is_running]
        
    def get_worker_stats(self) -> Dict[str, Any]:
        """获取Worker统计信息"""
        total = len(self._workers)
        running = sum(1 for info in self._workers.values() if info.is_running)
        error = sum(1 for info in self._workers.values() if info.status.state == WorkerState.ERROR)
        
        total_messages = sum(info.status.messages_processed for info in self._workers.values())
        total_orders = sum(info.status.orders_placed for info in self._workers.values())
        total_errors = sum(info.status.errors_count for info in self._workers.values())
        
        return {
            "total_workers": total,
            "running_workers": running,
            "error_workers": error,
            "total_messages_processed": total_messages,
            "total_orders_placed": total_orders,
            "total_errors": total_errors,
        }
        
    def stop_all_workers(self):
        """停止所有Worker"""
        for worker_id in list(self._workers.keys()):
            self.stop_worker(worker_id)
            
    def clear(self):
        """清除所有Worker"""
        self.stop_all_workers()
        self._workers.clear()
