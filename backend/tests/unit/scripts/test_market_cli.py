"""市场数据CLI单元测试"""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestCliKlines:
    """测试 CLI klines 命令"""

    @patch("cli.market.get_klines")
    def test_cli_klines_success(self, mock_get):
        """测试 CLI klines 命令成功"""
        from cli.market import app

        mock_get.return_value = "BTCUSDT 1h K线数据"

        result = runner.invoke(app, ["klines", "--symbol", "BTCUSDT", "--timeframe", "1h"])
        assert result.exit_code == 0
        assert "BTCUSDT" in result.output

    @patch("cli.market.get_klines")
    def test_cli_klines_error(self, mock_get):
        """测试 CLI klines 命令异常"""
        from cli.market import app

        mock_get.return_value = "错误: 获取失败"

        result = runner.invoke(app, ["klines", "--symbol", "BTCUSDT"])
        assert result.exit_code == 0
        assert "错误" in result.output


class TestCliTicker:
    """测试 CLI ticker 命令"""

    @patch("cli.market.get_ticker")
    def test_cli_ticker_success(self, mock_get):
        """测试 CLI ticker 命令成功"""
        from cli.market import app

        mock_get.return_value = "BTCUSDT 最新行情: 50000"

        result = runner.invoke(app, ["ticker", "--symbol", "BTCUSDT"])
        assert result.exit_code == 0
        assert "BTCUSDT" in result.output


class TestCliSymbols:
    """测试 CLI symbols 命令"""

    @patch("cli.market.get_crypto_symbols")
    def test_cli_symbols_success(self, mock_get):
        """测试 CLI symbols 命令成功"""
        from cli.market import app

        mock_get.return_value = json.dumps({"success": True, "total": 2})

        result = runner.invoke(app, ["symbols", "--exchange", "binance"])
        assert result.exit_code == 0
        assert "success" in result.output


class TestCliFetch:
    """测试 CLI fetch 命令"""

    @patch("cli.market.fetch_market_data")
    def test_cli_fetch_success(self, mock_fetch):
        """测试 CLI fetch 命令成功"""
        from cli.market import app

        mock_fetch.return_value = json.dumps({"success": True, "symbol": "BTCUSDT"})

        result = runner.invoke(app, ["fetch", "--symbol", "BTCUSDT", "--data-type", "kline"])
        assert result.exit_code == 0
        assert "BTCUSDT" in result.output

    @patch("cli.market.fetch_market_data")
    def test_cli_fetch_unsupported_type(self, mock_fetch):
        """测试 CLI fetch 命令不支持类型"""
        from cli.market import app

        mock_fetch.return_value = json.dumps({"success": False, "error": "不支持"})

        result = runner.invoke(app, ["fetch", "--symbol", "BTCUSDT", "--data-type", "invalid"])
        assert result.exit_code == 0


class TestGetKlines:
    """测试 get_klines 函数"""

    @patch("ccxt.binance")
    def test_get_klines_success(self, mock_exchange_cls):
        """测试成功获取K线数据"""
        from cli.market import get_klines

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
        assert "2009-02-13 23:31:30" in result
        assert "1234567890000" in result

    @patch("ccxt.binance")
    def test_get_klines_empty(self, mock_exchange_cls):
        """测试空K线数据"""
        from cli.market import get_klines

        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.return_value = []
        mock_exchange_cls.return_value = mock_exchange

        result = get_klines("BTCUSDT", "1h", 100, "binance")
        assert "未找到" in result

    @patch("ccxt.binance")
    def test_get_klines_error(self, mock_exchange_cls):
        """测试异常处理"""
        from cli.market import get_klines

        mock_exchange_cls.side_effect = Exception("网络错误")

        result = get_klines("BTCUSDT", "1h", 100, "binance")
        assert result.startswith("错误:")
        assert "网络错误" in result


class TestGetTicker:
    """测试 get_ticker 函数"""

    @patch("ccxt.binance")
    def test_get_ticker_success(self, mock_exchange_cls):
        """测试成功获取行情"""
        from cli.market import get_ticker

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
        from cli.market import get_ticker

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
        from cli.market import get_crypto_symbols

        mock_exchange = MagicMock()
        mock_exchange.markets = {
            "BTC/USDT": {
                "base": "BTC",
                "quote": "USDT",
                "active": True,
                "type": "spot",
            },
            "ETH/USDT": {
                "base": "ETH",
                "quote": "USDT",
                "active": True,
                "type": "spot",
            },
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
        from cli.market import fetch_market_data

        result = fetch_market_data("BTCUSDT", "unsupported_type")
        data = json.loads(result)
        assert data["success"] is False
        assert "不支持" in data["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
