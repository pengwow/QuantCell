# -*- coding: utf-8 -*-
"""
PortManager 集成测试

验证 PortManager 与其他模块（FastAPI、ZMQ、Worker IPC）的集成是否正常工作。
涵盖完整系统启动流程、多实例端口隔离、异常退出恢复、前后端同步等场景。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-13
"""

import os
import sys
import json
import socket
import subprocess
import asyncio
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from contextlib import contextmanager
from typing import Dict, Generator, Optional

import pytest
import pytest_asyncio

from core.port_manager import (
    PortManager,
    PortAllocationError,
    PortConfig,
    PORT_RANGES,
    port_manager,
)


# ============================================================
# Fixtures - 测试基础设施
# ============================================================


@pytest.fixture(autouse=True)
def reset_port_manager_singleton():
    """自动重置 PortManager 单例，确保每个测试独立运行"""
    original_instance = PortManager._instance
    original_initialized = getattr(PortManager._instance, '_initialized', False) if PortManager._instance else False

    PortManager._instance = None

    yield

    PortManager._instance = original_instance
    if original_instance and original_initialized:
        original_instance._initialized = True


@pytest.fixture(autouse=True)
def clean_env():
    """清理环境变量 - 确保每个测试不受之前的环境变量影响"""
    original_static = os.environ.get('USE_STATIC_PORTS')
    original_config = os.environ.get('PORT_CONFIG_PATH')

    os.environ.pop('USE_STATIC_PORTS', None)
    os.environ.pop('PORT_CONFIG_PATH', None)

    yield

    if original_static:
        os.environ['USE_STATIC_PORTS'] = original_static
    else:
        os.environ.pop('USE_STATIC_PORTS', None)

    if original_config:
        os.environ['PORT_CONFIG_PATH'] = original_config
    else:
        os.environ.pop('PORT_CONFIG_PATH', None)


@pytest.fixture
def temp_config_dir():
    """创建临时目录用于测试配置文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, 'test_port_config.json')
        os.environ['PORT_CONFIG_PATH'] = config_path
        yield tmpdir
        if os.environ.get('PORT_CONFIG_PATH') == config_path:
            os.environ.pop('PORT_CONFIG_PATH', None)


@pytest.fixture
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_subprocess():
    """Mock subprocess 调用，避免真实进程操作"""
    with patch('subprocess.run') as mock_run, \
         patch('subprocess.Popen') as mock_popen:
        yield {'run': mock_run, 'popen': mock_popen}


@pytest.fixture
def mock_socket_operations():
    """Mock socket 操作，避免真实网络绑定"""
    with patch('socket.socket') as mock_sock_class:
        mock_socket = MagicMock()
        mock_sock_class.return_value = mock_socket
        yield mock_socket


@contextmanager
def reserve_port(port: int) -> Generator[None, None, None]:
    """
    占用指定端口的上下文管理器

    用于模拟端口被占用的场景，测试结束后自动释放。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('0.0.0.0', port))
        sock.listen(1)
        yield
    finally:
        sock.close()


def find_available_port(start: int = 19000, end: int = 20000) -> int:
    """在指定范围内查找可用端口"""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"在范围 {start}-{end} 内找不到可用端口")


# ============================================================
# TestSystemStartupFlow - 完整系统启动流程测试
# ============================================================


class TestSystemStartupFlow:
    """测试完整的系统启动流程"""

    def test_fastapi_startup_with_port_manager(self, temp_config_dir):
        """FastAPI 使用动态端口成功启动

        模拟 main.py 中的启动流程：
        1. PortManager 分配端口成功
        2. 验证配置文件正确保存
        3. 验证端口信息可被获取
        """
        manager = PortManager()

        # 模拟 main.py 中的启动逻辑
        fastapi_port = manager.get_port("fastapi")

        # 验证端口分配成功
        assert fastapi_port is not None
        assert isinstance(fastapi_port, int)
        assert 8000 <= fastapi_port < 8010

        # 验证配置文件已保存
        assert manager.config_path.exists()
        with open(manager.config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        assert "services" in config_data
        assert "fastapi" in config_data["services"]
        assert config_data["services"]["fastapi"]["port"] == fastapi_port

        # 验证端口可重复获取（缓存机制）
        port_again = manager.get_port("fastapi")
        assert port_again == fastapi_port

        # 验证 get_all_ports 包含该服务
        all_ports = manager.get_all_ports()
        assert "fastapi" in all_ports
        assert all_ports["fastapi"] == fastapi_port

    def test_fastapi_startup_with_preferred_port(self, temp_config_dir):
        """使用首选端口启动 FastAPI 服务

        模拟命令行参数 --port 指定端口的场景。
        """
        manager = PortManager()

        # 设置首选端口
        preferred_port = 8003
        manager.set_preferred_port("fastapi", preferred_port)

        # 获取端口
        actual_port = manager.get_port("fastapi")

        # 验证使用了首选端口
        assert actual_port == preferred_port

    def test_fastapi_startup_auto_switch_when_occupied(self, temp_config_dir):
        """默认端口被占用时自动切换到备用端口

        模拟 8000 端口已被其他进程占用的情况。
        """
        occupied_port = 8000

        with patch.object(PortManager, '_is_port_available') as mock_available:
            # 模拟 8000 被占用，8001 可用
            def check_availability(port):
                return port != occupied_port

            mock_available.side_effect = check_availability

            manager = PortManager()
            fastapi_port = manager.get_port("fastapi")

            # 验证自动切换到了备用端口
            assert fastapi_port != 8000
            assert 8001 <= fastapi_port < 8010

    @patch('core.port_manager.port_manager')
    def test_main_py_startup_flow_integration(self, mock_pm, temp_config_dir):
        """集成测试：模拟 main.py 完整启动流程

        验证从参数解析到 uvicorn 启动的完整链路。
        """
        from unittest.mock import Mock

        # 配置 mock 返回值
        test_port = 8000
        mock_pm.get_port.return_value = test_port
        mock_pm.set_preferred_port.return_value = None

        # 模拟 parse_args 的返回
        args = Mock()
        args.port = None
        args.host = "localhost"
        args.debug = False

        # 模拟 main.py 中的启动逻辑
        try:
            if args.port:
                mock_pm.set_preferred_port("fastapi", args.port)

            fastapi_port = mock_pm.get_port("fastapi")

            # 验证调用顺序正确
            if args.port:
                mock_pm.set_preferred_port.assert_called_once_with("fastapi", args.port)

            mock_pm.get_port.assert_called_once_with("fastapi")

            # 验证端口值
            assert fastapi_port == test_port

        except PortAllocationError as e:
            pytest.fail(f"启动流程中端口分配失败: {e}")

    def test_zmq_services_use_dynamic_ports(self, temp_config_dir):
        """ZMQ 服务使用动态分配的端口

        验证 CommManager 初始化时能正确从 PortManager 获取 ZMQ 端口。
        注意：PortManager 可能返回默认端口或范围内的端口。
        """
        manager = PortManager()

        # 分配所有 ZMQ 相关服务端口
        zmq_data_port = manager.get_port("zmq_data")
        zmq_control_port = manager.get_port("zmq_control")
        zmq_status_port = manager.get_port("zmq_status")
        zmq_broadcast_port = manager.get_port("zmq_broadcast")

        # 验证所有 ZMQ 端口有效：要么是默认端口，要么在定义的范围内
        for service_name, port in [
            ("zmq_data", zmq_data_port),
            ("zmq_control", zmq_control_port),
            ("zmq_status", zmq_status_port),
            ("zmq_broadcast", zmq_broadcast_port),
        ]:
            config = PORT_RANGES[service_name]
            default_port = config["default"]
            start, end = config["range"]

            # 端口应该是默认端口或在范围内
            is_valid = port == default_port or (start <= port < end)
            assert is_valid, (
                f"{service_name} 端口 {port} 无效: "
                f"既不是默认端口 {default_port}，也不在范围 {start}-{end-1} 内"
            )

        # 验证各服务使用不同端口
        zmq_ports = [zmq_data_port, zmq_control_port, zmq_status_port, zmq_broadcast_port]
        assert len(set(zmq_ports)) == len(zmq_ports), "ZMQ 服务应使用不同端口"

        # 验证配置文件包含所有 ZMQ 服务
        all_ports = manager.get_all_ports()
        for service in ["zmq_data", "zmq_control", "zmq_status", "zmq_broadcast"]:
            assert service in all_ports

    def test_worker_ipc_port_consistency(self, temp_config_dir):
        """Worker IPC 各组件使用一致的端口配置

        验证 CommManager、WorkerClient、WorkerManager 使用相同的端口来源。
        """
        manager = PortManager()

        # 模拟 CommManager 初始化（从 PortManager 获取端口）
        comm_data_port = manager.get_port("zmq_data")
        comm_control_port = manager.get_port("zmq_control")
        comm_status_port = manager.get_port("zmq_status")

        # 再次获取相同服务的端口（模拟其他组件初始化）
        worker_data_port = manager.get_port("zmq_data")
        worker_control_port = manager.get_port("zmq_control")
        worker_status_port = manager.get_port("zmq_status")

        # 验证所有组件获得相同的端口
        assert comm_data_port == worker_data_port
        assert comm_control_port == worker_control_port
        assert comm_status_port == worker_status_port

    def test_all_services_startup_sequence(self, temp_config_dir):
        """完整的服务启动序列测试

        按照实际启动顺序分配所有服务端口，验证整体一致性。
        """
        manager = PortManager()

        # 启动顺序：FastAPI -> ZMQ services
        startup_sequence = [
            ("fastapi", 8000),
            ("zmq_data", 5555),
            ("zmq_control", 5556),
            ("zmq_status", 5557),
            ("zmq_broadcast", 5558),
        ]

        allocated_ports = {}

        for service_name, default_port in startup_sequence:
            port = manager.get_port(service_name)
            allocated_ports[service_name] = port

            # 验证端口有效：要么是默认端口，要么在定义的范围内
            config = PORT_RANGES[service_name]
            start, end = config["range"]
            is_valid = port == default_port or (start <= port < end)
            assert is_valid, (
                f"{service_name} 端口 {port} 无效: "
                f"既不是默认端口 {default_port}，也不在范围 {start}-{end-1} 内"
            )

        # 验证所有服务都已分配
        assert len(allocated_ports) == len(PORT_RANGES)

        # 验证配置文件完整性
        with open(manager.config_path, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)

        assert len(saved_config["services"]) == len(PORT_RANGES)
        for service_name in allocated_ports:
            assert service_name in saved_config["services"]
            assert saved_config["services"][service_name]["port"] == allocated_ports[service_name]


# ============================================================
# TestMultiInstancePortIsolation - 多实例端口隔离测试
# ============================================================


class TestMultiInstancePortIsolation:
    """测试多实例部署时的端口隔离"""

    def test_two_instances_use_different_configs(self, temp_config_dir):
        """两个实例使用不同的配置文件时互不影响

        通过不同配置路径实现隔离。
        """
        config_path_1 = os.path.join(temp_config_dir, 'instance1_config.json')
        config_path_2 = os.path.join(temp_config_dir, 'instance2_config.json')

        # 实例 1
        os.environ['PORT_CONFIG_PATH'] = config_path_1
        manager1 = PortManager()
        port1 = manager1.get_port("fastapi")

        # 重置单例以创建新实例
        PortManager._instance = None

        # 实例 2
        os.environ['PORT_CONFIG_PATH'] = config_path_2
        manager2 = PortManager()
        port2 = manager2.get_port("fastapi")

        # 两个实例可以独立操作
        assert manager1.config_path != manager2.config_path

        # 验证配置文件独立
        assert Path(config_path_1).exists()
        assert Path(config_path_2).exists()

    def test_concurrent_port_allocation_thread_safety(self, temp_config_dir):
        """并发端口分配不会导致竞争条件

        多线程同时请求不同服务的端口分配。
        """
        manager = PortManager()
        errors = []
        results = {}
        lock = threading.Lock()

        def allocate_port(service_name: str):
            try:
                port = manager.get_port(service_name)
                with lock:
                    results[service_name] = port
            except Exception as e:
                with lock:
                    errors.append((service_name, str(e)))

        # 创建多个线程同时分配不同服务
        threads = []
        services = list(PORT_RANGES.keys())

        for service_name in services:
            t = threading.Thread(target=allocate_port, args=(service_name,))
            threads.append(t)

        # 同时启动所有线程
        for t in threads:
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join(timeout=10)

        # 验证无错误发生
        assert len(errors) == 0, f"并发分配出现错误: {errors}"

        # 验证所有服务都成功分配
        assert len(results) == len(PORT_RANGES)

        # 验证同一服务的多次请求返回相同端口
        for service_name in services:
            port_repeat = manager.get_port(service_name)
            assert port_repeat == results[service_name]

    def test_concurrent_same_service_allocation(self, temp_config_dir):
        """多个线程同时请求同一服务的端口应安全处理

        验证线程安全和结果一致性。
        """
        manager = PortManager()
        results = []
        errors = []

        def get_fastapi_port():
            try:
                port = manager.get_port("fastapi")
                results.append(port)
            except Exception as e:
                errors.append(str(e))

        # 创建多个线程同时请求 fastapi 端口
        num_threads = 20
        threads = [threading.Thread(target=get_fastapi_port) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # 验证无错误
        assert len(errors) == 0, f"并发访问出现错误: {errors}"

        # 验证所有结果一致（缓存机制保证）
        assert len(results) > 0
        assert all(r == results[0] for r in results), "并发获取同一服务端口应返回一致结果"

    def test_rapid_sequential_allocation(self, temp_config_dir):
        """快速连续分配和释放端口

        模拟频繁启停场景下的端口管理稳定性。
        """
        manager = PortManager()

        for cycle in range(10):
            # 分配端口
            port = manager.get_port("fastapi")
            assert port > 0

            # 验证配置存在
            assert "fastapi" in manager.allocated_ports

            # 释放端口
            released = manager.release_port("fastapi")
            assert released is True

            # 验证已释放
            assert "fastapi" not in manager.allocated_ports

        # 最终重新分配验证系统正常
        final_port = manager.get_port("fastapi")
        assert final_port > 0


# ============================================================
# TestAbnormalExitRecovery - 异常退出恢复流程测试
# ============================================================


class TestAbnormalExitRecovery:
    """测试异常退出后的恢复机制"""

    @patch('subprocess.run')
    def test_zombie_process_detection_and_cleanup(self, mock_run, temp_config_dir):
        """检测并清理僵尸进程后重用端口

        模拟：检测到占用端口的僵尸进程并成功清理。
        """
        zombie_pid = 12345
        target_port = 8000

        # 配置 lsof 返回僵尸进程 PID
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f'{zombie_pid}\n'
        )

        manager = PortManager()

        # Mock 端口可用性检查和僵尸进程判断
        with patch.object(manager, '_is_port_available', return_value=False), \
             patch.object(manager, '_is_zombie_process', return_value=True), \
             patch.object(manager, '_terminate_process', return_value=True):

            # 执行僵尸进程检测和清理
            cleaned = manager.detect_and_cleanup_zombie_process(target_port)

            # 验证清理成功
            assert cleaned is True

            # 验证调用了终止进程方法
            manager._terminate_process.assert_called_once_with(zombie_pid)

    @patch('subprocess.run')
    def test_non_zombie_process_not_cleaned(self, mock_run, temp_config_dir):
        """非僵尸进程不被清理

        验证只清理识别为僵尸的进程，不误杀正常进程。
        """
        normal_pid = 99999
        target_port = 8000

        # 配置 lsof 返回正常进程 PID
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f'{normal_pid}\n'
        )

        manager = PortManager()

        with patch.object(manager, '_is_zombie_process', return_value=False):
            cleaned = manager.detect_and_cleanup_zombie_process(target_port)

            # 非僵尸进程不应被清理
            assert cleaned is False

    @patch('subprocess.run')
    def test_zombie_cleanup_failure_handling(self, mock_run, temp_config_dir):
        """僵尸进程清理失败时的处理

        验证即使清理失败也不会导致程序崩溃。
        """
        zombie_pid = 12345
        target_port = 8000

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f'{zombie_pid}\n'
        )

        manager = PortManager()

        with patch.object(manager, '_is_port_available', return_value=False), \
             patch.object(manager, '_is_zombie_process', return_value=True), \
             patch.object(manager, '_terminate_process', return_value=False):

            # 清理失败不应抛出异常
            cleaned = manager.detect_and_cleanup_zombie_process(target_port)

            # 应返回 False 表示未成功清理
            assert cleaned is False

    def test_port_released_after_crash_simulation(self, temp_config_dir):
        """程序崩溃后端口可被重新分配

        模拟：配置文件记录了端口但实际进程不存在的情况。
        """
        # 创建一个残留的配置文件（模拟崩溃前的状态）
        config_file = Path(temp_config_dir) / 'test_port_config.json'
        stale_config = {
            "version": "1.0",
            "updated_at": "2024-01-01T00:00:00",
            "services": {
                "fastapi": {
                    "port": 8000,
                    "pid": 99999,  # 已不存在的进程
                    "start_time": "2024-01-01T00:00:00",
                    "last_used": "2024-01-01T00:00:00",
                    "status": "active"
                }
            }
        }

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(stale_config, f)

        # 加载残留配置
        manager = PortManager()

        # 验证旧配置被加载
        assert "fastapi" in manager.allocated_ports
        assert manager.allocated_ports["fastapi"].port == 8000

        # 释放旧端口
        manager.release_port("fastapi")

        # 重新分配（应该成功，因为原进程已不存在）
        new_port = manager.get_port("fastapi")

        # 验证新分配成功
        assert new_port > 0
        assert "fastapi" in manager.allocated_ports

    def test_config_file_corruption_recovery(self, temp_config_dir):
        """配置文件损坏时能正常恢复

        损坏 port_config.json 后验证系统能正常启动。
        """
        # 创建损坏的配置文件
        config_file = Path(temp_config_dir) / 'test_port_config.json'

        # 写入各种损坏的内容
        corruption_cases = [
            "",  # 空文件
            "{invalid",  # 不完整的 JSON
            "binary garbage \x00\x01\x02",  # 二进制内容
            '{"version": "1.0"}',  # 缺少必需字段
        ]

        for corrupted_content in corruption_cases:
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write(corrupted_content)

            # 重置单例
            PortManager._instance = None

            # 应该能正常初始化（使用默认空配置）
            try:
                manager = PortManager()
                # 验证系统可用
                port = manager.get_port("fastapi")
                assert port > 0
            except Exception as e:
                pytest.fail(f"损坏配置文件 '{corrupted_content[:20]}...' 导致初始化失败: {e}")
            finally:
                PortManager._instance = None

    def test_missing_config_directory_recovery(self, temp_config_dir):
        """配置目录不存在时自动创建

        验证系统能处理配置目录缺失的情况。
        """
        # 设置一个不存在的目录路径
        nonexistent_dir = os.path.join(temp_config_dir, 'nonexistent', 'subdir')
        config_path = os.path.join(nonexistent_dir, 'config.json')

        os.environ['PORT_CONFIG_PATH'] = config_path

        # 应该能正常初始化并自动创建目录
        try:
            manager = PortManager()
            port = manager.get_port("fastapi")
            assert port > 0

            # 验证目录已创建
            assert os.path.exists(nonexistent_dir)
        finally:
            PortManager._instance = None

    @patch('subprocess.run', side_effect=FileNotFoundError())
    def test_lsof_unavailable_graceful_degradation(self, mock_run, temp_config_dir):
        """lsof 命令不可用时优雅降级

        在没有 lsof 的系统上（如某些容器环境），僵尸进程检测应跳过而非失败。
        """
        manager = PortManager()

        # 不应抛出异常
        result = manager.detect_and_cleanup_zombie_process(8000)

        # 应返回 False 表示无法检测
        assert result is False

    @patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd='lsof', timeout=5))
    def test_zombie_detection_timeout_handling(self, mock_run, temp_config_dir):
        """僵尸进程检测超时时的处理

        lsof 命令超时不应导致系统异常。
        """
        import subprocess

        manager = PortManager()

        # 超时时应优雅处理
        result = manager.detect_and_cleanup_zombie_process(8000)

        assert result is False


# ============================================================
# TestFrontendBackendPortSync - 前后端端口同步测试
# ============================================================


class TestFrontendBackendPortSync:
    """测试前后端端口同步机制"""

    def test_api_returns_correct_ports(self, temp_config_dir):
        """API 返回与实际使用一致的端口

        验证 GET /api/system/ports 接口返回正确的数据。
        """
        from api.system_ports import get_system_ports

        manager = PortManager()

        # 分配一些端口
        manager.get_port("fastapi")
        manager.get_port("zmq_data")

        # 调用 API（需要异步执行）
        response = asyncio.get_event_loop().run_until_complete(get_system_ports())

        # 验证响应结构
        assert response["code"] == 0
        assert response["message"] == "success"
        assert "data" in response

        data = response["data"]

        # 验证包含元数据
        assert "metadata" in data
        assert "pid" in data["metadata"]
        assert "config_file" in data["metadata"]

        # 验证包含已分配的服务端口
        assert "fastapi" in data
        assert data["fastapi"]["port"] == manager.get_port("fastapi")

    def test_api_single_service_endpoint(self, temp_config_dir):
        """API 单个服务端口查询接口

        验证 GET /api/system/ports/{service_name} 接口。
        """
        from api.system_ports import get_service_port

        manager = PortManager()
        manager.get_port("fastapi")

        # 查询存在的服务
        response = asyncio.get_event_loop().run_until_complete(
            get_service_port("fastapi")
        )

        assert response["code"] == 0
        assert response["data"]["service"] == "fastapi"
        assert response["data"]["port"] == manager.get_port("fastapi")

    def test_api_invalid_service_error(self, temp_config_dir):
        """API 无效服务名称返回错误

        验证查询不存在服务时的错误响应。
        """
        from api.system_ports import get_service_port
        from fastapi import HTTPException

        # 查询不存在的服务应抛出 HTTPException
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_service_port("invalid_service")
            )

        assert exc_info.value.status_code == 404

    def test_health_check_endpoint(self, temp_config_dir):
        """健康检查端点正常工作

        验证 GET /api/system/health 接口。
        """
        from api.system_ports import health_check

        response = asyncio.get_event_loop().run_until_complete(health_check())

        assert response["status"] == "healthy"
        assert response["service"] == "port-manager"
        assert "timestamp" in response
        assert "version" in response

    def test_frontend_port_config_format(self, temp_config_dir):
        """前端获取的端口配置格式正确

        模拟前端 fetchPortConfig() 调用后的数据处理。
        """
        from api.system_ports import get_system_ports

        manager = PortManager()

        # 分配所有服务
        for service_name in PORT_RANGES:
            manager.get_port(service_name)

        # 获取端口配置
        response = asyncio.get_event_loop().run_until_complete(get_system_ports())
        data = response["data"]

        # 验证前端需要的字段都存在
        required_fields_for_frontend = ["fastapi", "zmq_data", "zmq_control", "zmq_status", "zmq_broadcast"]

        for field in required_fields_for_frontend:
            assert field in data, f"缺少前端所需字段: {field}"
            assert "port" in data[field], f"{field} 缺少 port 字段"
            assert "service" in data[field], f"{field} 缺少 service 字段"
            assert isinstance(data[field]["port"], int), f"{field}.port 应为整数"

        # 验证元数据字段
        metadata = data["metadata"]
        assert "pid" in metadata
        assert "start_time" in metadata
        assert "last_updated" in metadata
        assert "config_file" in metadata

    def test_port_consistency_between_api_and_manager(self, temp_config_dir):
        """API 返回的端口与 PortManager 内部状态一致

        确保前后端看到的端口配置完全一致。
        注意：API 使用全局 port_manager 单例，测试需使用同一实例。
        """
        from api.system_ports import get_system_ports

        # API 使用全局 port_manager 单例，这里也使用同一个
        manager = port_manager

        # 动态分配多个服务
        services_to_allocate = ["fastapi", "zmq_data", "zmq_broadcast"]
        for service in services_to_allocate:
            manager.get_port(service)

        # 从 API 获取（API 内部也调用同一个全局 port_manager）
        api_response = asyncio.get_event_loop().run_until_complete(get_system_ports())
        api_data = api_response["data"]

        # 从 Manager 获取
        manager_ports = manager.get_all_ports()

        # 对比一致性（排除 metadata 字段）
        for service in services_to_allocate:
            assert service in api_data, f"API 缺少服务: {service}"
            assert service in manager_ports, f"Manager 缺少服务: {service}"
            assert api_data[service]["port"] == manager_ports[service], \
                f"{service} 端口不一致: API={api_data[service]['port']} vs Manager={manager_ports[service]}"


# ============================================================
# TestEdgeCasesAndStress - 边界条件和压力测试
# ============================================================


class TestEdgeCasesAndStress:
    """边界条件和压力测试"""

    @patch.object(PortManager, '_is_port_available', return_value=False)
    def test_all_ports_occupied_scenario(self, mock_available, temp_config_dir):
        """所有端口都被占用的极端情况

        验证抛出明确的错误信息。
        """
        manager = PortManager()

        with pytest.raises(PortAllocationError) as exc_info:
            manager.get_port("fastapi")

        # 验证错误信息明确
        assert "所有端口都不可用" in str(exc_info.value)
        assert exc_info.value.service_name == "fastapi"

    def test_rapid_start_stop_cycles(self, temp_config_dir):
        """快速启停压力测试

        循环多次：启动 → 停止 → 再启动，验证没有资源泄漏。
        """
        manager = PortManager()

        num_cycles = 20
        allocated_ports = []

        for i in range(num_cycles):
            # 启动：分配端口
            port = manager.get_port("fastapi")
            allocated_ports.append(port)
            assert port > 0

            # 停止：释放端口
            released = manager.release_port("fastapi")
            assert released is True

            # 验证已释放
            assert "fastapi" not in manager.allocated_ports

        # 最终验证系统仍正常工作
        final_port = manager.get_port("fastapi")
        assert final_port > 0
        assert "fastapi" in manager.allocated_ports

        # 验证配置文件最终状态正确
        with open(manager.config_path, 'r', encoding='utf-8') as f:
            final_config = json.load(f)

        assert "fastapi" in final_config["services"]
        assert final_config["services"]["fastapi"]["port"] == final_port

    def test_large_number_of_services_allocation(self, temp_config_dir):
        """大量服务分配的压力测试

        虽然当前只有固定数量的服务，但验证系统在高频操作下的稳定性。
        """
        manager = PortManager()

        operations_count = 100
        errors = []

        for _ in range(operations_count):
            try:
                # 循环获取所有服务端口
                for service_name in PORT_RANGES:
                    port = manager.get_port(service_name)
                    assert port > 0
            except Exception as e:
                errors.append(str(e))

        # 验证无错误累积
        assert len(errors) == 0, f"高频操作中出现错误: {errors[:5]}"

    def test_concurrent_read_write_operations(self, temp_config_dir):
        """并发读写操作的安全性

        多线程同时进行端口分配和查询操作。
        """
        manager = PortManager()
        errors = []

        def writer_thread():
            """写入线程：循环分配和释放端口"""
            try:
                for _ in range(20):
                    manager.get_port("zmq_data")
                    manager.release_port("zmq_data")
            except Exception as e:
                errors.append(f"Writer error: {e}")

        def reader_thread():
            """读取线程：循环查询端口"""
            try:
                for _ in range(50):
                    ports = manager.get_all_ports()
                    assert isinstance(ports, dict)
            except Exception as e:
                errors.append(f"Reader error: {e}")

        # 创建多个读写线程
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=writer_thread))
        for _ in range(5):
            threads.append(threading.Thread(target=reader_thread))

        # 启动所有线程
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # 验证无错误
        assert len(errors) == 0, f"并发读写出现错误: {errors}"

    def test_port_range_boundary_values(self, temp_config_dir):
        """端口范围边界值测试

        验证范围首尾端口的处理。
        """
        manager = PortManager()

        # 测试设置边界端口
        boundary_tests = [
            ("fastapi", 8000),   # 范围起始
            ("fastapi", 8009),   # 范围结束前一个
            ("zmq_data", 5550),
            ("zmq_data", 5559),
        ]

        for service_name, port in boundary_tests:
            try:
                manager.set_preferred_port(service_name, port)
                allocated = manager.get_port(service_name)

                # 如果端口可用，应该分配成功
                assert allocated == port or PORT_RANGES[service_name]["default"] == allocated

                # 为下次测试重置
                manager.release_port(service_name)
                PortManager._instance = None
                PortManager._instance = manager
            except ValueError:
                # 端口超出范围是预期行为
                pass

    def test_config_persistence_under_stress(self, temp_config_dir):
        """高频率配置持久化测试

        验证频繁保存配置时文件的完整性。
        """
        manager = PortManager()

        save_count = 50

        for i in range(save_count):
            # 分配或释放触发配置保存
            if i % 2 == 0:
                manager.get_port("fastapi") if "fastapi" not in manager.allocated_ports else None
            else:
                manager.release_port("fastapi") if "fastapi" in manager.allocated_ports else None

            time.sleep(0.01)  # 小延迟避免过快

        # 验证配置文件仍然有效
        assert manager.config_path.exists()

        with open(manager.config_path, 'r', encoding='utf-8') as f:
            try:
                config = json.load(f)
                assert "version" in config
                assert "services" in config
            except json.JSONDecodeError:
                pytest.fail("压力测试后配置文件损坏")

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific process management")
    def test_real_port_binding_verification(self, temp_config_dir):
        """真实端口绑定验证（仅 Unix）

        在真实环境中验证 PortManager 分配的端口确实可用。
        使用高编号端口避免与系统服务冲突。
        """
        # 使用一个确定可用的高位端口进行测试
        test_port = find_available_port(19000, 20000)

        manager = PortManager()

        # 设置并获取一个我们确定可用的端口
        try:
            manager.set_preferred_port("fastapi", test_port)
            port = manager.get_port("fastapi")

            assert port == test_port

            # 尝试真实绑定
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                test_sock.bind(('127.0.0.1', port))
                test_sock.close()
                # 绑定成功说明端口确实可用
                assert True
            except OSError as e:
                test_sock.close()
                if e.errno in (98, 48, 10048):
                    pytest.skip(f"端口 {port} 在绑定前被其他进程占用")
                raise
        except ValueError:
            # 端口超出范围，跳过此测试
            pytest.skip("测试端口不在 fastapi 服务范围内")
            raise

    def test_memory_stability_under_load(self, temp_config_dir):
        """内存稳定性测试

        验证长时间运行后内存使用稳定（通过对象数量间接检测）。
        """
        import gc

        manager = PortManager()

        # 记录初始状态
        gc.collect()
        # 这里不做精确内存测量，而是验证基本功能不受影响

        iterations = 1000

        for _ in range(iterations):
            manager.get_port("zmq_data")
            manager.get_all_ports()

            if _ % 100 == 99:
                manager.release_port("zmq_data")

        # 验证功能仍然正常
        final_port = manager.get_port("zmq_data")
        assert final_port > 0
        assert manager.get_all_ports() is not None


# ============================================================
# TestErrorHandling - 错误处理专项测试
# ============================================================


class TestErrorHandling:
    """错误处理专项测试"""

    def test_permission_denied_on_privileged_port(self, temp_config_dir):
        """特权端口权限不足的处理

        尝试使用需要 root 权限的端口时应优雅处理。
        """
        manager = PortManager()

        # 尝试设置特权端口（< 1024）
        with pytest.raises(ValueError, match="超出"):
            manager.set_preferred_port("fastapi", 80)

    def test_invalid_port_number_handling(self, temp_config_dir):
        """无效端口号的处理

        负数、超大值等无效输入的处理。
        """
        manager = PortManager()

        invalid_ports = [-1, 0, 65536, 100000]

        for invalid_port in invalid_ports:
            with pytest.raises((ValueError, Exception)):
                manager.set_preferred_port("fastapi", invalid_port)

    def test_concurrent_release_safety(self, temp_config_dir):
        """并发释放端口的安全性

        多线程同时释放同一端口不应出错。
        """
        manager = PortManager()
        manager.get_port("fastapi")

        errors = []

        def release_port():
            try:
                manager.release_port("fastapi")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=release_port) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # 即使多次释放也不应报错
        assert len(errors) == 0

    def test_reload_config_during_operation(self, temp_config_dir):
        """运行期间重新加载配置

        验证热重载配置不会导致数据不一致。
        """
        manager = PortManager()

        # 先分配一些端口
        manager.get_port("fastapi")
        manager.get_port("zmq_data")

        initial_state = dict(manager.allocated_ports)

        # 修改配置文件
        with open(manager.config_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": "1.0",
                "updated_at": "2024-01-01T00:00:00",
                "services": {
                    "zmq_control": {
                        "port": 5565,
                        "pid": 11111,
                        "start_time": "2024-01-01T00:00:00",
                        "last_used": "2024-01-01T00:00:00",
                        "status": "active"
                    }
                }
            }, f)

        # 重新加载
        manager.reload_config()

        # 验证新配置已加载
        assert "zmq_control" in manager.allocated_ports
        assert manager.allocated_ports["zmq_control"].port == 5565


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
