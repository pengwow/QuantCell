"""
优雅停机管理器 - 带超时控制和资源清理保障

核心功能：
1. 分阶段停机（排空 → 停止服务 → 清理资源）
2. 每个阶段有独立的超时控制
3. 超时后可选强制终止
4. 详细的停机报告和审计日志

设计原则：
- 防御性编程：所有异常都被捕获并记录
- 超时保护：避免无限等待导致僵尸进程
- 优雅降级：即使某个阶段失败也继续执行后续阶段
- 可观测性：详细的日志记录和状态报告

使用示例：
    async def my_drain():
        await wait_for_orders_to_complete()

    async def my_stop():
        await trading_engine.stop()

    async def my_cleanup():
        await close_connections()

    mgr = GracefulShutdownManager(
        config=ShutdownConfig(total_timeout=30.0),
        on_drain=my_drain,
        on_stop_services=my_stop,
        on_cleanup=my_cleanup,
    )

    status = await mgr.shutdown()
    print(f"停机耗时: {status.duration_seconds:.2f}s, 是否超时: {status.timeout_occurred}")
"""

import asyncio
import logging
import os
import signal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class ShutdownPhase(Enum):
    """停机阶段枚举"""

    REQUESTED = "requested"
    DRAINING = "draining"
    STOPPING_SERVICES = "stopping_services"
    CLEANUP = "cleanup"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ERROR = "error"
    FORCE_KILLED = "force_killed"


@dataclass
class ShutdownConfig:
    """
    停机配置

    Attributes:
        total_timeout: 总超时时间（秒）
        drain_timeout: 排空进行中操作的超时时间（秒）
        service_stop_timeout: 停止外部服务的超时时间（秒）
        force_kill_after_timeout: 超时后是否强制终止进程
        skip_drain: 是否跳过排空阶段（紧急停机时使用）
        skip_service_stop: 是否跳过服务停止阶段
    """

    total_timeout: float = 30.0
    drain_timeout: float = 10.0
    service_stop_timeout: float = 10.0
    force_kill_after_timeout: bool = True
    skip_drain: bool = False
    skip_service_stop: bool = False


@dataclass
class PhaseResult:
    """单个阶段的执行结果"""

    phase_name: str
    success: bool
    duration_seconds: float = 0.0
    error: str | None = None
    timed_out: bool = False


@dataclass
class ShutdownStatus:
    """
    停机状态报告

    Attributes:
        phase: 当前所处阶段
        started_at: 开始时间
        completed_at: 完成时间
        duration_seconds: 总耗时（秒）
        phases_completed: 已完成的阶段数
        phase_results: 各阶段的详细结果
        errors: 错误列表
        timeout_occurred: 是否发生超时
        force_killed: 是否被强制终止
    """

    phase: ShutdownPhase = ShutdownPhase.REQUESTED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    phases_completed: int = 0
    phase_results: list[PhaseResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timeout_occurred: bool = False
    force_killed: bool = False

    @property
    def is_successful(self) -> bool:
        return self.phase == ShutdownPhase.COMPLETED and not self.timeout_occurred

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式（用于API响应）"""
        return {
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 3),
            "phases_completed": self.phases_completed,
            "total_phases": len(self.phase_results),
            "phase_results": [
                {
                    "phase": pr.phase_name,
                    "success": pr.success,
                    "duration": round(pr.duration_seconds, 3),
                    "error": pr.error,
                    "timed_out": pr.timed_out,
                }
                for pr in self.phase_results
            ],
            "errors": self.errors,
            "timeout_occurred": self.timeout_occurred,
            "force_killed": self.force_killed,
            "is_successful": self.is_successful,
        }


class GracefulShutdownManager:
    """
    优雅停机管理器

    提供分阶段的、带超时保护的停机流程。

    停机流程：
    1. DRAINING（排空）- 等待进行中的操作完成
    2. STOPPING_SERVICES（停止服务）- 断开外部连接
    3. CLEANUP（清理）- 释放内部资源

    每个阶段都有独立的超时控制，总时间不超过 total_timeout。
    """

    def __init__(
        self,
        config: ShutdownConfig | None = None,
        on_drain: Callable[[], Awaitable[None]] | None = None,
        on_stop_services: Callable[[], Awaitable[None]] | None = None,
        on_cleanup: Callable[[], Awaitable[None]] | None = None,
    ):
        """
        初始化停机管理器

        Args:
            config: 停机配置，如果为None则使用默认配置
            on_drain: 排空阶段的回调函数
            on_stop_services: 停止服务阶段的回调函数
            on_cleanup: 清理阶段的回调函数
        """
        self.config = config or ShutdownConfig()
        self.status = ShutdownStatus()

        # 各阶段的回调函数
        self._on_drain = on_drain
        self._on_stop_services = on_stop_services
        self._on_cleanup = on_cleanup

    async def shutdown(self) -> ShutdownStatus:
        """
        执行完整的优雅停机流程

        Returns:
            ShutdownStatus: 停机状态报告
        """
        self.status.started_at = datetime.now()
        self.status.phase = ShutdownPhase.DRAINING

        logger.info("[GracefulShutdown] ════════════════════════════════════")
        logger.info("[GracefulShutdown] 开始优雅停机流程")
        logger.info(
            f"[GracefulShutdown] 配置: "
            f"总超时={self.config.total_timeout}s, "
            f"排空超时={self.config.drain_timeout}s, "
            f"服务停止超时={self.config.service_stop_timeout}s, "
            f"强制终止={'启用' if self.config.force_kill_after_timeout else '禁用'}"
        )
        logger.info("[GracefulShutdown] ════════════════════════════════════")

        try:
            # Phase 1: 排空进行中的操作
            if not self.config.skip_drain:
                await self._execute_phase_with_timeout(
                    phase_name="DRAINING",
                    handler=self._on_drain,
                    timeout=self.config.drain_timeout,
                )
            else:
                logger.info("[GracefulShutdown] [DRAINING] 跳过（配置禁用）")

            # Phase 2: 停止外部服务
            if not self.config.skip_service_stop:
                remaining_after_drain = max(
                    0,
                    self.config.total_timeout - (datetime.now() - self.status.started_at).total_seconds(),
                )
                service_timeout = min(remaining_after_drain, self.config.service_stop_timeout)

                await self._execute_phase_with_timeout(
                    phase_name="STOPPING_SERVICES",
                    handler=self._on_stop_services,
                    timeout=service_timeout,
                )
            else:
                logger.info("[GracefulShutdown] [STOPPING_SERVICES] 跳过（配置禁用）")

            # Phase 3: 清理内部资源
            elapsed_so_far = (datetime.now() - self.status.started_at).total_seconds()
            cleanup_timeout = max(0, self.config.total_timeout - elapsed_so_far)

            await self._execute_phase_with_timeout(
                phase_name="CLEANUP",
                handler=self._on_cleanup,
                timeout=cleanup_timeout,
            )

            # 完成
            self.status.phase = ShutdownPhase.COMPLETED
            self.status.completed_at = datetime.now()
            self.status.duration_seconds = (self.status.completed_at - self.status.started_at).total_seconds()

            self._log_completion()

        except Exception as e:
            logger.exception(f"[GracefulShutdown] 停机流程发生未预期异常: {e}")
            self.status.phase = ShutdownPhase.ERROR
            self.status.errors.append(f"Unexpected error: {e!s}")
            self.status.completed_at = datetime.now()
            self.status.duration_seconds = (self.status.completed_at - self.status.started_at).total_seconds()

        return self.status

    async def _execute_phase_with_timeout(
        self,
        phase_name: str,
        handler: Callable[[], Awaitable[None]] | None,
        timeout: float,
    ) -> None:
        """
        执行单个停机阶段（带超时控制）

        Args:
            phase_name: 阶段名称
            handler: 该阶段的回调函数
            timeout: 该阶段的超时时间（秒）
        """
        # 安全地设置阶段（兼容字符串和枚举）
        try:
            self.status.phase = ShutdownPhase(phase_name)
        except ValueError:
            # 如果字符串不匹配枚举值，保持当前阶段
            logger.warning(f"[GracefulShutdown] 未知阶段: {phase_name}")

        phase_start = datetime.now()

        logger.info(f"[GracefulShutdown] [{phase_name}] 开始执行 (超时限制: {timeout:.1f}s)")

        if handler is None:
            logger.debug(f"[GracefulShutdown] [{phase_name}] 无处理器，跳过")
            result = PhaseResult(
                phase_name=phase_name,
                success=True,
                duration_seconds=0.0,
            )
            self.status.phase_results.append(result)
            self.status.phases_completed += 1
            return

        try:
            await asyncio.wait_for(
                self._safe_execute_handler(phase_name, handler),
                timeout=timeout,
            )

            duration = (datetime.now() - phase_start).total_seconds()
            result = PhaseResult(
                phase_name=phase_name,
                success=True,
                duration_seconds=duration,
            )
            self.status.phase_results.append(result)
            self.status.phases_completed += 1

            logger.info(f"[GracefulShutdown] [{phase_name}] ✓ 完成 ({duration:.2f}s)")

        except TimeoutError:
            duration = (datetime.now() - phase_start).total_seconds()
            error_msg = f"{phase_name} 阶段超时 ({timeout:.1f}s)"
            logger.warning(f"[GracefulShutdown] [{phase_name}] ✗ {error_msg}")

            result = PhaseResult(
                phase_name=phase_name,
                success=False,
                duration_seconds=duration,
                error=error_msg,
                timed_out=True,
            )
            self.status.phase_results.append(result)
            self.status.errors.append(error_msg)

            # 检查是否需要强制终止
            if self.config.force_kill_after_timeout:
                self.status.timeout_occurred = True
                logger.error(f"[GracefulShutdown] [{phase_name}] 触发强制终止策略...")
                self._force_kill()

        except Exception as e:
            duration = (datetime.now() - phase_start).total_seconds()
            error_msg = f"{phase_name} 阶段异常: {e!s}"
            logger.error(f"[GracefulShutdown] [{phase_name}] ✗ {error_msg}")

            result = PhaseResult(
                phase_name=phase_name,
                success=False,
                duration_seconds=duration,
                error=error_msg,
            )
            self.status.phase_results.append(result)
            self.status.errors.append(error_msg)

    async def _safe_execute_handler(
        self,
        phase_name: str,
        handler: Callable[[], Awaitable[None]],
    ) -> None:
        """安全地执行回调函数（捕获所有异常）"""
        try:
            await handler()
        except Exception as e:
            logger.error(f"[GracefulShutdown] [{phase_name}] 处理器抛出异常: {e}")
            raise

    def _force_kill(self):
        """强制终止当前进程"""
        try:
            self.status.force_killed = True
            pid = os.getpid()
            logger.warning(f"[GracefulShutdown] 发送 SIGTERM 到进程 {pid}")
            os.kill(pid, signal.SIGTERM)

        except Exception as e:
            logger.error(f"[GracefulShutdown] 强制终止失败: {e}")

    def _log_completion(self):
        """记录停机完成的汇总信息"""
        logger.info("[GracefulShutdown] ════════════════════════════════════")
        logger.info("[GracefulShutdown] 停机流程完成")
        logger.info(f"[GracefulShutdown] 状态: {'✓ 成功' if self.status.is_successful else '✗ 失败'}")
        logger.info(f"[GracefulShutdown] 总耗时: {self.status.duration_seconds:.2f}s")
        logger.info(f"[GracefulShutdown] 完成阶段: {self.status.phases_completed}/{len(self.status.phase_results)}")

        if self.status.errors:
            logger.warning("[GracefulShutdown] 错误列表:")
            for err in self.status.errors:
                logger.warning(f"  - {err}")

        if self.status.timeout_occurred:
            logger.error("[GracefulShutdown] ⚠ 曾触发超时机制")

        if self.status.force_killed:
            logger.error("[GracefulShutdown] ⚠ 进程已被强制终止")

        logger.info("[GracefulShutdown] ════════════════════════════════════")


# 全局实例
_shutdown_manager: GracefulShutdownManager | None = None


def get_shutdown_manager() -> GracefulShutdownManager:
    """获取全局停机管理器（懒初始化单例）"""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdownManager()
    return _shutdown_manager


def reset_shutdown_manager():
    """重置全局停机管理器（用于测试）"""
    global _shutdown_manager
    _shutdown_manager = None
