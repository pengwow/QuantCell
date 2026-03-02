"""
交易所配置业务逻辑层单元测试

测试ExchangeConfigBusiness类的CRUD操作和API密钥处理功能
"""

import pytest
from unittest.mock import MagicMock, patch

from exchange.config.models import ExchangeConfigBusiness


class TestExchangeConfigBusiness:
    """ExchangeConfigBusiness单元测试类"""

    def test_mask_api_key_short(self):
        """测试短API密钥脱敏"""
        result = ExchangeConfigBusiness._mask_api_key("short")
        assert result == "********"

    def test_mask_api_key_normal(self):
        """测试正常API密钥脱敏"""
        api_key = "sk-abcdefghijklmnopqrstuvwxyz123456"
        result = ExchangeConfigBusiness._mask_api_key(api_key)
        assert result == "sk-a...3456"
        assert "..." in result

    def test_mask_api_key_empty(self):
        """测试空API密钥脱敏"""
        result = ExchangeConfigBusiness._mask_api_key("")
        assert result is None

    def test_mask_api_key_none(self):
        """测试None API密钥脱敏"""
        result = ExchangeConfigBusiness._mask_api_key(None)
        assert result is None

    def test_create_exchange_config(self):
        """测试创建交易所配置 - 模拟完整流程"""
        mock_config = MagicMock()
        mock_config.id = 1
        mock_config.exchange_id = "binance"
        mock_config.name = "币安"
        mock_config.trading_mode = "spot"
        mock_config.quote_currency = "USDT"
        mock_config.commission_rate = 0.001
        mock_config.api_key = "test_api_key"
        mock_config.api_secret = "test_api_secret"
        mock_config.proxy_enabled = True
        mock_config.proxy_url = "http://proxy.example.com:8080"
        mock_config.proxy_username = "user"
        mock_config.proxy_password = "pass"
        mock_config.is_default = True
        mock_config.is_enabled = True
        mock_config.created_at = None
        mock_config.updated_at = None

        result = ExchangeConfigBusiness._to_dict(mock_config)

        assert result is not None
        assert result["exchange_id"] == "binance"
        assert result["name"] == "币安"
        assert result["trading_mode"] == "spot"
        assert result["proxy_enabled"] is True
        assert result["proxy_url"] == "http://proxy.example.com:8080"

    def test_to_dict_with_api_key(self):
        """测试包含API密钥的字典转换"""
        mock_config = MagicMock()
        mock_config.id = 1
        mock_config.exchange_id = "okx"
        mock_config.name = "OKX"
        mock_config.trading_mode = "futures"
        mock_config.quote_currency = "USDT"
        mock_config.commission_rate = 0.0005
        mock_config.api_key = "my_secret_key_12345"
        mock_config.api_secret = "my_secret_secret_67890"
        mock_config.proxy_enabled = False
        mock_config.proxy_url = None
        mock_config.proxy_username = None
        mock_config.proxy_password = None
        mock_config.is_default = False
        mock_config.is_enabled = True
        mock_config.created_at = None
        mock_config.updated_at = None

        # 不包含API密钥
        result_without_key = ExchangeConfigBusiness._to_dict(mock_config, include_api_key=False)
        assert "api_key_masked" in result_without_key
        assert "api_secret_masked" in result_without_key
        assert result_without_key["api_key_masked"] == "my_s...2345"

        # 包含API密钥
        result_with_key = ExchangeConfigBusiness._to_dict(mock_config, include_api_key=True)
        assert result_with_key["api_key"] == "my_secret_key_12345"
        assert result_with_key["api_secret"] == "my_secret_secret_67890"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
