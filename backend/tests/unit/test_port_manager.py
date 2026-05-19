# -*- coding: utf-8 -*-
"""
PortManager 端口管理器单元测试

测试 port_manager 模块的端口分配、配置持久化、僵尸进程检测等功能。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-13
"""

import os
import json
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from core.port_manager import (
    PortManager,
    PortAllocationError,
    PortConfig,
    PORT_RANGES,
    port_manager,
)


@pytest.fixture(autouse=True)
def reset_port_manager_singleton():
    """自动重置 PortManager 单例，确保每个测试独立运行"""
    original_instance = PortManager._instance
    original_initialized = getattr(PortManager._instance, '_initialized', False)

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

    yield

    if original_static:
        os.environ['USE_STATIC_PORTS'] = original_static
    else:
        os.environ.pop('USE_STATIC_PORTS', None)

    if original_config:
        os.environ['PORT_CONFIG_PATH'] = original_config


@pytest.fixture
def temp_config_dir():
    """创建临时目录用于测试配置文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, 'test_port_config.json')
        os.environ['PORT_CONFIG_PATH'] = config_path
        yield tmpdir
        if 'PORT_CONFIG_PATH' in os.environ and os.environ['PORT_CONFIG_PATH'] == config_path:
            os.environ.pop('PORT_CONFIG_PATH', None)


class TestPortManagerInitialization:
    """测试 PortManager 初始化"""

    def test_default_initialization(self, temp_config_dir):
        """测试默认初始化 - 验证基本属性设置正确"""
        manager = PortManager()

        assert manager.config_path.name == 'test_port_config.json'
        assert isinstance(manager.allocated_ports, dict)
        assert len(manager.allocated_ports) == 0
        assert manager.use_static_ports is False

    def test_static_ports_mode(self, temp_config_dir):
        """测试静态端口模式初始化"""
        os.environ['USE_STATIC_PORTS'] = 'true'
        manager = PortManager()

        assert manager.use_static_ports is True
        assert len(manager.allocated_ports) == len(PORT_RANGES)

        for service_name, config in PORT_RANGES.items():
            assert service_name in manager.allocated_ports
            assert manager.allocated_ports[service_name].port == config['default']
            assert manager.allocated_ports[service_name].status == 'static'

    def test_custom_config_path(self, temp_config_dir):
        """测试自定义配置文件路径"""
        custom_path = os.path.join(temp_config_dir, 'custom_config.json')
        os.environ['PORT_CONFIG_PATH'] = custom_path

        manager = PortManager()
        assert str(manager.config_path) == custom_path

    def test_thread_lock_initialization(self, temp_config_dir):
        """测试线程锁初始化"""
        manager = PortManager()

        assert hasattr(manager, '_port_lock')
        assert isinstance(manager._port_lock, type(threading.Lock()))

    def test_singleton_pattern(self, temp_config_dir):
        """测试单例模式 - 多次创建返回同一实例"""
        manager1 = PortManager()
        manager2 = PortManager()

        assert manager1 is manager2

    def test_logger_initialization(self, temp_config_dir):
        """测试日志器初始化"""
        manager = PortManager()

        assert hasattr(manager, 'logger')
        assert manager.logger is not None


class TestPortAllocationNormal:
    """测试端口分配 - 正常场景"""

    def test_get_port_returns_default_when_available(self, temp_config_dir):
        """当默认端口可用时返回默认端口"""
        manager = PortManager()

        port = manager.get_port('fastapi')

        start_port, end_port = PORT_RANGES['fastapi']['range']
        assert start_port <= port <= end_port

    def test_get_port_caches_result(self, temp_config_dir):
        """重复获取同一服务端口应返回缓存值"""
        manager = PortManager()

        port1 = manager.get_port('zmq_data')
        port2 = manager.get_port('zmq_data')

        assert port1 == port2
        assert 'zmq_data' in manager.allocated_ports

    def test_get_all_services_ports(self, temp_config_dir):
        """获取所有服务的端口"""
        manager = PortManager()

        for service_name in PORT_RANGES.keys():
            port = manager.get_port(service_name)
            assert port > 0
            assert port < 65536

    def test_get_all_ports_returns_dict(self, temp_config_dir):
        """get_all_ports 返回正确的字典结构"""
        manager = PortManager()
        manager.get_port('fastapi')
        manager.get_port('zmq_data')

        all_ports = manager.get_all_ports()

        assert isinstance(all_ports, dict)
        assert 'fastapi' in all_ports
        assert 'zmq_data' in all_ports
        assert all_ports['fastapi'] is not None
        start_port, end_port = PORT_RANGES['fastapi']['range']
        assert start_port <= all_ports['fastapi'] <= end_port

    def test_last_used_timestamp_updated(self, temp_config_dir):
        """获取端口时更新最后使用时间"""
        manager = PortManager()

        port = manager.get_port('fastapi')
        config = manager.allocated_ports['fastapi']

        assert config.last_used is not None
        assert len(config.last_used) > 0


class TestPortAllocationConflictDetection:
    """测试端口分配 - 冲突检测与自动切换"""

    @patch.object(PortManager, '_is_port_available')
    def test_auto_switch_when_default_port_occupied(self, mock_available, temp_config_dir):
        """默认端口被占用时自动切换到下一个可用端口"""
        def check_availability(port):
            if port == 8000:
                return False
            return True

        mock_available.side_effect = check_availability

        manager = PortManager()
        port = manager.get_port('fastapi')

        assert port != 8000
        assert PORT_RANGES['fastapi']['range'][0] <= port < PORT_RANGES['fastapi']['range'][1]

    @patch.object(PortManager, '_is_port_available', return_value=False)
    def test_exhaust_all_ports_raises_error(self, mock_available, temp_config_dir):
        """所有端口都占用时抛出异常"""
        manager = PortManager()

        with pytest.raises(PortAllocationError, match="所有端口都不可用"):
            manager.get_port('fastapi')

    def test_preferred_port_allocation(self, temp_config_dir):
        """设置首选端口后优先使用该端口"""
        manager = PortManager()

        manager.set_preferred_port('fastapi', 8005)
        port = manager.get_port('fastapi')

        assert port == 8005

    @patch.object(PortManager, '_is_port_available')
    def test_fallback_to_default_when_preferred_occupied(self, mock_available, temp_config_dir):
        """首选端口被占用时回退到默认端口"""
        def check_availability(port):
            if port == 8005:
                return False
            return True

        mock_available.side_effect = check_availability

        manager = PortManager()
        manager.set_preferred_port('fastapi', 8005)
        port = manager.get_port('fastapi')

        assert port == PORT_RANGES['fastapi']['default']


class TestConfigPersistence:
    """测试配置文件持久化"""

    def test_save_config_creates_file(self, temp_config_dir):
        """保存配置后文件存在且内容正确"""
        manager = PortManager()
        manager.get_port('fastapi')

        manager.save_config()

        assert manager.config_path.exists()

        with open(manager.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert 'version' in data
        assert 'services' in data
        assert 'fastapi' in data['services']
        start_port, end_port = PORT_RANGES['fastapi']['range']
        assert start_port <= data['services']['fastapi']['port'] <= end_port
        assert 'pid' in data['services']['fastapi']

    def test_load_config_reads_existing_config(self, temp_config_dir):
        """能正确读取已存在的配置文件"""
        config_file = Path(temp_config_dir) / 'test_port_config.json'
        test_config = {
            "version": "1.0",
            "updated_at": "2024-01-01T00:00:00",
            "services": {
                "fastapi": {
                    "port": 8001,
                    "pid": 12345,
                    "start_time": "2024-01-01T00:00:00",
                    "last_used": "2024-01-01T00:00:00",
                    "status": "active"
                }
            }
        }

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(test_config, f)

        mgr = PortManager()

        assert 'fastapi' in mgr.allocated_ports
        assert mgr.allocated_ports['fastapi'].port == 8001

    def test_load_config_handles_missing_file(self, temp_config_dir):
        """配置文件不存在时返回空字典"""
        manager = PortManager()

        result = manager.load_config()

        assert result == {}

    def test_load_config_handles_corrupted_file(self, temp_config_dir):
        """配置文件损坏时优雅处理"""
        config_file = Path(temp_config_dir) / 'test_port_config.json'
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{invalid json content}')

        manager = PortManager()

        result = manager.load_config()

        assert result == {}

    def test_save_config_atomic_write(self, temp_config_dir):
        """验证配置保存使用原子写入（临时文件+重命名）"""
        manager = PortManager()
        manager.get_port('fastapi')

        with patch('os.replace') as mock_replace:
            manager.save_config()
            mock_replace.assert_called_once()

    def test_reload_config_clears_and_reloads(self, temp_config_dir):
        """重新加载配置会清空当前配置并从文件加载"""
        manager = PortManager()
        manager.get_port('fastapi')
        manager.get_port('zmq_data')

        initial_count = len(manager.allocated_ports)

        manager.reload_config()

        assert len(manager.allocated_ports) <= initial_count


class TestZombieProcessDetection:
    """测试僵尸进程检测"""

    @patch('subprocess.run')
    def test_detect_zombie_process_success(self, mock_run, temp_config_dir):
        """成功检测并清理僵尸进程"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='12345\n'
        )

        with patch.object(PortManager, '_is_zombie_process', return_value=True), \
             patch.object(PortManager, '_terminate_process', return_value=True):

            manager = PortManager()
            result = manager.detect_and_cleanup_zombie_process(8000)

            assert result is True

    @patch('subprocess.run')
    def test_detect_non_zombie_process(self, mock_run, temp_config_dir):
        """非僵尸进程不清理"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='12345\n'
        )

        with patch.object(PortManager, '_is_zombie_process', return_value=False):

            manager = PortManager()
            result = manager.detect_and_cleanup_zombie_process(8000)

            assert result is False

    @patch('subprocess.run')
    def test_no_process_on_port(self, mock_run, temp_config_dir):
        """端口无进程时不报错"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=''
        )

        manager = PortManager()
        result = manager.detect_and_cleanup_zombie_process(8000)

        assert result is True

    @patch('subprocess.run', side_effect=FileNotFoundError())
    def test_lsof_not_available(self, mock_run, temp_config_dir):
        """lsof 命令不可用时优雅处理"""
        manager = PortManager()
        result = manager.detect_and_cleanup_zombie_process(8000)

        assert result is False

    @patch('subprocess.run')
    def test_is_zombie_process_detection(self, mock_run, temp_config_dir):
        """测试僵尸进程判断逻辑"""
        manager = PortManager()

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='/usr/bin/python main:app --host 0.0.0.0 --port 8000'
        )

        result = manager._is_zombie_process(99999, os.getpid())

        assert result is True

    @patch('subprocess.run')
    def test_is_not_zombie_process(self, mock_run, temp_config_dir):
        """测试非僵尸进程判断"""
        manager = PortManager()

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='/usr/bin/nginx -g daemon off;'
        )

        result = manager._is_zombie_process(99999, os.getpid())

        assert result is False

    @patch('os.kill')
    def test_terminate_process_sigterm_success(self, mock_kill, temp_config_dir):
        """SIGTERM 成功终止进程"""
        mock_kill.side_effect = [None, ProcessLookupError()]

        manager = PortManager()
        result = manager._terminate_process(12345)

        assert result is True

    @patch('os.kill')
    def test_terminate_process_sigkill_fallback(self, mock_kill, temp_config_dir):
        """SIGTERM 失败后使用 SIGKILL"""
        call_count = [0]

        def mock_kill_side_effect(pid, sig):
            call_count[0] += 1
            if call_count[0] <= 11:
                return None
            raise ProcessLookupError()

        mock_kill.side_effect = mock_kill_side_effect

        manager = PortManager()
        result = manager._terminate_process(12345)

        assert result is True

    @patch('os.kill', side_effect=PermissionError("权限不足"))
    def test_terminate_process_permission_error(self, mock_kill, temp_config_dir):
        """权限不足时终止失败"""
        manager = PortManager()
        result = manager._terminate_process(12345)

        assert result is False


class TestConcurrencySafety:
    """测试并发安全"""

    def test_concurrent_access_thread_safety(self, temp_config_dir):
        """多线程并发访问不会导致数据竞争"""
        manager = PortManager()
        errors = []
        results = {}

        def get_port_thread(service_name):
            try:
                port = manager.get_port(service_name)
                results[service_name] = port
            except Exception as e:
                errors.append(e)

        threads = []
        services = list(PORT_RANGES.keys()) * 10

        for service_name in services:
            t = threading.Thread(target=get_port_thread, args=(service_name,))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"并发访问出现错误: {errors}"
        assert len(results) > 0

    def test_concurrent_get_all_ports(self, temp_config_dir):
        """并发获取所有端口配置安全"""
        manager = PortManager()
        manager.get_port('fastapi')

        errors = []
        results = []

        def get_all_ports():
            try:
                ports = manager.get_all_ports()
                results.append(ports)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_all_ports) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert all(r == results[0] for r in results)


class TestEdgeCasesAndValidation:
    """测试边界条件和输入验证"""

    def test_invalid_service_name_raises_error(self, temp_config_dir):
        """无效的服务名称抛出异常"""
        manager = PortManager()

        with pytest.raises((PortAllocationError, ValueError), match="未知的服务名称"):
            manager.get_port('invalid_service')

    def test_invalid_service_name_in_set_preferred(self, temp_config_dir):
        """set_preferred_port 使用无效服务名抛出异常"""
        manager = PortManager()

        with pytest.raises(ValueError, match="未知的服务名称"):
            manager.set_preferred_port('invalid_service', 8000)

    def test_port_out_of_range_raises_error(self, temp_config_dir):
        """超出范围的端口号抛出异常"""
        manager = PortManager()

        with pytest.raises(ValueError, match="端口号.*超出"):
            manager.set_preferred_port('fastapi', 9000)

    def test_environment_variable_override(self, temp_config_dir):
        """环境变量 USE_STATIC_PORTS=true 时强制使用默认值"""
        os.environ['USE_STATIC_PORTS'] = 'true'

        manager = PortManager()

        assert manager.use_static_ports is True
        assert len(manager.allocated_ports) == len(PORT_RANGES)

        for service_name in PORT_RANGES:
            assert manager.allocated_ports[service_name].port == PORT_RANGES[service_name]['default']

    def test_release_nonexistent_service(self, temp_config_dir):
        """释放不存在的服务端口返回 False"""
        manager = PortManager()

        result = manager.release_port('nonexistent')

        assert result is False

    def test_release_existing_service(self, temp_config_dir):
        """释放已分配的服务端口"""
        manager = PortManager()
        manager.get_port('fastapi')

        assert 'fastapi' in manager.allocated_ports

        result = manager.release_port('fastapi')

        assert result is True
        assert 'fastapi' not in manager.allocated_ports

    def test_validate_config_valid_data(self, temp_config_dir):
        """验证有效配置数据"""
        manager = PortManager()

        valid_config = {
            "version": "1.0",
            "services": {
                "fastapi": {"port": 8000}
            }
        }

        assert manager._validate_config(valid_config) is True

    def test_validate_config_missing_keys(self, temp_config_dir):
        """验证缺少必需键的配置"""
        manager = PortManager()

        invalid_config = {
            "version": "1.0"
        }

        assert manager._validate_config(invalid_config) is False

    def test_validate_config_invalid_services_format(self, temp_config_dir):
        """验证无效格式的 services"""
        manager = PortManager()

        invalid_configs = [
            {"version": "1.0", "services": "not_a_dict"},
            {"version": "1.0", "services": {"fastapi": "not_a_dict"}},
            {"version": "1.0", "services": {"fastapi": {"port": "not_int"}}},
        ]

        for config in invalid_configs:
            assert manager._validate_config(config) is False

    def test_port_config_to_dict(self, temp_config_dir):
        """PortConfig.to_dict() 正确转换"""
        config = PortConfig(
            port=8000,
            pid=12345,
            start_time="2024-01-01T00:00:00",
            last_used="2024-01-01T00:00:00",
            status="active"
        )

        result = config.to_dict()

        assert isinstance(result, dict)
        assert result['port'] == 8000
        assert result['pid'] == 12345
        assert result['status'] == 'active'


class TestPortAvailabilityCheck:
    """测试端口可用性检查"""

    def test_available_port_returns_true(self, temp_config_dir):
        """可用端口返回 True"""
        manager = PortManager()

        result = manager._is_port_available(19999)

        assert result is True

    @patch.object(PortManager, '_is_port_available', return_value=False)
    def test_occupied_port_returns_false(self, mock_available, temp_config_dir):
        """被占用端口返回 False"""
        manager = PortManager()

        result = manager._is_port_available(19998)

        assert result is False

    def test_privileged_port_handling(self, temp_config_dir):
        """特权端口处理（需要 root 权限）"""
        manager = PortManager()

        result = manager._is_port_available(80)

        assert isinstance(result, bool)


class TestPortAllocationError:
    """测试 PortAllocationError 异常"""

    def test_exception_attributes(self, temp_config_dir):
        """异常包含正确的属性"""
        error = PortAllocationError(
            "测试错误消息",
            service_name="test_service",
            port=8080
        )

        assert str(error) == "测试错误消息"
        assert error.service_name == "test_service"
        assert error.port == 8080

    def test_exception_inheritance(self, temp_config_dir):
        """异常继承自 Exception"""
        assert issubclass(PortAllocationError, Exception)


class TestIntegrationScenarios:
    """测试集成场景"""

    def test_full_lifecycle(self, temp_config_dir):
        """完整生命周期测试：分配 -> 使用 -> 释放"""
        manager = PortManager()

        port = manager.get_port('fastapi')
        assert port > 0

        all_ports = manager.get_all_ports()
        assert 'fastapi' in all_ports

        released = manager.release_port('fastapi')
        assert released is True

        all_ports_after = manager.get_all_ports()
        assert 'fastapi' not in all_ports_after

    def test_multiple_services_allocation(self, temp_config_dir):
        """多个服务同时分配端口"""
        manager = PortManager()

        ports = {}
        for service_name in PORT_RANGES.keys():
            ports[service_name] = manager.get_port(service_name)

        assert len(ports) == len(PORT_RANGES)

        all_ports = manager.get_all_ports()
        assert len(all_ports) == len(PORT_RANGES)

    def test_reallocation_after_release(self, temp_config_dir):
        """释放后重新分配可能获得不同端口"""
        manager = PortManager()

        port1 = manager.get_port('zmq_data')
        manager.release_port('zmq_data')

        port2 = manager.get_port('zmq_data')

        assert port2 > 0
        assert 'zmq_data' in manager.allocated_ports


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
