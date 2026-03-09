"""性能监控模块单元测试

测试PerformanceMonitor类的各项功能，包括:
- 单例模式
- 指标记录
- 统计计算
- 告警功能
- 数据持久化
"""

import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 直接导入 performance_monitor 模块，避免循环导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "ai_model"))
from performance_monitor import PerformanceMonitor, get_performance_monitor


class TestPerformanceMonitorSingleton:
    """测试单例模式"""

    def test_singleton_instance(self):
        """测试单例模式确保只有一个实例"""
        # 重置单例以便测试
        PerformanceMonitor._instance = None

        monitor1 = PerformanceMonitor()
        monitor2 = PerformanceMonitor()

        assert monitor1 is monitor2

    def test_thread_safety(self):
        """测试单例的线程安全性"""
        # 重置单例以便测试
        PerformanceMonitor._instance = None

        instances = []

        def create_instance():
            instance = PerformanceMonitor()
            instances.append(instance)

        # 创建多个线程同时获取实例
        threads = [threading.Thread(target=create_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有实例应该是同一个对象
        assert len(set(id(i) for i in instances)) == 1

    def test_get_performance_monitor_helper(self):
        """测试get_performance_monitor辅助函数"""
        # 重置单例以便测试
        PerformanceMonitor._instance = None

        monitor1 = get_performance_monitor()
        monitor2 = get_performance_monitor()

        assert monitor1 is monitor2


class TestPerformanceMonitorRecording:
    """测试指标记录功能"""

    @pytest.fixture(autouse=True)
    def setup_monitor(self):
        """每个测试前重置监控器状态"""
        # 重置单例
        PerformanceMonitor._instance = None

        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.monitor = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)

        yield

        # 清理
        self.monitor.clear_data()
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_record_successful_request(self):
        """测试记录成功请求"""
        self.monitor.record_request(
            model_id="gpt-4",
            success=True,
            generation_time=2.5,
            tokens_used=150,
        )

        stats = self.monitor.get_stats()
        assert stats["total_requests"] == 1
        assert stats["successful_requests"] == 1
        assert stats["failed_requests"] == 0
        assert stats["success_rate"] == 1.0

    def test_record_failed_request(self):
        """测试记录失败请求"""
        self.monitor.record_request(
            model_id="gpt-4",
            success=False,
            generation_time=5.0,
            tokens_used=None,
            error_code="api_error",
        )

        stats = self.monitor.get_stats()
        assert stats["total_requests"] == 1
        assert stats["successful_requests"] == 0
        assert stats["failed_requests"] == 1
        assert stats["success_rate"] == 0.0

    def test_record_multiple_requests(self):
        """测试记录多个请求"""
        # 记录多个成功和失败请求
        for i in range(5):
            self.monitor.record_request(
                model_id="gpt-4",
                success=True,
                generation_time=1.0 + i * 0.5,
                tokens_used=100 + i * 10,
            )

        for i in range(3):
            self.monitor.record_request(
                model_id="gpt-4",
                success=False,
                generation_time=2.0 + i * 0.3,
                tokens_used=None,
                error_code="timeout",
            )

        stats = self.monitor.get_stats()
        assert stats["total_requests"] == 8
        assert stats["successful_requests"] == 5
        assert stats["failed_requests"] == 3
        assert stats["success_rate"] == 0.625

    def test_record_with_different_models(self):
        """测试记录不同模型的请求"""
        self.monitor.record_request(
            model_id="gpt-4",
            success=True,
            generation_time=2.0,
            tokens_used=200,
        )
        self.monitor.record_request(
            model_id="gpt-3.5",
            success=True,
            generation_time=1.0,
            tokens_used=150,
        )

        gpt4_stats = self.monitor.get_stats(model_id="gpt-4")
        gpt35_stats = self.monitor.get_stats(model_id="gpt-3.5")

        assert gpt4_stats["total_requests"] == 1
        assert gpt35_stats["total_requests"] == 1


class TestPerformanceMonitorStats:
    """测试统计计算功能"""

    @pytest.fixture(autouse=True)
    def setup_monitor(self):
        """每个测试前重置监控器状态"""
        PerformanceMonitor._instance = None
        self.temp_dir = tempfile.mkdtemp()
        self.monitor = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)

        # 添加测试数据
        self._add_test_data()

        yield

        self.monitor.clear_data()
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def _add_test_data(self):
        """添加测试数据"""
        # 成功请求
        for i in range(3):
            self.monitor.record_request(
                model_id="gpt-4",
                success=True,
                generation_time=2.0 + i,
                tokens_used=100 + i * 50,
            )
        # 失败请求
        self.monitor.record_request(
            model_id="gpt-4",
            success=False,
            generation_time=5.0,
            tokens_used=None,
            error_code="api_error",
        )

    def test_get_stats_basic(self):
        """测试基本统计功能"""
        stats = self.monitor.get_stats()

        assert stats["total_requests"] == 4
        assert stats["successful_requests"] == 3
        assert stats["failed_requests"] == 1
        assert stats["success_rate"] == 0.75

    def test_get_stats_generation_time(self):
        """测试生成时间统计"""
        stats = self.monitor.get_stats()

        # 生成时间: 2.0, 3.0, 4.0, 5.0
        assert stats["avg_generation_time"] == 3.5
        assert stats["min_generation_time"] == 2.0
        assert stats["max_generation_time"] == 5.0

    def test_get_stats_tokens(self):
        """测试Token统计"""
        stats = self.monitor.get_stats()

        # Tokens: 100, 150, 200 (失败请求为None)
        assert stats["avg_tokens_used"] == 150.0
        assert stats["total_tokens_used"] == 450

    def test_get_stats_by_model(self):
        """测试按模型过滤统计"""
        # 添加其他模型的数据
        self.monitor.record_request(
            model_id="gpt-3.5",
            success=True,
            generation_time=1.0,
            tokens_used=50,
        )

        gpt4_stats = self.monitor.get_stats(model_id="gpt-4")
        gpt35_stats = self.monitor.get_stats(model_id="gpt-3.5")
        all_stats = self.monitor.get_stats()

        assert gpt4_stats["total_requests"] == 4
        assert gpt35_stats["total_requests"] == 1
        assert all_stats["total_requests"] == 5

    def test_get_stats_by_date_range(self):
        """测试按日期范围过滤统计"""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        one_hour_later = now + timedelta(hours=1)

        stats = self.monitor.get_stats(
            start_date=one_hour_ago,
            end_date=one_hour_later,
        )

        assert stats["total_requests"] == 4

    def test_get_stats_empty_data(self):
        """测试无数据时的统计"""
        self.monitor.clear_data()
        stats = self.monitor.get_stats()

        assert stats["total_requests"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_generation_time"] == 0.0

    def test_get_summary(self):
        """测试获取总体摘要"""
        # 添加不同模型的数据
        self.monitor.record_request(
            model_id="gpt-3.5",
            success=True,
            generation_time=1.0,
            tokens_used=50,
        )

        summary = self.monitor.get_summary()

        assert "overall" in summary
        assert "by_model" in summary
        assert "time_range" in summary
        assert summary["overall"]["total_requests"] == 5
        assert "gpt-4" in summary["by_model"]
        assert "gpt-3.5" in summary["by_model"]


class TestPerformanceMonitorAlerts:
    """测试告警功能"""

    @pytest.fixture(autouse=True)
    def setup_monitor(self):
        """每个测试前重置监控器状态"""
        PerformanceMonitor._instance = None
        self.temp_dir = tempfile.mkdtemp()
        self.monitor = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)

        yield

        self.monitor.clear_data()
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_check_alerts_high_latency(self):
        """测试高延迟告警"""
        # 记录高延迟请求（超过30秒阈值）
        self.monitor.record_request(
            model_id="gpt-4",
            success=True,
            generation_time=35.0,
            tokens_used=200,
        )

        alerts = self.monitor.check_alerts()

        assert len(alerts) >= 1
        latency_alerts = [a for a in alerts if a["type"] == "high_latency"]
        assert len(latency_alerts) >= 1
        assert latency_alerts[0]["model_id"] == "gpt-4"
        assert latency_alerts[0]["value"] == 35.0

    def test_check_alerts_high_failure_rate(self):
        """测试高失败率告警"""
        # 记录多个失败请求（超过20%失败率）
        for _ in range(3):
            self.monitor.record_request(
                model_id="gpt-4",
                success=False,
                generation_time=2.0,
                tokens_used=None,
                error_code="api_error",
            )
        # 只记录1个成功请求（25%成功率，即75%失败率）
        self.monitor.record_request(
            model_id="gpt-4",
            success=True,
            generation_time=2.0,
            tokens_used=100,
        )

        alerts = self.monitor.check_alerts()

        failure_alerts = [a for a in alerts if a["type"] == "high_failure_rate"]
        assert len(failure_alerts) >= 1
        assert failure_alerts[0]["model_id"] == "gpt-4"

    def test_check_alerts_no_alerts(self):
        """测试正常情况无告警"""
        # 记录正常请求
        for _ in range(5):
            self.monitor.record_request(
                model_id="gpt-4",
                success=True,
                generation_time=5.0,  # 低于30秒阈值
                tokens_used=100,
            )

        alerts = self.monitor.check_alerts()

        # 成功率100%，平均耗时5秒，不应触发告警
        latency_alerts = [a for a in alerts if a["type"] == "high_latency"]
        failure_alerts = [a for a in alerts if a["type"] == "high_failure_rate"]
        assert len(latency_alerts) == 0
        assert len(failure_alerts) == 0

    def test_check_alerts_empty_data(self):
        """测试无数据时无告警"""
        alerts = self.monitor.check_alerts()
        assert len(alerts) == 0


class TestPerformanceMonitorPersistence:
    """测试数据持久化功能"""

    @pytest.fixture(autouse=True)
    def setup_monitor(self):
        """每个测试前重置监控器状态"""
        PerformanceMonitor._instance = None
        self.temp_dir = tempfile.mkdtemp()

        yield

        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_data_persistence(self):
        """测试数据持久化到文件"""
        monitor = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=1)

        # 记录数据
        monitor.record_request(
            model_id="gpt-4",
            success=True,
            generation_time=2.0,
            tokens_used=100,
        )

        # 强制持久化
        monitor.force_persist()

        # 检查文件是否存在
        data_file = Path(self.temp_dir) / "ai_model_performance.json"
        assert data_file.exists()

        # 读取并验证数据
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["model_id"] == "gpt-4"
        assert data[0]["success"] is True
        assert data[0]["generation_time"] == 2.0
        assert data[0]["tokens_used"] == 100

    def test_data_loading(self):
        """测试从文件加载数据"""
        # 先创建一些数据
        monitor1 = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)
        monitor1.record_request(
            model_id="gpt-4",
            success=True,
            generation_time=2.0,
            tokens_used=100,
        )
        monitor1.force_persist()

        # 重置单例并创建新实例
        PerformanceMonitor._instance = None
        monitor2 = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)

        # 验证数据已加载
        stats = monitor2.get_stats()
        assert stats["total_requests"] == 1

    def test_clear_data(self):
        """测试清除数据"""
        monitor = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)

        # 添加数据
        for _ in range(5):
            monitor.record_request(
                model_id="gpt-4",
                success=True,
                generation_time=2.0,
                tokens_used=100,
            )

        # 清除所有数据
        cleared_count = monitor.clear_data()
        assert cleared_count == 5

        stats = monitor.get_stats()
        assert stats["total_requests"] == 0

    def test_clear_old_data(self):
        """测试清除旧数据"""
        monitor = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)

        # 添加数据
        for _ in range(3):
            monitor.record_request(
                model_id="gpt-4",
                success=True,
                generation_time=2.0,
                tokens_used=100,
            )

        # 清除7天前的数据（应该不清除任何数据）
        cleared_count = monitor.clear_data(older_than_days=7)
        assert cleared_count == 0

        stats = monitor.get_stats()
        assert stats["total_requests"] == 3


class TestPerformanceMonitorThreadSafety:
    """测试线程安全性"""

    @pytest.fixture(autouse=True)
    def setup_monitor(self):
        """每个测试前重置监控器状态"""
        PerformanceMonitor._instance = None
        self.temp_dir = tempfile.mkdtemp()
        self.monitor = PerformanceMonitor(data_dir=self.temp_dir, persistence_interval=3600)

        yield

        self.monitor.clear_data()
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_concurrent_record_request(self):
        """测试并发记录请求"""
        def record_requests(model_id, count):
            for i in range(count):
                self.monitor.record_request(
                    model_id=model_id,
                    success=True,
                    generation_time=1.0 + i * 0.1,
                    tokens_used=100,
                )

        # 创建多个线程并发记录
        threads = []
        for i in range(5):
            t = threading.Thread(target=record_requests, args=(f"model-{i}", 10))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证所有请求都被记录
        stats = self.monitor.get_stats()
        assert stats["total_requests"] == 50

    def test_concurrent_read_write(self):
        """测试并发读写"""
        write_count = [0]
        read_count = [0]

        def writer():
            for _ in range(20):
                self.monitor.record_request(
                    model_id="gpt-4",
                    success=True,
                    generation_time=2.0,
                    tokens_used=100,
                )
                write_count[0] += 1

        def reader():
            for _ in range(20):
                _ = self.monitor.get_stats()
                read_count[0] += 1

        # 创建读写线程
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=writer))
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证所有操作都完成
        assert write_count[0] == 60
        assert read_count[0] == 60
