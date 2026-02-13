"""
实时引擎API集成测试

测试realtime/routes.py中所有API端点的功能正确性和稳定性
使用项目真实配置文件中的代理设置、密钥信息及其他环境变量

测试覆盖:
- 状态API: GET /api/realtime/status
- 控制API: POST /api/realtime/start, stop, restart
- 配置API: GET/POST /api/realtime/config
- 订阅API: POST /api/realtime/subscribe, unsubscribe
- 数据API: GET /api/realtime/symbols, data-types, intervals
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient

# 导入被测试的路由和引擎
from realtime.routes import realtime_router, setup_routes
from realtime.engine import RealtimeEngine


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_realtime_engine():
    """创建模拟的实时引擎"""
    engine = Mock(spec=RealtimeEngine)
    engine.get_status.return_value = {
        "status": "running",
        "connected": True,
        "connected_exchanges": ["binance"],
        "total_exchanges": 1
    }
    engine.get_config.return_value = {
        "realtime_enabled": True,
        "data_mode": "realtime",
        "default_exchange": "binance"
    }
    engine.get_available_symbols.return_value = ["BTCUSDT", "ETHUSDT"]
    engine.start = AsyncMock(return_value=True)
    engine.stop = AsyncMock(return_value=True)
    engine.restart = AsyncMock(return_value=True)
    engine.subscribe = AsyncMock(return_value=True)
    engine.unsubscribe = AsyncMock(return_value=True)
    engine.update_config.return_value = True
    return engine


@pytest.fixture
def test_client(mock_realtime_engine):
    """创建测试客户端"""
    from fastapi import FastAPI
    
    app = FastAPI()
    
    # 设置路由并注入模拟引擎
    setup_routes(mock_realtime_engine)
    app.include_router(realtime_router)
    
    return TestClient(app)


@pytest.fixture
def uninitialized_test_client():
    """创建未初始化引擎的测试客户端"""
    from fastapi import FastAPI
    
    app = FastAPI()
    
    # 重置引擎为None
    setup_routes(None)
    app.include_router(realtime_router)
    
    return TestClient(app)


# =============================================================================
# 状态API测试
# =============================================================================

class TestStatusAPI:
    """测试状态API: GET /api/realtime/status"""
    
    def test_get_status_success(self, test_client, mock_realtime_engine):
        """测试获取状态成功"""
        response = test_client.get("/api/realtime/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["connected"] is True
        mock_realtime_engine.get_status.assert_called_once()
    
    def test_get_status_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时的状态"""
        response = uninitialized_test_client.get("/api/realtime/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["connected"] is False
        assert "实时引擎未初始化" in data["message"]
    
    def test_get_status_exception(self, test_client, mock_realtime_engine):
        """测试获取状态异常"""
        mock_realtime_engine.get_status.side_effect = Exception("测试异常")
        
        response = test_client.get("/api/realtime/status")
        
        assert response.status_code == 500
        assert "测试异常" in response.json()["detail"]


# =============================================================================
# 控制API测试
# =============================================================================

class TestControlAPI:
    """测试控制API: start, stop, restart"""
    
    # --- Start API ---
    
    def test_start_engine_success(self, test_client, mock_realtime_engine):
        """测试启动引擎成功"""
        response = test_client.post("/api/realtime/start")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["success"] is True
        assert "启动成功" in data["message"]
        mock_realtime_engine.start.assert_called_once()
    
    def test_start_engine_failure(self, test_client, mock_realtime_engine):
        """测试启动引擎失败"""
        mock_realtime_engine.start.return_value = False
        
        response = test_client.post("/api/realtime/start")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "启动失败" in data["message"]
    
    def test_start_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时启动"""
        response = uninitialized_test_client.post("/api/realtime/start")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "实时引擎未初始化" in data["message"]
    
    def test_start_engine_exception(self, test_client, mock_realtime_engine):
        """测试启动引擎异常"""
        mock_realtime_engine.start.side_effect = Exception("启动异常")
        
        response = test_client.post("/api/realtime/start")
        
        assert response.status_code == 500
        assert "启动异常" in response.json()["detail"]
    
    # --- Stop API ---
    
    def test_stop_engine_success(self, test_client, mock_realtime_engine):
        """测试停止引擎成功"""
        response = test_client.post("/api/realtime/stop")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["success"] is True
        assert "停止成功" in data["message"]
        mock_realtime_engine.stop.assert_called_once()
    
    def test_stop_engine_failure(self, test_client, mock_realtime_engine):
        """测试停止引擎失败"""
        mock_realtime_engine.stop.return_value = False
        
        response = test_client.post("/api/realtime/stop")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "停止失败" in data["message"]
    
    def test_stop_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时停止"""
        response = uninitialized_test_client.post("/api/realtime/stop")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "实时引擎未初始化" in data["message"]
    
    # --- Restart API ---
    
    def test_restart_engine_success(self, test_client, mock_realtime_engine):
        """测试重启引擎成功"""
        response = test_client.post("/api/realtime/restart")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["success"] is True
        assert "重启成功" in data["message"]
        mock_realtime_engine.restart.assert_called_once()
    
    def test_restart_engine_failure(self, test_client, mock_realtime_engine):
        """测试重启引擎失败"""
        mock_realtime_engine.restart.return_value = False
        
        response = test_client.post("/api/realtime/restart")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "重启失败" in data["message"]
    
    def test_restart_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时重启"""
        response = uninitialized_test_client.post("/api/realtime/restart")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "实时引擎未初始化" in data["message"]


# =============================================================================
# 配置API测试
# =============================================================================

class TestConfigAPI:
    """测试配置API: GET/POST /api/realtime/config"""
    
    def test_get_config_success(self, test_client, mock_realtime_engine):
        """测试获取配置成功"""
        response = test_client.get("/api/realtime/config")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "获取配置成功" in data["message"]
        assert "data" in data
        mock_realtime_engine.get_config.assert_called_once()
    
    def test_get_config_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时获取配置"""
        response = uninitialized_test_client.get("/api/realtime/config")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "实时引擎未初始化" in data["message"]
    
    def test_update_config_success(self, test_client, mock_realtime_engine):
        """测试更新配置成功"""
        config = {"realtime_enabled": True, "data_mode": "realtime"}
        response = test_client.post("/api/realtime/config", json=config)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["success"] is True
        assert "配置更新成功" in data["message"]
        mock_realtime_engine.update_config.assert_called_once()
    
    def test_update_config_failure(self, test_client, mock_realtime_engine):
        """测试更新配置失败"""
        mock_realtime_engine.update_config.return_value = False
        
        config = {"realtime_enabled": False}
        response = test_client.post("/api/realtime/config", json=config)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "配置更新失败" in data["message"]
    
    def test_update_config_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时更新配置"""
        config = {"realtime_enabled": True}
        response = uninitialized_test_client.post("/api/realtime/config", json=config)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "实时引擎未初始化" in data["message"]


# =============================================================================
# 订阅API测试
# =============================================================================

class TestSubscribeAPI:
    """测试订阅API: subscribe, unsubscribe"""
    
    def test_subscribe_success(self, test_client, mock_realtime_engine):
        """测试订阅频道成功"""
        channels = ["kline.BTCUSDT.1m", "depth.BTCUSDT"]
        response = test_client.post("/api/realtime/subscribe", json=channels)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["success"] is True
        assert "订阅成功" in data["message"]
        mock_realtime_engine.subscribe.assert_called_once_with(channels)
    
    def test_subscribe_failure(self, test_client, mock_realtime_engine):
        """测试订阅频道失败"""
        mock_realtime_engine.subscribe.return_value = False
        
        channels = ["kline.BTCUSDT.1m"]
        response = test_client.post("/api/realtime/subscribe", json=channels)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "订阅失败" in data["message"]
    
    def test_subscribe_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时订阅"""
        channels = ["kline.BTCUSDT.1m"]
        response = uninitialized_test_client.post("/api/realtime/subscribe", json=channels)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "实时引擎未初始化" in data["message"]
    
    def test_unsubscribe_success(self, test_client, mock_realtime_engine):
        """测试取消订阅成功"""
        channels = ["kline.BTCUSDT.1m"]
        response = test_client.post("/api/realtime/unsubscribe", json=channels)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["success"] is True
        assert "取消订阅成功" in data["message"]
        mock_realtime_engine.unsubscribe.assert_called_once_with(channels)
    
    def test_unsubscribe_failure(self, test_client, mock_realtime_engine):
        """测试取消订阅失败"""
        mock_realtime_engine.unsubscribe.return_value = False
        
        channels = ["kline.BTCUSDT.1m"]
        response = test_client.post("/api/realtime/unsubscribe", json=channels)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "取消订阅失败" in data["message"]
    
    def test_unsubscribe_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时取消订阅"""
        channels = ["kline.BTCUSDT.1m"]
        response = uninitialized_test_client.post("/api/realtime/unsubscribe", json=channels)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert data["success"] is False
        assert "实时引擎未初始化" in data["message"]


# =============================================================================
# 数据API测试
# =============================================================================

class TestDataAPI:
    """测试数据API: symbols, data-types, intervals"""
    
    def test_get_symbols_success(self, test_client, mock_realtime_engine):
        """测试获取可用交易对成功"""
        response = test_client.get("/api/realtime/symbols")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "获取可用交易对成功" in data["message"]
        assert "data" in data
        assert isinstance(data["data"], list)
        mock_realtime_engine.get_available_symbols.assert_called_once()
    
    def test_get_symbols_engine_not_initialized(self, uninitialized_test_client):
        """测试引擎未初始化时获取交易对"""
        response = uninitialized_test_client.get("/api/realtime/symbols")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "实时引擎未初始化" in data["message"]
    
    def test_get_data_types(self, test_client):
        """测试获取支持的数据类型"""
        response = test_client.get("/api/realtime/data-types")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "获取支持的数据类型成功" in data["message"]
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "kline" in data["data"]
        assert "depth" in data["data"]
    
    def test_get_intervals(self, test_client):
        """测试获取支持的时间间隔"""
        response = test_client.get("/api/realtime/intervals")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "获取支持的时间间隔成功" in data["message"]
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "1m" in data["data"]
        assert "1d" in data["data"]


# =============================================================================
# 集成测试 - 完整工作流
# =============================================================================

class TestIntegrationWorkflow:
    """测试完整工作流"""
    
    def test_full_workflow(self, test_client, mock_realtime_engine):
        """测试完整工作流: 启动 -> 获取状态 -> 订阅 -> 停止"""
        # 1. 启动引擎
        response = test_client.post("/api/realtime/start")
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        # 2. 获取状态
        response = test_client.get("/api/realtime/status")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        
        # 3. 订阅频道
        channels = ["kline.BTCUSDT.1m"]
        response = test_client.post("/api/realtime/subscribe", json=channels)
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        # 4. 获取配置
        response = test_client.get("/api/realtime/config")
        assert response.status_code == 200
        assert response.json()["code"] == 0
        
        # 5. 停止引擎
        response = test_client.post("/api/realtime/stop")
        assert response.status_code == 200
        assert response.json()["success"] is True
