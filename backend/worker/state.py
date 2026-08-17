"""
Worker 模块全局单例状态枢纽

集中管理 Worker 模块所需的所有全局单例，
确保所有 Router 和 Service 层操作同一实例。

单例列表:
    - connection_manager: WebSocket 连接管理与消息广播
    - strategy_registry: 策略注册表（内存字典 + DB 持久化）
    - live_manager: 实盘交易管理器（Binance/OKX 连接）
    - trading_system: 策略执行引擎
"""

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from fastapi import WebSocket

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


# =============================================================================
# ConnectionManager — WebSocket 连接管理与消息广播
# =============================================================================

class ConnectionManager:
    """
    WebSocket 连接管理器

    管理所有活跃的 WebSocket 连接，支持广播消息到所有客户端，
    自动清理已断开的连接。
    """

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket 客户端已连接，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket 客户端已断开，当前连接数: {len(self.active_connections)}")

    async def broadcast(self, message: dict) -> None:
        """向所有连接广播消息，自动清理断开连接"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


# =============================================================================
# StrategyRuntime — 策略运行时状态
# =============================================================================

@dataclass
class StrategyRuntime:
    """
    策略运行时对象

    记录单个策略在进程内的完整运行时状态，
    包括配置、策略执行引擎实例、异步任务引用等。
    """
    worker_id: int
    strategy_id: int
    name: str
    status: str = "stopped"
    trading_node: Optional[Any] = None
    _run_task: Optional[asyncio.Task] = None
    _run_thread: Optional[threading.Thread] = None
    _flush_stop: Optional[threading.Event] = None
    _pid: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "strategy_id": self.strategy_id,
            "name": self.name,
            "status": self.status,
            "is_running": self.is_running,
            "pid": self._pid,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
        }

    def set_pid(self, pid: int) -> None:
        self._pid = pid

    @property
    def is_running(self) -> bool:
        if self.status != "running":
            return False
        if self._run_task is not None and not self._run_task.done():
            return True
        if self._run_thread is not None and self._run_thread.is_alive():
            return True
        return False


# =============================================================================
# StrategyRegistry — 策略注册表
# =============================================================================

class StrategyRegistry:
    """
    策略注册表（单例）

    维护所有策略的运行时状态，提供 CRUD 操作，
    状态变更时触发回调通知（用于 WebSocket 广播）。

    三层架构中的内存存储层：
        1. 全局单例层: state.py 统一管理
        2. 内存存储层: StrategyRegistry 字典（本文）
        3. 数据库持久化层: crud.py
    """

    def __init__(self):
        self._strategies: Dict[int, StrategyRuntime] = {}
        self._change_callbacks: List[Callable] = []
        self._lock = threading.Lock()  # 保护 _strategies 的并发访问

    def register(self, runtime: StrategyRuntime) -> None:
        with self._lock:
            self._strategies[runtime.worker_id] = runtime
        logger.info(f"[StrategyRegistry] 注册策略: worker_id={runtime.worker_id}, name={runtime.name}")

    def unregister(self, worker_id: int) -> Optional[StrategyRuntime]:
        with self._lock:
            runtime = self._strategies.pop(worker_id, None)
        if runtime:
            logger.info(f"[StrategyRegistry] 注销策略: worker_id={worker_id}")
        return runtime

    def get(self, worker_id: int) -> Optional[StrategyRuntime]:
        with self._lock:
            return self._strategies.get(worker_id)

    def list_all(self) -> List[StrategyRuntime]:
        with self._lock:
            return list(self._strategies.values())

    def update_status(
        self,
        worker_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> Optional[StrategyRuntime]:
        with self._lock:
            runtime = self._strategies.get(worker_id)
            if runtime is None:
                return None

            old_status = runtime.status
            runtime.status = status
            if error_message is not None:
                runtime.error_message = error_message

        logger.info(
            f"[StrategyRegistry] 状态变更: worker_id={worker_id}, "
            f"{old_status} -> {status}"
        )

        self._notify_change(worker_id, old_status, status, error_message)
        return runtime

    def set_run_task(self, worker_id: int, task: Optional[asyncio.Task]) -> None:
        with self._lock:
            runtime = self._strategies.get(worker_id)
            if runtime:
                runtime._run_task = task

    def set_trading_node(self, worker_id: int, trading_node: Any) -> None:
        with self._lock:
            runtime = self._strategies.get(worker_id)
            if runtime:
                runtime.trading_node = trading_node

    def set_run_thread(self, worker_id: int, thread: Optional[threading.Thread]) -> None:
        with self._lock:
            runtime = self._strategies.get(worker_id)
            if runtime:
                runtime._run_thread = thread

    def set_flush_stop(self, worker_id: int, event: Optional[threading.Event]) -> None:
        with self._lock:
            runtime = self._strategies.get(worker_id)
            if runtime:
                runtime._flush_stop = event

    def get_flush_stop(self, worker_id: int) -> Optional[threading.Event]:
        with self._lock:
            runtime = self._strategies.get(worker_id)
            if runtime:
                return runtime._flush_stop
        return None

    def on_change(self, callback: callable) -> None:
        """注册状态变更回调"""
        self._change_callbacks.append(callback)

    def _notify_change(
        self,
        worker_id: int,
        old_status: str,
        new_status: str,
        error_message: Optional[str],
    ) -> None:
        for callback in self._change_callbacks:
            try:
                callback(worker_id, old_status, new_status, error_message)
            except Exception as e:
                logger.error(f"[StrategyRegistry] 回调执行失败: {e}")


# =============================================================================
# LiveTradingManager — 实盘交易管理器
# =============================================================================

class LiveTradingManager:
    """
    实盘交易管理器，管理交易所连接、下单、撤单、持仓同步等实盘操作。
    支持按 worker_id 追踪多个交易所连接配置。
    """

    def __init__(self):
        self._connected_workers: Dict[int, Dict[str, Any]] = {}

    @property
    def is_connected(self) -> bool:
        return len(self._connected_workers) > 0

    async def connect(self, worker_id: int, exchange: str, config: Optional[Dict[str, Any]] = None) -> bool:
        self._connected_workers[worker_id] = {
            "exchange": exchange,
            "config": config or {},
        }
        logger.info(f"[LiveTradingManager] Worker {worker_id} 已连接交易所: {exchange}")
        return True

    async def disconnect(self, worker_id: Optional[int] = None) -> None:
        if worker_id is not None:
            if worker_id in self._connected_workers:
                exchange = self._connected_workers[worker_id].get("exchange", "unknown")
                del self._connected_workers[worker_id]
                logger.info(f"[LiveTradingManager] Worker {worker_id} 已断开交易所连接: {exchange}")
            else:
                logger.warning(f"[LiveTradingManager] Worker {worker_id} 未找到连接记录")
        else:
            self._connected_workers.clear()
            logger.info("[LiveTradingManager] 已断开所有交易所连接")

    def get_status(self) -> Dict[str, Any]:
        workers_status = {}
        for wid, info in self._connected_workers.items():
            workers_status[wid] = {
                "exchange": info.get("exchange"),
                "config": info.get("config"),
            }
        return {
            "connected": self.is_connected,
            "worker_count": len(self._connected_workers),
            "workers": workers_status,
        }

    def register_worker(self, worker_id: int, exchange: str, config: Optional[Dict[str, Any]] = None) -> None:
        """注册一个 worker 的交易所配置（不立即连接）。"""
        if worker_id not in self._connected_workers:
            self._connected_workers[worker_id] = {
                "exchange": exchange,
                "config": config or {},
            }
            logger.info(f"[LiveTradingManager] 已注册 Worker {worker_id} 交易所: {exchange}")
        else:
            logger.warning(f"[LiveTradingManager] Worker {worker_id} 已注册，更新配置")
            self._connected_workers[worker_id]["exchange"] = exchange
            self._connected_workers[worker_id]["config"] = config or {}

    def unregister_worker(self, worker_id: int) -> None:
        """取消注册一个 worker 的交易所配置。"""
        if worker_id in self._connected_workers:
            del self._connected_workers[worker_id]
            logger.info(f"[LiveTradingManager] 已取消注册 Worker {worker_id}")
        else:
            logger.warning(f"[LiveTradingManager] Worker {worker_id} 未注册")


# =============================================================================
# 模块级单例（在 Python 模块加载时创建一次，全局唯一）
# =============================================================================

connection_manager = ConnectionManager()
strategy_registry = StrategyRegistry()
live_manager = LiveTradingManager()

# trading_system 延迟导入（避免循环依赖，由 trading 系统模块提供）
trading_system: Optional[Any] = None


# =============================================================================
# WebSocket 广播集成 — 策略状态变更时自动广播到所有连接的客户端
# =============================================================================

def _broadcast_state_change(
    worker_id: int,
    old_status: str,
    new_status: str,
    error_message: Optional[str],
) -> None:
    """策略状态变更时通过 WebSocket 广播消息到所有客户端"""
    message = {
        "type": "strategy_event",
        "worker_id": worker_id,
        "old_status": old_status,
        "new_status": new_status,
        "error_message": error_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(connection_manager.broadcast(message))
    except RuntimeError:
        pass


strategy_registry.on_change(_broadcast_state_change)