"""
Worker 状态机定义

定义 Worker 进程的生命周期状态
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime


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
    PAUSED = "paused"  # 已暂停

    # 停止状态
    STOPPING = "stopping"  # 正在停止
    STOPPED = "stopped"  # 已停止

    # 错误状态
    ERROR = "error"  # 发生错误
    RECOVERING = "recovering"  # 正在恢复

    # 重启状态
    RELOADING = "reloading"  # 正在重载配置
    RESTARTING = "restarting"  # 正在重启

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
        # 定义合法的状态转换
        valid_transitions = {
            WorkerState.INITIALIZING: [
                WorkerState.INITIALIZED,
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
                WorkerState.PAUSED,
                WorkerState.STOPPING,
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


@dataclass
class WorkerStatus:
    """
    Worker 状态信息

    记录 Worker 的完整状态信息
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

            # 更新时间戳
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

        from datetime import timedelta
        elapsed = datetime.now() - self.last_heartbeat
        return elapsed < timedelta(seconds=heartbeat_timeout)


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

            # 调用状态转换处理器
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
            except Exception as e:
                # 处理器错误不应影响状态转换
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
