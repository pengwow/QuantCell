"""市场数据CLI单元测试"""

import pytest
import json
from unittest.mock import patch, MagicMock


class TestGetKlines:
    """测试 get_klines 函数"""

    @patch("ccxt.binance")
    def test_get_klines_success(self, mock_exchange_cls):
        """测试成功获取K线数据"""
        from scripts.market_cli import get_klines

        # 模拟交易所返回数据
        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.return_value = [
            [1234567890000, 100.0, 110.0, 90.0, 105.0, 1000.0],
            [1234567900000, 105.0, 115.0, 95.0, 110.0, 1200.0],
        ]
        mock_exchange_cls.return_value = mock_exchange

        result = get_klines("BTCUSDT", "1h", 100, "binance")
        assert "BTCUSDT" in result
        assert "1h" in result

    @patch("ccxt.binance")
    def test_get_klines_empty(self, mock_exchange_cls):
        """测试空K线数据"""
        from scripts.market_cli import get_klines

        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.return_value = []
        mock_exchange_cls.return_value = mock_exchange

        result = get_klines("BTCUSDT", "1h", 100, "binance")
        assert "未找到" in result

    @patch("ccxt.binance")
    def test_get_klines_error(self, mock_exchange_cls):
        """测试异常处理"""
        from scripts.market_cli import get_klines

        mock_exchange_cls.side_effect = Exception("网络错误")

        result = get_klines("BTCUSDT", "1h", 100, "binance")
        assert result.startswith("错误:")
        assert "网络错误" in result


class TestGetTicker:
    """测试 get_ticker 函数"""

    @patch("ccxt.binance")
    def test_get_ticker_success(self, mock_exchange_cls):
        """测试成功获取行情"""
        from scripts.market_cli import get_ticker

        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {
            "last": 50000.0,
            "percentage": 2.5,
            "high": 51000.0,
            "low": 49000.0,
            "baseVolume": 1000.0,
            "bid": 49999.0,
            "ask": 50001.0,
        }
        mock_exchange_cls.return_value = mock_exchange

        result = get_ticker("BTCUSDT", "binance")
        assert "BTCUSDT" in result
        assert "50000" in result

    @patch("ccxt.binance")
    def test_get_ticker_empty(self, mock_exchange_cls):
        """测试空行情数据"""
        from scripts.market_cli import get_ticker

        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {}
        mock_exchange_cls.return_value = mock_exchange

        result = get_ticker("BTCUSDT", "binance")
        assert "未找到" in result


class TestGetCryptoSymbols:
    """测试 get_crypto_symbols 函数"""

    @patch("ccxt.binance")
    def test_get_crypto_symbols_success(self, mock_exchange_cls):
        """测试成功获取交易对列表"""
        from scripts.market_cli import get_crypto_symbols

        mock_exchange = MagicMock()
        mock_exchange.markets = {
            "BTC/USDT": {"base": "BTC", "quote": "USDT", "active": True, "type": "spot"},
            "ETH/USDT": {"base": "ETH", "quote": "USDT", "active": True, "type": "spot"},
        }
        mock_exchange_cls.return_value = mock_exchange

        result = get_crypto_symbols("binance", "USDT", 100, "spot")
        data = json.loads(result)
        assert data["success"] is True
        assert data["total"] == 2


class TestFetchMarketData:
    """测试 fetch_market_data 函数"""

    def test_fetch_market_data_unsupported_type(self):
        """测试不支持的数据类型"""
        from scripts.market_cli import fetch_market_data

        result = fetch_market_data("BTCUSDT", "unsupported_type")
        data = json.loads(result)
        assert data["success"] is False
        assert "不支持" in data["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
