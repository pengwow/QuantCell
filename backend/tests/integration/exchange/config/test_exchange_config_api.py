"""
交易所配置API集成测试

测试完整的API接口流程
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from main import app


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_auth():
    """模拟JWT认证"""
    with patch("utils.auth.decode_jwt_token") as mock_decode:
        mock_decode.return_value = {"sub": "test_user", "name": "Test User"}
        yield mock_decode


@pytest.fixture
def mock_should_refresh():
    """模拟不需要刷新token"""
    with patch("utils.auth.should_refresh_token") as mock_refresh:
        mock_refresh.return_value = False
        yield mock_refresh


class TestExchangeConfigAPI:
    """交易所配置API集成测试类"""

    def test_get_exchange_configs_list(self, client, mock_auth, mock_should_refresh):
        """测试获取交易所配置列表"""
        with patch("exchange.config.models.ExchangeConfigBusiness.list") as mock_list:
            mock_list.return_value = {
                "items": [
                    {
                        "id": 1,
                        "exchange_id": "binance",
                        "name": "币安",
                        "trading_mode": "spot",
                        "quote_currency": "USDT",
                        "commission_rate": 0.001,
                        "proxy_enabled": True,
                        "proxy_url": "http://proxy.example.com:8080",
                        "proxy_username": "user",
                        "proxy_password": "pass",
                        "is_default": True,
                        "is_enabled": True,
                        "created_at": "2026-03-02 10:00:00",
                        "updated_at": "2026-03-02 10:00:00",
                        "api_key_masked": "tes...1234",
                        "api_secret_masked": "sec...5678"
                    }
                ],
                "total": 1,
                "page": 1,
                "limit": 10,
                "pages": 1
            }

            response = client.get(
                "/api/exchange-configs/",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["total"] == 1
        assert len(data["data"]["items"]) == 1
        # 验证代理字段
        assert data["data"]["items"][0]["proxy_enabled"] is True
        assert data["data"]["items"][0]["proxy_url"] == "http://proxy.example.com:8080"

    def test_create_exchange_config(self, client, mock_auth, mock_should_refresh):
        """测试创建交易所配置"""
        with patch("exchange.config.models.ExchangeConfigBusiness.create") as mock_create:
            mock_create.return_value = {
                "id": 1,
                "exchange_id": "binance",
                "name": "币安",
                "trading_mode": "spot",
                "quote_currency": "USDT",
                "commission_rate": 0.001,
                "proxy_enabled": False,
                "proxy_url": None,
                "proxy_username": None,
                "proxy_password": None,
                "is_default": False,
                "is_enabled": True,
                "created_at": "2026-03-02 10:00:00",
                "updated_at": "2026-03-02 10:00:00",
                "api_key_masked": "tes...1234",
                "api_secret_masked": "sec...5678"
            }

            response = client.post(
                "/api/exchange-configs/",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "exchange_id": "binance",
                    "name": "币安",
                    "trading_mode": "spot",
                    "quote_currency": "USDT",
                    "commission_rate": 0.001,
                    "api_key": "test_api_key",
                    "api_secret": "test_api_secret",
                    "proxy_enabled": False,
                    "is_default": False,
                    "is_enabled": True
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["exchange_id"] == "binance"

    def test_get_exchange_config_by_id(self, client, mock_auth, mock_should_refresh):
        """测试获取单个交易所配置"""
        with patch("exchange.config.models.ExchangeConfigBusiness.get_by_id") as mock_get:
            mock_get.return_value = {
                "id": 1,
                "exchange_id": "okx",
                "name": "OKX",
                "trading_mode": "futures",
                "quote_currency": "USDT",
                "commission_rate": 0.0005,
                "proxy_enabled": True,
                "proxy_url": "http://proxy.okx.com:8080",
                "proxy_username": "okx_user",
                "proxy_password": "okx_pass",
                "is_default": False,
                "is_enabled": True,
                "created_at": "2026-03-02 10:00:00",
                "updated_at": "2026-03-02 10:00:00",
                "api_key_masked": "okx...key",
                "api_secret_masked": "okx...secret"
            }

            response = client.get(
                "/api/exchange-configs/1",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["id"] == 1
        assert data["data"]["exchange_id"] == "okx"
        # 验证代理字段
        assert data["data"]["proxy_enabled"] is True
        assert data["data"]["proxy_url"] == "http://proxy.okx.com:8080"

    def test_update_exchange_config(self, client, mock_auth, mock_should_refresh):
        """测试更新交易所配置"""
        with patch("exchange.config.models.ExchangeConfigBusiness.update") as mock_update:
            mock_update.return_value = {
                "id": 1,
                "exchange_id": "binance",
                "name": "币安Pro",
                "trading_mode": "futures",
                "quote_currency": "USDT",
                "commission_rate": 0.0005,
                "proxy_enabled": True,
                "proxy_url": "http://new.proxy.com:9090",
                "proxy_username": "new_user",
                "proxy_password": "new_pass",
                "is_default": True,
                "is_enabled": True,
                "created_at": "2026-03-02 10:00:00",
                "updated_at": "2026-03-02 11:00:00",
                "api_key_masked": "new...key",
                "api_secret_masked": "new...secret"
            }

            response = client.put(
                "/api/exchange-configs/1",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "name": "币安Pro",
                    "trading_mode": "futures",
                    "proxy_enabled": True,
                    "proxy_url": "http://new.proxy.com:9090",
                    "is_default": True
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "币安Pro"
        assert data["data"]["proxy_url"] == "http://new.proxy.com:9090"

    def test_delete_exchange_config(self, client, mock_auth, mock_should_refresh):
        """测试删除交易所配置"""
        with patch("exchange.config.models.ExchangeConfigBusiness.delete") as mock_delete:
            mock_delete.return_value = True

            response = client.delete(
                "/api/exchange-configs/1",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_get_supported_exchanges(self, client, mock_auth, mock_should_refresh):
        """测试获取支持的交易所列表"""
        response = client.get(
            "/api/exchange-configs/exchanges",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "exchanges" in data["data"]
        assert len(data["data"]["exchanges"]) == 2
        assert data["data"]["exchanges"][0]["id"] == "binance"
        assert data["data"]["exchanges"][1]["id"] == "okx"


class TestExchangeConfigAuth:
    """交易所配置认证测试类"""

    def test_unauthorized_access(self, client):
        """测试未授权访问被拒绝"""
        response = client.get("/api/exchange-configs/")

        assert response.status_code == 401

    def test_invalid_token(self, client):
        """测试无效令牌"""
        with patch("utils.auth.decode_jwt_token") as mock_decode:
            from utils.jwt_utils import TokenInvalidError
            mock_decode.side_effect = TokenInvalidError("Invalid token")

            response = client.get(
                "/api/exchange-configs/",
                headers={"Authorization": "Bearer invalid_token"}
            )

        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
