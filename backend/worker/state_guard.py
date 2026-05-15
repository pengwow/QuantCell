"""
状态机守卫器 - 确保所有状态变更都通过状态机验证

核心职责：
1. 包装所有状态变更操作，强制通过状态机验证
2. 提供事务语义（全部成功或详细报告）
3. 记录完整的状态变更历史
4. 支持同步和异步批量操作
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from .state import WorkerState, StateMachine
import logging

logger = logging.getLogger(__name__)


@dataclass
class OperationResult:
    """单个操作结果"""
    success: bool
    worker_id: int
    operation: str
    message: str = ""
    old_state: Optional[WorkerState] = None
    new_state: Optional[WorkerState] = None
    error: Optional[Exception] = None


@dataclass
class BatchOperationResult:
    """批量操作结果"""
    success_ids: List[int] = field(default_factory=list)
    failed_dict: Dict[int, str] = field(default_factory=dict)
    total: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def all_success(self) -> bool:
        return len(self.failed_dict) == 0 and len(self.success_ids) > 0

    @property
    def partial_failure(self) -> bool:
        return len(self.failed_dict) > 0 and len(self.success_ids) > 0

    @property
    def all_failed(self) -> bool:
        return len(self.failed_dict) > 0 and len(self.success_ids) == 0


class StateMachineGuard:
    """
    状态机守卫器

    设计原则：
    - 所有状态变更必须通过此类的 transition() 方法
    - 自动验证状态转换合法性
    - 记录完整的审计日志
    - 支持批量操作的原子性检查

    使用示例：
        guard = StateMachineGuard()

        # 单个转换
        result = guard.transition(worker_id=1, target_state=WorkerState.STARTING)
        if result.success:
            print(f"成功转换: {result.old_state} -> {result.new_state}")

        # 批量转换
        batch_result = await guard.batch_transition(
            worker_ids=[1, 2, 3],
            target_state=WorkerState.STOPPING,
            operation_name="emergency_stop"
        )
        print(f"成功: {batch_result.success_ids}, 失败: {batch_result.failed_dict}")
    """

    def __init__(self):
        self._machines: Dict[int, StateMachine] = {}
        self._transition_log: List[Dict[str, Any]] = []
        self._lock = None  # 可选的锁，用于多线程环境

    def get_machine(self, worker_id: int) -> StateMachine:
        """
        获取或懒加载 Worker 的状态机实例

        Args:
            worker_id: Worker ID

        Returns:
            StateMachine: 该 Worker 的状态机实例
        """
        if worker_id not in self._machines:
            try:
                from . import crud
                from .core_service import WorkerCoreService

                service = WorkerCoreService()
                with service.get_db() as db:
                    worker = crud.get_worker(db, worker_id)
                    if worker:
                        initial_state = WorkerState(worker.status)
                    else:
                        logger.warning(f"[StateMachineGuard] Worker {worker_id} 不存在，使用默认状态 STOPPED")
                        initial_state = WorkerState.STOPPED

                self._machines[worker_id] = StateMachine(initial_state=initial_state)
                logger.debug(f"[StateMachineGuard] 为 Worker {worker_id} 创建状态机，初始状态: {initial_state.value}")

            except Exception as e:
                logger.error(f"[StateMachineGuard] 加载 Worker {worker_id} 状态失败: {e}")
                self._machines[worker_id] = StateMachine(initial_state=WorkerState.STOPPED)

        return self._machines[worker_id]

    def transition(
        self,
        worker_id: int,
        target_state: WorkerState,
        db_session=None,
    ) -> OperationResult:
        """
        执行状态转换（同步版本）

        Args:
            worker_id: Worker ID
            target_state: 目标状态
            db_session: 可选的数据库会话（用于事务性持久化）

        Returns:
            OperationResult: 操作结果，包含新旧状态和错误信息
        """
        machine = self.get_machine(worker_id)
        old_state = machine.current_state

        logger.info(
            f"[StateMachineGuard] 尝试转换 Worker {worker_id}: "
            f"{old_state.value} -> {target_state.value}"
        )

        # 验证状态转换合法性
        if not machine.can_transition_to(target_state):
            error_msg = (
                f"非法状态转换: {old_state.value} -> {target_state.value}"
            )
            logger.warning(f"[StateMachineGuard] Worker {worker_id}: {error_msg}")

            return OperationResult(
                success=False,
                worker_id=worker_id,
                operation=f"transition_{target_state.value}",
                message=error_msg,
                old_state=old_state,
            )

        # 执行状态转换
        try:
            success = machine.transition_to(target_state)

            if success:
                # 记录转换日志（审计追踪）
                log_entry = {
                    "worker_id": worker_id,
                    "timestamp": datetime.now().isoformat(),
                    "old_state": old_state.value,
                    "new_state": target_state.value,
                    "trigger": "api_call",
                }
                self._transition_log.append(log_entry)

                # 同步到数据库（如果提供了会话）
                if db_session is not None:
                    try:
                        from . import crud
                        crud.update_worker_status(db_session, worker_id, target_state.value)
                        logger.debug(f"[StateMachineGuard] Worker {worker_id} 状态已持久化到数据库")
                    except Exception as e:
                        logger.error(f"[StateMachineGuard] 持久化失败: {e}")

                logger.info(
                    f"[StateMachineGuard] Worker {worker_id} 转换成功: "
                    f"{old_state.value} -> {target_state.value}"
                )

                return OperationResult(
                    success=True,
                    worker_id=worker_id,
                    operation=f"transition_{target_state.value}",
                    message=f"状态转换成功",
                    old_state=old_state,
                    new_state=target_state,
                )

            else:
                error_msg = "状态转换失败（未知原因）"
                logger.error(f"[StateMachineGuard] Worker {worker_id}: {error_msg}")
                return OperationResult(
                    success=False,
                    worker_id=worker_id,
                    operation=f"transition_{target_state.value}",
                    message=error_msg,
                    old_state=old_state,
                )

        except Exception as e:
            error_msg = f"状态转换异常: {str(e)}"
            logger.exception(f"[StateMachineGuard] Worker {worker_id}: {error_msg}")
            return OperationResult(
                success=False,
                worker_id=worker_id,
                operation=f"transition_{target_state.value}",
                message=error_msg,
                old_state=old_state,
                error=e,
            )

    async def batch_transition(
        self,
        worker_ids: List[int],
        target_state: WorkerState,
        operation_name: str = "batch",
    ) -> BatchOperationResult:
        """
        批量状态转换（支持事务语义）

        策略选择：
        - 收集所有结果模式：即使某个 Worker 失败也继续尝试其他
        - 返回详细的成功/失败列表用于前端展示
        - 记录每个操作的完整审计信息

        Args:
            worker_ids: Worker ID 列表
            target_state: 目标状态
            operation_name: 操作名称（用于日志和审计）

        Returns:
            BatchOperationResult: 包含成功/失败详情的批量结果
        """
        logger.info(
            f"[StateMachineGuard] 开始批量{operation_name}: "
            f"{len(worker_ids)} 个 Workers -> {target_state.value}"
        )

        results: List[OperationResult] = []
        batch_result = BatchOperationResult(total=len(worker_ids))

        for wid in worker_ids:
            result = self.transition(wid, target_state)
            results.append(result)

            if result.success:
                batch_result.success_ids.append(wid)
            else:
                batch_result.failed_dict[wid] = result.message

            # 构建详细结果列表
            batch_result.results.append({
                "worker_id": result.worker_id,
                "success": result.success,
                "old_state": result.old_state.value if result.old_state else None,
                "new_state": result.new_state.value if result.new_state else None,
                "message": result.message,
                "error": str(result.error) if result.error else None,
            })

        # 记录批量操作汇总日志
        logger.info(
            f"[StateMachineGuard] 批量{operation_name}完成: "
            f"成功={len(batch_result.success_ids)}, "
            f"失败={len(batch_result.failed_dict)}, "
            f"总计={batch_result.total}"
        )

        # 如果有失败，记录警告
        if batch_result.partial_failure:
            logger.warning(
                f"[StateMachineGuard] 批量{operation_name}部分失败: "
                f"失败的Worker IDs: {list(batch_result.failed_dict.keys())}"
            )
        elif batch_result.all_failed:
            logger.error(
                f"[StateMachineGuard] 批量{operation_name}全部失败!"
            )

        return batch_result

    def get_current_state(self, worker_id: int) -> WorkerState:
        """获取指定 Worker 的当前状态"""
        machine = self.get_machine(worker_id)
        return machine.current_state

    def get_state_history(
        self,
        worker_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取指定 Worker 的状态转换历史

        Args:
            worker_id: Worker ID
            limit: 最大返回条数

        Returns:
            状态转换历史记录列表
        """
        history = [
            entry for entry in self._transition_log
            if entry["worker_id"] == worker_id
        ]
        return history[-limit:]

    def get_all_states_summary(self) -> Dict[int, str]:
        """获取所有已加载 Worker 的当前状态摘要"""
        return {
            wid: machine.current_state.value
            for wid, machine in self._machines.items()
        }

    def invalidate_cache(self, worker_id: int = None):
        """
        使缓存失效（强制下次访问时从数据库重新加载）

        Args:
            worker_id: 指定 Worker ID，如果为 None 则清除所有缓存
        """
        if worker_id is not None:
            if worker_id in self._machines:
                del self._machines[worker_id]
                logger.debug(f"[StateMachineGuard] Worker {worker_id} 缓存已失效")
        else:
            count = len(self._machines)
            self._machines.clear()
            logger.info(f"[StateMachineGuard] 所有缓存已清除 ({count} 个)")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_transitions = len(self._transition_log)
        recent_transitions = self._transition_log[-10:] if total_transitions > 0 else []

        return {
            "cached_machines": len(self._machines),
            "total_transitions": total_transitions,
            "recent_transitions": recent_transitions,
            "states_distribution": {
                state.value: sum(
                    1 for m in self._machines.values()
                    if m.current_state == state
                )
                for state in WorkerState
            },
        }
