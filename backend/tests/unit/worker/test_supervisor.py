"""
Worker Supervisor 模块单元测试

测试 WorkerSupervisor、RestartPolicy 和 HealthCheckConfig 的功能
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from worker.supervisor import WorkerSupervisor, RestartPolicy, HealthCheckConfig
from worker.state import WorkerState, WorkerStatus


class TestRestartPolicy:
    """测试 RestartPolicy 类"""

    def test_default_values(self):
        """测试默认值"""
        policy = RestartPolicy()
        assert policy.max_restarts == 3
        assert policy.restart_window == 300
        assert policy.backoff_base == 1.0
        assert policy.backoff_max == 60.0

    def test_custom_values(self):
        """测试自定义值"""
        policy = RestartPolicy(
            max_restarts=5,
            restart_window=600,
            backoff_base=2.0,
            backoff_max=120.0
        )
        assert policy.max_restarts == 5
        assert policy.restart_window == 600
        assert policy.backoff_base == 2.0
        assert policy.backoff_max == 120.0


class TestHealthCheckConfig:
    """测试 HealthCheckConfig 类"""

    def test_default_values(self):
        """测试默认值"""
        config = HealthCheckConfig()
        assert config.heartbeat_timeout == 30
        assert config.check_interval == 10
        assert config.unhealthy_threshold == 3

    def test_custom_values(self):
        """测试自定义值"""
        config = HealthCheckConfig(
            heartbeat_timeout=60,
            check_interval=20,
            unhealthy_threshold=5
        )
        assert config.heartbeat_timeout == 60
        assert config.check_interval == 20
        assert config.unhealthy_threshold == 5


class TestWorkerSupervisor:
    """测试 WorkerSupervisor 类"""

    @pytest.fixture
    def supervisor(self):
        """创建测试用的 WorkerSupervisor 实例"""
        return WorkerSupervisor()

    @pytest.fixture
    def worker_status(self):
        """创建测试用的 WorkerStatus 实例"""
        status = WorkerStatus(worker_id="worker-001")
        status.update_state(WorkerState.INITIALIZED)
        status.update_state(WorkerState.STARTING)
        status.update_state(WorkerState.RUNNING)
        return status

    def test_initial_state(self, supervisor):
        """测试初始状态"""
        assert supervisor.restart_policy.max_restarts == 3
        assert supervisor.health_config.heartbeat_timeout == 30
        assert len(supervisor._worker_status) == 0
        assert len(supervisor._heartbeat_history) == 0
        assert len(supervisor._restart_history) == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, supervisor):
        """测试启动和停止"""
        result = await supervisor.start()
        assert result is True
        assert supervisor._running is True
        
        result = await supervisor.stop()
        assert result is True
        assert supervisor._running is False

    def test_register_worker(self, supervisor, worker_status):
        """测试注册 Worker"""
        supervisor.register_worker("worker-001", worker_status)
        
        assert "worker-001" in supervisor._worker_status
        assert "worker-001" in supervisor._heartbeat_history
        assert "worker-001" in supervisor._restart_history
        assert supervisor._worker_status["worker-001"] == worker_status

    def test_unregister_worker(self, supervisor, worker_status):
        """测试注销 Worker"""
        supervisor.register_worker("worker-001", worker_status)
        supervisor.unregister_worker("worker-001")
        
        assert "worker-001" not in supervisor._worker_status
        assert "worker-001" not in supervisor._heartbeat_history
        assert "worker-001" not in supervisor._restart_history

    def test_update_heartbeat(self, supervisor, worker_status):
        """测试更新心跳"""
        supervisor.register_worker("worker-001", worker_status)
        
        supervisor.update_heartbeat("worker-001")
        
        history = supervisor._heartbeat_history["worker-001"]
        assert len(history) == 1
        assert isinstance(history[0], datetime)

    def test_update_heartbeat_multiple(self, supervisor, worker_status):
        """测试多次更新心跳"""
        supervisor.register_worker("worker-001", worker_status)
        
        supervisor.update_heartbeat("worker-001")
        supervisor.update_heartbeat("worker-001")
        supervisor.update_heartbeat("worker-001")
        
        history = supervisor._heartbeat_history["worker-001"]
        assert len(history) == 3

    def test_update_heartbeat_cleanup_old(self, supervisor, worker_status):
        """测试清理旧的心跳记录"""
        supervisor.register_worker("worker-001", worker_status)
        
        # 添加一个旧的心跳记录
        old_time = datetime.now() - timedelta(seconds=100)
        supervisor._heartbeat_history["worker-001"].append(old_time)
        
        supervisor.update_heartbeat("worker-001")
        
        # 旧记录应该被清理
        history = supervisor._heartbeat_history["worker-001"]
        assert len(history) == 1  # 只有新的记录
        assert history[0] > old_time

    def test_record_restart(self, supervisor, worker_status):
        """测试记录重启"""
        supervisor.register_worker("worker-001", worker_status)
        
        supervisor.record_restart("worker-001")
        
        history = supervisor._restart_history["worker-001"]
        assert len(history) == 1
        assert isinstance(history[0], datetime)

    def test_record_restart_multiple(self, supervisor, worker_status):
        """测试多次记录重启"""
        supervisor.register_worker("worker-001", worker_status)
        
        supervisor.record_restart("worker-001")
        supervisor.record_restart("worker-001")
        
        history = supervisor._restart_history["worker-001"]
        assert len(history) == 2

    def test_record_restart_cleanup_old(self, supervisor, worker_status):
        """测试清理旧的重启记录"""
        supervisor.register_worker("worker-001", worker_status)
        
        # 添加一个旧的重启记录
        old_time = datetime.now() - timedelta(seconds=400)
        supervisor._restart_history["worker-001"].append(old_time)
        
        supervisor.record_restart("worker-001")
        
        # 旧记录应该被清理（因为超过了 restart_window）
        history = supervisor._restart_history["worker-001"]
        assert len(history) == 1  # 只有新的记录

    def test_is_healthy_running_with_heartbeat(self, supervisor, worker_status):
        """测试健康状态 - 运行中且有心跳"""
        supervisor.register_worker("worker-001", worker_status)
        worker_status.update_heartbeat()
        
        assert supervisor.is_healthy("worker-001") is True

    def test_is_healthy_no_heartbeat(self, supervisor, worker_status):
        """测试健康状态 - 无心跳"""
        supervisor.register_worker("worker-001", worker_status)
        # 不更新心跳
        
        assert supervisor.is_healthy("worker-001") is False

    def test_is_healthy_heartbeat_timeout(self, supervisor, worker_status):
        """测试健康状态 - 心跳超时"""
        supervisor.register_worker("worker-001", worker_status)
        worker_status.update_heartbeat()
        # 模拟心跳超时
        worker_status.last_heartbeat = datetime.now() - timedelta(seconds=60)
        
        assert supervisor.is_healthy("worker-001") is False

    def test_is_healthy_not_running(self, supervisor):
        """测试健康状态 - 非运行状态"""
        status = WorkerStatus(worker_id="worker-001")
        # 保持 INITIALIZING 状态
        supervisor.register_worker("worker-001", status)
        status.update_heartbeat()
        
        assert supervisor.is_healthy("worker-001") is False

    def test_is_healthy_nonexistent_worker(self, supervisor):
        """测试健康状态 - 不存在的 Worker"""
        assert supervisor.is_healthy("nonexistent") is False

    def test_should_restart_no_history(self, supervisor, worker_status):
        """测试是否应该重启 - 无历史记录"""
        supervisor.register_worker("worker-001", worker_status)
        
        assert supervisor.should_restart("worker-001") is True

    def test_should_restart_under_limit(self, supervisor, worker_status):
        """测试是否应该重启 - 低于限制"""
        supervisor.register_worker("worker-001", worker_status)
        
        # 记录 2 次重启（低于默认限制 3）
        supervisor.record_restart("worker-001")
        supervisor.record_restart("worker-001")
        
        assert supervisor.should_restart("worker-001") is True

    def test_should_restart_over_limit(self, supervisor, worker_status):
        """测试是否应该重启 - 超过限制"""
        supervisor.register_worker("worker-001", worker_status)
        
        # 记录 3 次重启（达到默认限制）
        supervisor.record_restart("worker-001")
        supervisor.record_restart("worker-001")
        supervisor.record_restart("worker-001")
        
        assert supervisor.should_restart("worker-001") is False

    def test_get_restart_delay_no_restarts(self, supervisor, worker_status):
        """测试获取重启延迟 - 无重启历史"""
        supervisor.register_worker("worker-001", worker_status)
        
        delay = supervisor.get_restart_delay("worker-001")
        assert delay == 0.0

    def test_get_restart_delay_with_restarts(self, supervisor, worker_status):
        """测试获取重启延迟 - 有重启历史"""
        supervisor.register_worker("worker-001", worker_status)
        
        supervisor.record_restart("worker-001")
        delay = supervisor.get_restart_delay("worker-001")
        assert delay == 1.0  # backoff_base * 2^0

        supervisor.record_restart("worker-001")
        delay = supervisor.get_restart_delay("worker-001")
        assert delay == 2.0  # backoff_base * 2^1

        supervisor.record_restart("worker-001")
        delay = supervisor.get_restart_delay("worker-001")
        assert delay == 4.0  # backoff_base * 2^2

    def test_get_restart_delay_max_cap(self, supervisor, worker_status):
        """测试获取重启延迟 - 上限"""
        supervisor.register_worker("worker-001", worker_status)
        
        # 记录多次重启
        for _ in range(10):
            supervisor.record_restart("worker-001")
        
        delay = supervisor.get_restart_delay("worker-001")
        assert delay == 60.0  # backoff_max

    def test_get_health_report(self, supervisor, worker_status):
        """测试获取健康报告"""
        supervisor.register_worker("worker-001", worker_status)
        supervisor.update_heartbeat("worker-001")
        supervisor.record_restart("worker-001")
        
        report = supervisor.get_health_report("worker-001")
        
        assert report is not None
        assert report["worker_id"] == "worker-001"
        assert report["state"] == "running"
        assert report["is_healthy"] is True
        assert report["restart_count"] == 1
        assert report["heartbeat_count"] == 1
        assert "last_heartbeat" in report

    def test_get_health_report_nonexistent(self, supervisor):
        """测试获取不存在的 Worker 健康报告"""
        report = supervisor.get_health_report("nonexistent")
        assert report is None

    def test_get_all_health_reports(self, supervisor, worker_status):
        """测试获取所有健康报告"""
        supervisor.register_worker("worker-001", worker_status)
        
        status2 = WorkerStatus(worker_id="worker-002")
        status2.update_state(WorkerState.RUNNING)
        supervisor.register_worker("worker-002", status2)
        
        reports = supervisor.get_all_health_reports()
        
        assert len(reports) == 2
        assert "worker-001" in reports
        assert "worker-002" in reports

    def test_register_health_handler(self, supervisor, worker_status):
        """测试注册健康处理器"""
        handler_called = []

        def handler(worker_id, is_healthy):
            handler_called.append((worker_id, is_healthy))

        supervisor.register_health_handler(handler)

        supervisor.register_worker("worker-001", worker_status)
        supervisor.update_heartbeat("worker-001")

        # 模拟心跳过期，使 Worker 不健康
        old_time = datetime.now() - timedelta(seconds=supervisor.health_config.heartbeat_timeout + 10)
        worker_status.last_heartbeat = old_time

        # 手动调用检查
        asyncio.run(supervisor._check_worker_health("worker-001"))

        assert len(handler_called) == 1
        assert handler_called[0] == ("worker-001", False)

    def test_register_restart_handler(self, supervisor, worker_status):
        """测试注册重启处理器"""
        handler_called = []
        
        def handler(worker_id, restart_count):
            handler_called.append((worker_id, restart_count))
        
        supervisor.register_restart_handler(handler)
        
        supervisor.register_worker("worker-001", worker_status)
        supervisor.record_restart("worker-001")
        
        assert len(handler_called) == 1
        assert handler_called[0] == ("worker-001", 1)

    def test_is_restart_recommended(self, supervisor, worker_status):
        """测试是否建议重启"""
        supervisor.register_worker("worker-001", worker_status)
        
        # 初始状态
        assert supervisor.is_restart_recommended("worker-001") is False
        
        # 增加不健康计数
        supervisor._unhealthy_count["worker-001"] = 3
        
        assert supervisor.is_restart_recommended("worker-001") is True

    def test_get_stats(self, supervisor, worker_status):
        """测试获取统计信息"""
        supervisor.register_worker("worker-001", worker_status)
        # 为第一个 Worker 添加心跳，使其健康
        supervisor.update_heartbeat("worker-001")

        # 添加第二个 Worker（不健康状态）
        status2 = WorkerStatus(worker_id="worker-002")
        status2.update_state(WorkerState.ERROR)
        supervisor.register_worker("worker-002", status2)

        stats = supervisor.get_stats()

        assert stats["total_workers"] == 2
        assert stats["healthy_workers"] == 1
        assert stats["unhealthy_workers"] == 1
        assert stats["total_restarts"] == 0
        assert "restart_policy" in stats
        assert "health_config" in stats

    @pytest.mark.asyncio
    async def test_health_check_loop(self, supervisor, worker_status):
        """测试健康检查循环"""
        supervisor.register_worker("worker-001", worker_status)
        
        # 启动监控
        await supervisor.start()
        
        # 等待一段时间让检查循环运行
        await asyncio.sleep(0.1)
        
        # 停止监控
        await supervisor.stop()
        
        # 验证运行状态
        assert supervisor._running is False

    @pytest.mark.asyncio
    async def test_check_worker_health_healthy(self, supervisor, worker_status):
        """测试检查健康的 Worker"""
        supervisor.register_worker("worker-001", worker_status)
        worker_status.update_heartbeat()
        
        await supervisor._check_worker_health("worker-001")
        
        # 健康状态应该保持不变
        assert supervisor._unhealthy_count.get("worker-001", 0) == 0

    @pytest.mark.asyncio
    async def test_check_worker_health_unhealthy(self, supervisor, worker_status):
        """测试检查不健康的 Worker"""
        supervisor.register_worker("worker-001", worker_status)
        # 不更新心跳，使其不健康
        
        await supervisor._check_worker_health("worker-001")
        
        # 不健康计数应该增加
        assert supervisor._unhealthy_count.get("worker-001", 0) == 1

    @pytest.mark.asyncio
    async def test_check_worker_health_recovery(self, supervisor, worker_status):
        """测试 Worker 恢复健康"""
        supervisor.register_worker("worker-001", worker_status)
        supervisor._unhealthy_count["worker-001"] = 2
        worker_status.update_heartbeat()
        
        await supervisor._check_worker_health("worker-001")
        
        # 不健康计数应该重置
        assert supervisor._unhealthy_count.get("worker-001", 0) == 0
