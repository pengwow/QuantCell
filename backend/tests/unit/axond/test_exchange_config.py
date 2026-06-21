# -*- coding: utf-8 -*-
"""axon 交易所配置测试"""
import pytest
import os
from unittest.mock import patch


class TestAxonExchangeConfig:
    def test_build_binance_testnet_config(self):
        from axond.exchange_config import build_exchange_config
        with patch.dict(os.environ, {"BINANCE_API_KEY": "test_key", "BINANCE_API_SECRET": "test_secret"}):
            config = build_exchange_config("binance", "testnet")
            assert config is not None
            assert config["exchange"] == "binance"
            assert config["testnet"] is True

    def test_build_okx_testnet_config(self):
        from axond.exchange_config import build_exchange_config
        with patch.dict(os.environ, {
            "OKX_API_KEY": "test_key",
            "OKX_API_SECRET": "test_secret",
            "OKX_PASSPHRASE": "test_pass",
        }):
            config = build_exchange_config("okx", "testnet")
            assert config is not None
            assert config["exchange"] == "okx"
            assert config["testnet"] is True

    def test_build_binance_production_config(self):
        from axond.exchange_config import build_exchange_config
        with patch.dict(os.environ, {"BINANCE_API_KEY": "prod_key", "BINANCE_API_SECRET": "prod_secret"}):
            config = build_exchange_config("binance", "production")
            assert config["testnet"] is False

    def test_missing_env_vars_raises(self):
        from axond.exchange_config import build_exchange_config
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="缺少"):
                build_exchange_config("binance", "testnet")

    def test_unsupported_exchange_raises(self):
        from axond.exchange_config import build_exchange_config
        with pytest.raises(ValueError, match="不支持"):
            build_exchange_config("unsupported", "testnet")
