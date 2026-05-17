"""
Worker 状态管理器

状态驱动的 Worker 管理机制，提供：
- 状态转换验证和执行
- 内存缓存与数据库持久化
- 事件驱动通知机制
- 并发安全的单例管理
- Worker 状态枚举、状态信息数据类、状态机
"""

import asyncio
import inspect
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, Callable, List, Set

from utils.logger import get_logger, LogType
from collector.db.database import SessionLocal
from . import crud

logger = get_logger(__name__, LogType.APPLICATION)


# =============================================================================
# Worker 状态枚举
# =============================================================================

class WorkerState(Enum):
    """
    Worker 状态枚举

    定义 Worker 进程的完整生命周期状态
    """

    # 初始状态
    INITIALIZING = "initializing"  # 正在初始化
    INITIALIZED = "initialized"  # 初始化完成

    # 运行状态
    STARTING = "starting"  # 正在启动
    RUNNING = "running"  # 正常运行

    # 停止状态
    STOPPING = "stopping"  # 正在停止
    STOPPED = "stopped"  # 已停止

    # 错误状态
    ERROR = "error"  # 发生错误
    RECOVERING = "recovering"  # 正在恢复

    # 重启状态
    RELOADING = "reloading"  # 正在重载配置
    RESTARTING = "restarting"  # 正在重启

    # 暂停状态
    PAUSED = "paused"  # 已暂停

    def is_active(self) -> bool:
        """
        检查状态是否为活跃状态

        Returns:
            是否为活跃状态
        """
        return self in [
            WorkerState.RUNNING,
            WorkerState.PAUSED,
        ]

    def is_terminal(self) -> bool:
        """
        检查状态是否为终止状态

        Returns:
            是否为终止状态
        """
        return self in [
            WorkerState.STOPPED,
            WorkerState.ERROR,
        ]

    def can_transition_to(self, new_state: "WorkerState") -> bool:
        """
        检查是否可以转换到指定状态

        Args:
            new_state: 目标状态

        Returns:
            是否可以转换
        """
        valid_transitions = {
            WorkerState.INITIALIZING: [
                WorkerState.INITIALIZED,
                WorkerState.STARTING,
                WorkerState.RUNNING,
                WorkerState.ERROR,
            ],
            WorkerState.INITIALIZED: [
                WorkerState.STARTING,
                WorkerState.STOPPING,
                WorkerState.ERROR,
            ],
            WorkerState.STARTING: [
                WorkerState.RUNNING,
                WorkerState.ERROR,
            ],
            WorkerState.RUNNING: [
                WorkerState.STOPPING,
                WorkerState.PAUSED,
                WorkerState.RELOADING,
                WorkerState.ERROR,
            ],
            WorkerState.PAUSED: [
                WorkerState.RUNNING,
                WorkerState.STOPPING,
                WorkerState.ERROR,
            ],
            WorkerState.STOPPING: [
                WorkerState.STOPPED,
                WorkerState.ERROR,
            ],
            WorkerState.STOPPED: [
                WorkerState.STARTING,
                WorkerState.RESTARTING,
            ],
            WorkerState.ERROR: [
                WorkerState.RECOVERING,
                WorkerState.STOPPING,
            ],
            WorkerState.RECOVERING: [
                WorkerState.RUNNING,
                WorkerState.ERROR,
                WorkerState.STOPPING,
            ],
            WorkerState.RELOADING: [
                WorkerState.RUNNING,
                WorkerState.ERROR,
            ],
            WorkerState.RESTARTING: [
                WorkerState.INITIALIZING,
                WorkerState.ERROR,
            ],
        }

        return new_state in valid_transitions.get(self, [])


# =============================================================================
# Worker 状态信息数据类（WorkerProcess 使用的完整状态快照）
# =============================================================================

@dataclass
class WorkerStatus:
    """
    Worker 状态信息

    记录 Worker 的完整状态信息，用于 WorkerProcess 子进程侧的状态追踪
    """

    worker_id: str
    state: WorkerState = WorkerState.INITIALIZING
    strategy_name: Optional[str] = None
    strategy_path: Optional[str] = None
    symbols: list = field(default_factory=list)
    pid: Optional[int] = None

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None

    # 统计信息
    messages_processed: int = 0
    orders_placed: int = 0
    errors_count: int = 0

    # 错误信息
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None

    # 扩展信息
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        Returns:
            状态字典
        """
        return {
            "worker_id": self.worker_id,
            "state": self.state.value,
            "strategy_name": self.strategy_name,
            "strategy_path": self.strategy_path,
            "symbols": self.symbols,
            "pid": self.pid,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "messages_processed": self.messages_processed,
            "orders_placed": self.orders_placed,
            "errors_count": self.errors_count,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "metadata": self.metadata,
        }

    def update_state(self, new_state: WorkerState) -> bool:
        """
        更新状态

        Args:
            new_state: 新状态

        Returns:
            是否更新成功
        """
        if self.state.can_transition_to(new_state):
            old_state = self.state
            self.state = new_state

            if new_state == WorkerState.RUNNING and old_state != WorkerState.RUNNING:
                self.started_at = datetime.now()
            elif new_state == WorkerState.STOPPED:
                self.stopped_at = datetime.now()

            return True
        return False

    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.now()

    def record_error(self, error_message: str):
        """
        记录错误

        Args:
            error_message: 错误信息
        """
        self.errors_count += 1
        self.last_error = error_message
        self.last_error_time = datetime.now()

    def is_healthy(self, heartbeat_timeout: int = 30) -> bool:
        """
        检查 Worker 是否健康

        Args:
            heartbeat_timeout: 心跳超时时间（秒）

        Returns:
            是否健康
        """
        if self.state not in [WorkerState.RUNNING, WorkerState.PAUSED]:
            return False

        if self.last_heartbeat is None:
            return False

        elapsed = datetime.now() - self.last_heartbeat
        return elapsed < timedelta(seconds=heartbeat_timeout)


# =============================================================================
# 状态机管理器
# =============================================================================

class StateMachine:
    """
    状态机管理器

    管理 Worker 的状态转换
    """

    def __init__(self, initial_state: WorkerState = WorkerState.INITIALIZING):
        self._state = initial_state
        self._state_history: list = [(initial_state, datetime.now())]
        self._transition_handlers: Dict[WorkerState, list] = {}

    @property
    def current_state(self) -> WorkerState:
        """获取当前状态"""
        return self._state

    def transition_to(self, new_state: WorkerState) -> bool:
        """
        转换到指定状态

        Args:
            new_state: 目标状态

        Returns:
            是否转换成功
        """
        if self._state.can_transition_to(new_state):
            old_state = self._state
            self._state = new_state
            self._state_history.append((new_state, datetime.now()))

            self._call_transition_handlers(old_state, new_state)

            return True
        return False

    def register_transition_handler(
        self,
        target_state: WorkerState,
        handler: callable,
    ):
        """
        注册状态转换处理器

        Args:
            target_state: 目标状态
            handler: 处理函数，接收 (old_state, new_state) 参数
        """
        if target_state not in self._transition_handlers:
            self._transition_handlers[target_state] = []
        self._transition_handlers[target_state].append(handler)

    def _call_transition_handlers(self, old_state: WorkerState, new_state: WorkerState):
        """
        调用状态转换处理器

        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        handlers = self._transition_handlers.get(new_state, [])
        for handler in handlers:
            try:
                handler(old_state, new_state)
            except Exception:
                pass

    def get_state_history(self) -> list:
        """
        获取状态历史

        Returns:
            状态历史列表
        """
        return self._state_history.copy()

    def can_transition_to(self, new_state: WorkerState) -> bool:
        """
        检查是否可以转换到指定状态

        Args:
            new_state: 目标状态

        Returns:
            是否可以转换
        """
        return self._state.can_transition_to(new_state)


# =============================================================================
# Worker 状态记录（状态管理器内部使用的数据类）
# =============================================================================

@dataclass
class WorkerStateRecord:
    """
    Worker 状态数据类

    记录 Worker 的完整生命周期状态信息
    """

    worker_id: int
    status: str = "stopped"
    previous_status: Optional[str] = None
    pid: Optional[int] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    error_message: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.stopped_at:
            data['stopped_at'] = self.stopped_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data


# 合法的状态转换规则
STATE_TRANSITIONS: Dict[str, List[str]] = {
    "stopped": ["starting", "restarting"],
    "starting": ["running", "error"],
    "running": ["stopping", "error", "paused", "restarting"],
    "stopping": ["stopped", "error"],
    "paused": ["running", "stopping", "restarting"],
    "error": [
        "starting",      # 重试启动
        "stopped",       # 标记为已停止（清理完成）
        "stopping",      # 强制停止（从错误状态恢复的关键路径）
        "restarting",    # 强制重启
    ],
    "restarting": ["starting", "stopped", "error"],
}


def is_valid_transition(current_status: str, target_status: str) -> bool:
    """
    验证状态转换是否合法

    Args:
        current_status: 当前状态
        target_status: 目标状态

    Returns:
        是否为合法的状态转换
    """
    valid_targets = STATE_TRANSITIONS.get(current_status, [])
    return target_status in valid_targets


class WorkerStateManager:
    """
    Worker 状态管理器（单例）

    提供 Worker 状态的统一管理，包括：
    - 状态缓存和查询
    - 状态转换验证和执行
    - 数据库持久化
    - 事件驱动通知
    """

    _instance: Optional["WorkerStateManager"] = None
    _initialized: bool = False

    def __new__(cls) -> "WorkerStateManager":
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化状态管理器"""
        if self._initialized:
            return

        self._initialized = True
        self._state_cache: Dict[int, WorkerStateRecord] = {}
        self._lock = asyncio.Lock()
        self._event_handlers: Dict[str, List[Callable]] = {}

        logger.info("WorkerStateManager 初始化完成")

    async def get_state(self, worker_id: int) -> Optional[WorkerStateRecord]:
        """
        获取 Worker 状态

        Args:
            worker_id: Worker ID

        Returns:
            WorkerStateRecord 对象，如果不存在返回 None
        """
        async with self._lock:
            state = self._state_cache.get(worker_id)
            if state:
                logger.debug(f"获取 Worker {worker_id} 状态: {state.status}")
            return state

    async def transition(
        self,
        worker_id: int,
        target_status: str,
        **kwargs
    ) -> bool:
        """
        执行状态转换

        验证合法性、更新缓存、触发事件、持久化到数据库

        Args:
            worker_id: Worker ID
            target_status: 目标状态
            **kwargs: 额外参数（pid, error_message 等）

        Returns:
            是否转换成功
        """
        async with self._lock:
            current_state = self._state_cache.get(worker_id)

            # 如果状态不存在，只允许从 stopped 开始
            if current_state is None:
                if target_status != "stopped":
                    logger.warning(
                        f"Worker {worker_id} 不存在，无法转换到 {target_status}"
                    )
                    return False
                current_state = WorkerStateRecord(worker_id=worker_id, status="stopped")
                self._state_cache[worker_id] = current_state

            # 验证状态转换合法性
            if not is_valid_transition(current_state.status, target_status):
                logger.warning(
                    f"非法状态转换: Worker {worker_id} 从 {current_state.status} 到 {target_status}"
                )
                return False

            # 保存旧状态
            old_status = current_state.status

            # 更新状态
            current_state.previous_status = old_status
            current_state.status = target_status
            current_state.updated_at = datetime.now()

            # 处理额外参数
            if 'pid' in kwargs:
                current_state.pid = kwargs['pid']
            if 'error_message' in kwargs:
                current_state.error_message = kwargs['error_message']

            # 更新时间戳
            if target_status == "running" and old_status != "running":
                current_state.started_at = datetime.now()
            elif target_status == "stopped":
                current_state.stopped_at = datetime.now()

            # 持久化到数据库
            try:
                self._persist_state(current_state)
            except Exception as e:
                logger.error(f"持久化 Worker {worker_id} 状态失败: {e}")

            # 触发状态转换事件（fire-and-forget，避免阻塞调用方）
            # 事件处理器（如 manager._handle_start_event）可能耗时较长，
            # 使用 create_task 确保 transition 快速返回，不阻塞 HTTP 响应
            try:
                asyncio.create_task(
                    self._emit_event("state_changed", {
                        "worker_id": worker_id,
                        "old_status": old_status,
                        "new_status": target_status,
                        "timestamp": datetime.now().isoformat(),
                        "error_message": kwargs.get("error_message", ""),
                    })
                )
            except Exception as e:
                logger.error(f"触发状态转换事件失败: {e}")

            logger.info(
                f"Worker {worker_id} 状态转换: {old_status} -> {target_status}"
            )

            return True

    async def get_all_states(self) -> Dict[int, WorkerStateRecord]:
        """
        获取所有 Worker 状态

        Returns:
            Worker ID 到 WorkerStateRecord 的映射字典
        """
        async with self._lock:
            return self._state_cache.copy()

    async def force_reset_to_stopped(self, worker_id: int, reason: str = "紧急重置") -> bool:
        """
        强制将 Worker 状态重置为 stopped（紧急恢复接口）

        当 Worker 卡在异常状态（如 error）无法正常转换时，
        使用此方法可以强制将其重置到 stopped 状态。

        ⚠️ 此方法跳过正常的合法性验证，仅用于：
        - 从 error 状态恢复
        - 清理僵尸进程后的状态重置
        - 管理员手动干预

        Args:
            worker_id: Worker ID
            reason: 重置原因（用于日志记录）

        Returns:
            是否重置成功
        """
        async with self._lock:
            current_state = self._state_cache.get(worker_id)

            if current_state is None:
                logger.warning(f"Worker {worker_id} 不存在，无法强制重置")
                return False

            old_status = current_state.status

            # 直接更新状态，不进行合法性检查
            current_state.previous_status = old_status
            current_state.status = "stopped"
            current_state.error_message = f"强制重置 (原因: {reason}, 原状态: {old_status})"
            current_state.updated_at = datetime.now()
            current_state.stopped_at = datetime.now()
            current_state.pid = None

            # 持久化到数据库
            try:
                self._persist_state(current_state)
            except Exception as e:
                logger.error(f"持久化强制重置失败: {e}")

            # 触发事件通知（fire-and-forget）
            try:
                asyncio.create_task(
                    self._emit_event("state_changed", {
                        "worker_id": worker_id,
                        "old_status": old_status,
                        "new_status": "stopped",
                        "timestamp": datetime.now().isoformat(),
                        "force_reset": True,
                        "reason": reason,
                    })
                )
            except Exception as e:
                logger.error(f"触发强制重置事件失败: {e}")

            logger.warning(
                f"[紧急恢复] Worker {worker_id} 强制重置: {old_status} -> stopped (原因: {reason})"
            )

            return True

    def _persist_state(self, state: WorkerStateRecord) -> None:
        """
        持久化状态到数据库（带重试机制）

        最多尝试3次，每次失败后指数退避
        最终失败时记录错误但不中断主流程（内存状态继续使用）

        Args:
            state: WorkerStateRecord 对象
        """
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            db = SessionLocal()
            try:
                crud.update_worker_status(
                    db=db,
                    worker_id=state.worker_id,
                    status=state.status,
                    pid=state.pid,
                )
                logger.debug(f"Worker {state.worker_id} 状态已持久化: {state.status}")
                return
            except Exception as e:
                last_error = e
                db.rollback()
                if attempt < max_retries - 1:
                    wait_time = 0.5 * (attempt + 1)
                    logger.warning(
                        f"持久化状态失败（尝试 {attempt + 1}/{max_retries}），"
                        f"{wait_time:.1f}s 后重试: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"持久化状态最终失败（{max_retries}次尝试均失败）: {e}，"
                        f"Worker {state.worker_id} 内存状态保持为 {state.status}"
                    )
            finally:
                db.close()

        if last_error:
            raise last_error

    async def initialize(self) -> None:
        """
        从数据库恢复状态

        在应用启动时调用，将数据库中的 Worker 状态加载到内存缓存
        """
        async with self._lock:
            logger.info("正在从数据库恢复 Worker 状态...")

            db = SessionLocal()
            try:
                from .crud import get_workers

                workers, total = get_workers(db, skip=0, limit=1000)

                # 中间状态集合（程序异常退出后残留的风险状态）
                RECOVERABLE_STATES = {"starting", "stopping", "restarting", "paused"}
                recovered_count = 0

                for worker in workers:
                    status = worker.status or "stopped"

                    # 自动修复中间状态为 stopped，防止程序异常退出后状态永久冻住
                    if status in RECOVERABLE_STATES:
                        logger.warning(
                            f"[状态恢复] Worker {worker.id} 发现残留中间状态 '{status}'，"
                            f"自动修正为 'stopped'（上次程序可能异常退出）"
                        )
                        status = "stopped"
                        recovered_count += 1
                        # 同步修正数据库中的状态
                        try:
                            from .crud import update_worker_status
                            update_worker_status(db, worker.id, "stopped", pid=None)
                        except Exception as e:
                            logger.error(
                                f"[状态恢复] 修正Worker {worker.id} 数据库状态失败: {e}"
                            )

                    state = WorkerStateRecord(
                        worker_id=worker.id,
                        status=status,
                        pid=None if status == "stopped" else worker.pid,
                        started_at=worker.started_at,
                        stopped_at=worker.stopped_at,
                        updated_at=worker.updated_at or datetime.now(),
                    )
                    self._state_cache[worker.id] = state

                if recovered_count > 0:
                    logger.info(
                        f"已恢复 {len(workers)} 个 Worker 状态，"
                        f"其中 {recovered_count} 个残留中间状态已被自动修正为 stopped"
                    )
                else:
                    logger.info(f"已恢复 {len(workers)} 个 Worker 状态")
            except Exception as e:
                logger.error(f"从数据库恢复状态失败: {e}")
            finally:
                db.close()

    async def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        发射事件

        通知所有注册的事件处理器，支持同步和异步处理器，
        处理器错误不会影响主流程

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        handlers = self._event_handlers.get(event_type, [])

        for handler in handlers:
            try:
                # 判断处理器是异步还是同步
                if inspect.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                # 异常隔离：单个处理器错误不影响其他处理器和主流程
                logger.error(
                    f"事件处理器错误 [event={event_type}, handler={handler.__name__}]: {e}"
                )

    def register_handler(
        self,
        event_type: str,
        handler: Callable[[Dict[str, Any]], Any]
    ) -> None:
        """
        注册事件处理器

        支持同步和异步函数作为处理器

        Args:
            event_type: 事件类型
            handler: 处理函数，接收事件数据字典作为参数
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []

        self._event_handlers[event_type].append(handler)
        logger.debug(
            f"注册事件处理器: event={event_type}, handler={handler.__name__}"
        )

    def unregister_handler(
        self,
        event_type: str,
        handler: Callable[[Dict[str, Any]], Any]
    ) -> None:
        """
        移除事件处理器

        Args:
            event_type: 事件类型
            handler: 要移除的处理函数
        """
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
                logger.debug(
                    f"移除事件处理器: event={event_type}, handler={handler.__name__}"
                )
            except ValueError:
                pass

    async def remove_worker(self, worker_id: int) -> bool:
        """
        从缓存中移除 Worker 状态

        Args:
            worker_id: Worker ID

        Returns:
            是否移除成功
        """
        async with self._lock:
            if worker_id in self._state_cache:
                del self._state_cache[worker_id]
                logger.info(f"已移除 Worker {worker_id} 状态")
                return True
            return False

    def get_registered_events(self) -> Set[str]:
        """
        获取所有已注册的事件类型

        Returns:
            事件类型集合
        """
        return set(self._event_handlers.keys())

    def get_handler_count(self, event_type: str) -> int:
        """
        获取指定事件类型的处理器数量

        Args:
            event_type: 事件类型

        Returns:
            处理器数量
        """
        return len(self._event_handlers.get(event_type, []))


# 全局单例实例
worker_state_manager = WorkerStateManager()
