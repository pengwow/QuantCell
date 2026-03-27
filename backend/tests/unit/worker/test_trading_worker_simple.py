# -*- coding: utf-8 -*-
"""
Trading Worker 简化单元测试

测试 Trading Worker 相关组件的单元功能，不依赖 zmq 和 binance 模块
"""

import pytest
import sys
import os
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))


# =============================================================================
# 配置构建测试
# =============================================================================

class TestTradingConfig:
    """TradingNode 配置构建测试"""

    def test_build_binance_config_testnet(self):
        """测试 Binance 测试网配置构建"""
        # 直接导入 config 模块，避免完整的 worker 包导入
        import importlib.util
        config_path = os.path.join(os.path.dirname(__file__), '../../../worker/config.py')
        spec = importlib.util.spec_from_file_location("worker_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        
        # Mock Nautilus 导入
        sys.modules['nautilus_trader'] = Mock()
        sys.modules['nautilus_trader.config'] = Mock()
        sys.modules['nautilus_trader.live'] = Mock()
        sys.modules['nautilus_trader.live.config'] = Mock()
        sys.modules['nautilus_trader.common'] = Mock()
        sys.modules['nautilus_trader.model'] = Mock()
        sys.modules['nautilus_trader.model.identifiers'] = Mock()
        
        spec.loader.exec_module(config_module)
        
        result = config_module.build_binance_config(
            api_key="test_api_key",
            api_secret="test_api_secret",
            testnet=True,
            use_usdt_margin=True,
        )

        assert result["api_key"] == "test_api_key"
        assert result["api_secret"] == "test_api_secret"
        assert result["testnet"] is True
        assert result["use_usdt_margin"] is True
        assert "base_url_http" in result
        assert "base_url_ws" in result

    def test_build_binance_config_live(self):
        """测试 Binance 生产环境配置构建"""
        import importlib.util
        config_path = os.path.join(os.path.dirname(__file__), '../../../worker/config.py')
        spec = importlib.util.spec_from_file_location("worker_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        
        # Mock Nautilus 导入
        sys.modules['nautilus_trader'] = Mock()
        sys.modules['nautilus_trader.config'] = Mock()
        sys.modules['nautilus_trader.live'] = Mock()
        sys.modules['nautilus_trader.live.config'] = Mock()
        sys.modules['nautilus_trader.common'] = Mock()
        sys.modules['nautilus_trader.model'] = Mock()
        sys.modules['nautilus_trader.model.identifiers'] = Mock()
        
        spec.loader.exec_module(config_module)
        
        result = config_module.build_binance_config(
            api_key="live_api_key",
            api_secret="live_api_secret",
            testnet=False,
            use_usdt_margin=True,
        )

        assert result["testnet"] is False

    def test_build_binance_live_config(self):
        """测试 Binance 生产环境便捷配置"""
        import importlib.util
        config_path = os.path.join(os.path.dirname(__file__), '../../../worker/config.py')
        spec = importlib.util.spec_from_file_location("worker_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        
        # Mock Nautilus 导入
        sys.modules['nautilus_trader'] = Mock()
        sys.modules['nautilus_trader.config'] = Mock()
        sys.modules['nautilus_trader.live'] = Mock()
        sys.modules['nautilus_trader.live.config'] = Mock()
        sys.modules['nautilus_trader.common'] = Mock()
        sys.modules['nautilus_trader.model'] = Mock()
        sys.modules['nautilus_trader.model.identifiers'] = Mock()
        
        spec.loader.exec_module(config_module)
        
        result = config_module.build_binance_live_config(
            api_key="live_api_key",
            api_secret="live_api_secret",
            use_usdt_margin=True,
        )

        assert result["testnet"] is False
        assert "fapi.binance.com" in result["base_url_http"]
        assert "fstream.binance.com" in result["base_url_ws"]


# =============================================================================
# Worker 状态测试
# =============================================================================

class TestWorkerState:
    """Worker 状态测试"""

    def test_worker_state_transitions(self):
        """测试 Worker 状态转换"""
        import importlib.util
        state_path = os.path.join(os.path.dirname(__file__), '../../../worker/state.py')
        spec = importlib.util.spec_from_file_location("worker_state", state_path)
        state_module = importlib.util.module_from_spec(spec)
        
        # Mock 依赖
        sys.modules['sqlalchemy'] = Mock()
        sys.modules['sqlalchemy.orm'] = Mock()
        sys.modules['collector'] = Mock()
        sys.modules['collector.db'] = Mock()
        sys.modules['collector.db.database'] = Mock()
        
        spec.loader.exec_module(state_module)
        
        WorkerState = state_module.WorkerState
        WorkerStatus = state_module.WorkerStatus
        
        status = WorkerStatus(worker_id="test-worker")

        # 初始状态是 INITIALIZING
        assert status.state == WorkerState.INITIALIZING

        # 初始化完成
        status.update_state(WorkerState.INITIALIZED)
        assert status.state == WorkerState.INITIALIZED

        # 启动
        status.update_state(WorkerState.STARTING)
        assert status.state == WorkerState.STARTING

        status.update_state(WorkerState.RUNNING)
        assert status.state == WorkerState.RUNNING

        # 暂停
        status.update_state(WorkerState.PAUSED)
        assert status.state == WorkerState.PAUSED

        # 恢复
        status.update_state(WorkerState.RUNNING)
        assert status.state == WorkerState.RUNNING

        # 停止
        status.update_state(WorkerState.STOPPING)
        assert status.state == WorkerState.STOPPING

    def test_worker_error_handling(self):
        """测试 Worker 错误处理"""
        import importlib.util
        state_path = os.path.join(os.path.dirname(__file__), '../../../worker/state.py')
        spec = importlib.util.spec_from_file_location("worker_state", state_path)
        state_module = importlib.util.module_from_spec(spec)
        
        # Mock 依赖
        sys.modules['sqlalchemy'] = Mock()
        sys.modules['sqlalchemy.orm'] = Mock()
        sys.modules['collector'] = Mock()
        sys.modules['collector.db'] = Mock()
        sys.modules['collector.db.database'] = Mock()
        
        spec.loader.exec_module(state_module)
        
        WorkerStatus = state_module.WorkerStatus
        
        status = WorkerStatus(worker_id="test-worker")

        # 记录错误
        status.record_error("Test error")
        assert status.errors_count == 1
        assert status.last_error == "Test error"
        assert status.last_error_time is not None

        # 记录多个错误
        status.record_error("Another error")
        assert status.errors_count == 2
        assert status.last_error == "Another error"

    def test_worker_heartbeat(self):
        """测试 Worker 心跳"""
        import importlib.util
        state_path = os.path.join(os.path.dirname(__file__), '../../../worker/state.py')
        spec = importlib.util.spec_from_file_location("worker_state", state_path)
        state_module = importlib.util.module_from_spec(spec)
        
        # Mock 依赖
        sys.modules['sqlalchemy'] = Mock()
        sys.modules['sqlalchemy.orm'] = Mock()
        sys.modules['collector'] = Mock()
        sys.modules['collector.db'] = Mock()
        sys.modules['collector.db.database'] = Mock()
        
        spec.loader.exec_module(state_module)
        
        WorkerStatus = state_module.WorkerStatus
        WorkerState = state_module.WorkerState
        
        status = WorkerStatus(worker_id="test-worker")

        # 先转换到 RUNNING 状态（is_healthy 要求 RUNNING 或 PAUSED 状态）
        status.update_state(WorkerState.INITIALIZED)
        status.update_state(WorkerState.STARTING)
        status.update_state(WorkerState.RUNNING)

        # 更新心跳
        status.update_heartbeat()
        assert status.last_heartbeat is not None

        # 检查健康状态
        assert status.is_healthy() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
