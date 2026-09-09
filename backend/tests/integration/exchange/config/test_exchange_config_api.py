"""
交易所配置API集成测试

覆盖 settings.routes 中 /api/v1/exchange-configs 的扁平化存储实现
（SystemConfigBusiness），通过 mock 配置库避免读写真实数据。
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_auth():
    """模拟JWT认证（装饰器认证路径）"""
    with (
        patch("utils.auth.decode_jwt_token") as mock_decode,
        patch("utils.auth.should_refresh_token", return_value=False),
    ):
        mock_decode.return_value = {"sub": "test_user", "name": "Test User"}
        yield mock_decode


@pytest.fixture
def mock_system_config():
    """mock 扁平化存储，避免触达真实配置库"""
    with (
        patch("settings.models.SystemConfigBusiness.get_all_flattened_by_prefix") as mock_get_all,
        patch("settings.models.SystemConfigBusiness.set_flattened") as mock_set,
        patch("settings.models.SystemConfigBusiness.delete_flattened") as mock_delete,
        patch("utils.config_manager.load_system_configs", return_value={}),
    ):
        yield {"get_all": mock_get_all, "set": mock_set, "delete": mock_delete}


class TestExchangeConfigAPI:
    """交易所配置API集成测试类"""

    def test_get_exchange_configs_list(self, client, mock_auth, mock_system_config):
        """测试获取交易所配置列表"""
        mock_system_config["get_all"].return_value = {
            "binance": {
                "name": "币安",
                "trading_mode": "spot",
                "quote_currency": "USDT",
                "commission_rate": 0.001,
                "proxy_enabled": True,
                "proxy_url": "http://proxy.example.com:8080",
                "is_default": True,
                "is_enabled": True,
            }
        }

        response = client.get(
            "/api/v1/exchange-configs/",
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["total"] == 1
        assert len(data["data"]["items"]) == 1
        assert data["data"]["items"][0]["exchange_id"] == "binance"
        assert data["data"]["items"][0]["proxy_enabled"] is True

    def test_create_exchange_config(self, client, mock_auth, mock_system_config):
        """测试创建交易所配置"""
        mock_system_config["set"].return_value = True

        response = client.post(
            "/api/v1/exchange-configs/",
            headers={"Authorization": "Bearer test_token"},
            json={
                "exchange_id": "binance",
                "name": "币安",
                "trading_mode": "spot",
                "quote_currency": "USDT",
                "commission_rate": 0.001,
                "proxy_enabled": False,
                "is_default": False,
                "is_enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["exchange_id"] == "binance"
        assert data["data"]["name"] == "币安"

    def test_update_exchange_config(self, client, mock_auth, mock_system_config):
        """测试更新交易所配置"""
        mock_system_config["set"].return_value = True

        response = client.put(
            "/api/v1/exchange-configs/binance",
            headers={"Authorization": "Bearer test_token"},
            json={
                "name": "币安Pro",
                "trading_mode": "futures",
                "proxy_enabled": True,
                "proxy_url": "http://new.proxy.com:9090",
                "is_default": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "币安Pro"
        assert data["data"]["proxy_url"] == "http://new.proxy.com:9090"

    def test_delete_exchange_config(self, client, mock_auth, mock_system_config):
        """测试删除交易所配置"""
        mock_system_config["delete"].return_value = True

        response = client.delete(
            "/api/v1/exchange-configs/binance",
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_get_supported_exchanges(self, client, mock_auth, mock_system_config):
        """测试获取支持的交易所列表"""
        response = client.get(
            "/api/v1/exchange-configs/exchanges",
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "exchanges" in data["data"]
        exchanges = data["data"]["exchanges"]
        assert len(exchanges) >= 2
        assert exchanges[0]["id"] == "binance"
        assert exchanges[1]["id"] == "okx"


class TestExchangeConfigAuth:
    """交易所配置认证测试类"""

    def test_unauthorized_access(self, client):
        """测试未授权访问被拒绝"""
        response = client.get("/api/v1/exchange-configs/")

        assert response.status_code == 401

    def test_invalid_token(self, client):
        """测试无效令牌"""
        with patch("utils.auth.decode_jwt_token") as mock_decode:
            from utils.jwt_utils import TokenInvalidError

            mock_decode.side_effect = TokenInvalidError("Invalid token")

            response = client.get(
                "/api/v1/exchange-configs/",
                headers={"Authorization": "Bearer invalid_token"},
            )

        assert response.status_code == 401
