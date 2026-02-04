# -*- coding: utf-8 -*-
"""
加密货币对同步服务单元测试

测试CryptoSymbolService和sync_crypto_symbols函数的功能
"""

import json
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# 添加backend目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from collector.services.crypto_symbol_service import (
    sync_crypto_symbols,
    CryptoSymbolService,
)
from collector.db.models import CryptoSymbol


class TestSyncCryptoSymbols:
    """测试sync_crypto_symbols函数"""

    @patch('collector.services.crypto_symbol_service.init_database_config')
    @patch('collector.services.crypto_symbol_service.SessionLocal')
    def test_sync_crypto_symbols_success(
        self, mock_session_local, mock_init_db
    ):
        """测试同步加密货币对成功的情况"""
        # 模拟ccxt模块
        with patch.dict('sys.modules', {'ccxt': MagicMock()}):
            import ccxt
            # 模拟交易所实例
            mock_exchange = MagicMock()
            mock_exchange.timeout = 30000
            mock_exchange.enableRateLimit = True
            mock_exchange.load_markets.return_value = {
                'BTC/USDT': {
                    'symbol': 'BTC/USDT',
                    'base': 'BTC',
                    'quote': 'USDT',
                    'active': True,
                    'precision': {'price': 2, 'amount': 6},
                    'limits': {'amount': {'min': 0.0001, 'max': 10000}},
                    'type': 'spot'
                },
                'ETH/USDT': {
                    'symbol': 'ETH/USDT',
                    'base': 'ETH',
                    'quote': 'USDT',
                    'active': True,
                    'precision': {'price': 2, 'amount': 5},
                    'limits': {'amount': {'min': 0.001, 'max': 5000}},
                    'type': 'spot'
                }
            }
            ccxt.binance = MagicMock(return_value=mock_exchange)

            # 模拟数据库会话
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            # 模拟查询结果为空（没有现有货币对）
            mock_db.query.return_value.filter_by.return_value.all.return_value = []

            # 执行同步
            result = sync_crypto_symbols(exchange='binance')

            # 验证结果
            assert result['success'] is True
            assert result['exchange'] == 'binance'
            assert result['symbol_count'] == 2
            assert result['inserted_count'] == 2
            assert result['updated_count'] == 0
            assert result['deleted_count'] == 0
            assert 'timestamp' in result

            # 验证数据库操作
            mock_db.add.assert_called()
            mock_db.commit.assert_called()
            mock_db.close.assert_called()

    @patch('collector.services.crypto_symbol_service.init_database_config')
    @patch('collector.services.crypto_symbol_service.SessionLocal')
    def test_sync_crypto_symbols_with_existing_symbols(
        self, mock_session_local, mock_init_db
    ):
        """测试同步时存在现有货币对的情况"""
        with patch.dict('sys.modules', {'ccxt': MagicMock()}):
            import ccxt
            # 模拟交易所实例
            mock_exchange = MagicMock()
            mock_exchange.load_markets.return_value = {
                'BTC/USDT': {
                    'symbol': 'BTC/USDT',
                    'base': 'BTC',
                    'quote': 'USDT',
                    'active': True,
                    'precision': {'price': 2},
                    'limits': {'amount': {'min': 0.0001}},
                    'type': 'spot'
                }
            }
            ccxt.binance = MagicMock(return_value=mock_exchange)

            # 模拟数据库会话
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            # 模拟现有货币对
            existing_symbol = MagicMock()
            existing_symbol.symbol = 'BTC/USDT'
            existing_symbol.active = True
            existing_symbol.is_deleted = False
            mock_db.query.return_value.filter_by.return_value.all.return_value = [existing_symbol]

            # 执行同步
            result = sync_crypto_symbols(exchange='binance')

            # 验证结果 - 应该更新现有货币对
            assert result['success'] is True
            assert result['updated_count'] == 1
            assert result['inserted_count'] == 0

    @patch('collector.services.crypto_symbol_service.init_database_config')
    @patch('collector.services.crypto_symbol_service.SessionLocal')
    def test_sync_crypto_symbols_with_proxy(
        self, mock_session_local, mock_init_db
    ):
        """测试使用代理同步加密货币对"""
        with patch.dict('sys.modules', {'ccxt': MagicMock()}):
            import ccxt
            # 模拟交易所实例
            mock_exchange = MagicMock()
            mock_exchange.load_markets.return_value = {}
            ccxt.binance = MagicMock(return_value=mock_exchange)

            # 模拟数据库会话
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.all.return_value = []

            # 执行同步（启用代理）
            result = sync_crypto_symbols(
                exchange='binance',
                proxy_enabled=True,
                proxy_url='http://127.0.0.1:7897',
                proxy_username='user',
                proxy_password='pass'
            )

            # 验证代理设置
            assert mock_exchange.proxies == {
                'http': 'http://127.0.0.1:7897',
                'https': 'http://127.0.0.1:7897'
            }
            assert result['success'] is True

    def test_sync_crypto_symbols_exchange_error(self):
        """测试交易所API调用失败的情况"""
        with patch.dict('sys.modules', {'ccxt': MagicMock()}):
            import ccxt
            # 模拟交易所实例抛出异常
            mock_exchange = MagicMock()
            mock_exchange.load_markets.side_effect = Exception("API Error")
            ccxt.binance = MagicMock(return_value=mock_exchange)

            # 执行同步
            result = sync_crypto_symbols(exchange='binance')

            # 验证结果
            assert result['success'] is False
            assert 'API Error' in result['message']
            assert result['exchange'] == 'binance'

    @patch('collector.services.crypto_symbol_service.init_database_config')
    @patch('collector.services.crypto_symbol_service.SessionLocal')
    def test_sync_crypto_symbols_mark_inactive(
        self, mock_session_local, mock_init_db
    ):
        """测试标记不再存在的货币对为已删除"""
        with patch.dict('sys.modules', {'ccxt': MagicMock()}):
            import ccxt
            # 模拟交易所实例 - 只返回一个货币对
            mock_exchange = MagicMock()
            mock_exchange.load_markets.return_value = {
                'BTC/USDT': {
                    'symbol': 'BTC/USDT',
                    'base': 'BTC',
                    'quote': 'USDT',
                    'active': True,
                    'precision': {},
                    'limits': {},
                    'type': 'spot'
                }
            }
            ccxt.binance = MagicMock(return_value=mock_exchange)

            # 模拟数据库会话
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            # 模拟数据库中有两个货币对，但API只返回一个
            existing_symbol1 = MagicMock()
            existing_symbol1.symbol = 'BTC/USDT'
            existing_symbol2 = MagicMock()
            existing_symbol2.symbol = 'ETH/USDT'
            mock_db.query.return_value.filter_by.return_value.all.return_value = [
                existing_symbol1, existing_symbol2
            ]

            # 执行同步
            result = sync_crypto_symbols(exchange='binance')

            # 验证结果 - ETH/USDT应该被标记为已删除
            assert result['success'] is True
            assert result['deleted_count'] == 1
            assert existing_symbol2.is_deleted is True
            assert existing_symbol2.active is False


class TestCryptoSymbolService:
    """测试CryptoSymbolService类"""

    @patch('collector.services.crypto_symbol_service.sync_crypto_symbols')
    def test_sync_symbols(self, mock_sync):
        """测试sync_symbols方法"""
        # 设置模拟返回值
        mock_sync.return_value = {
            'success': True,
            'message': '同步成功',
            'exchange': 'binance',
            'symbol_count': 10
        }

        # 调用方法
        result = CryptoSymbolService.sync_symbols(
            exchange='binance',
            proxy_enabled=True,
            proxy_url='http://proxy.example.com'
        )

        # 验证结果
        assert result['success'] is True
        mock_sync.assert_called_once_with(
            exchange='binance',
            proxy_enabled=True,
            proxy_url='http://proxy.example.com',
            proxy_username=None,
            proxy_password=None,
        )

    @patch('collector.services.crypto_symbol_service.sync_crypto_symbols')
    def test_sync_all_exchanges(self, mock_sync):
        """测试sync_all_exchanges方法"""
        # 设置模拟返回值
        mock_sync.return_value = {
            'success': True,
            'message': '同步成功',
            'exchange': 'binance',
            'symbol_count': 10
        }

        # 调用方法
        result = CryptoSymbolService.sync_all_exchanges(
            exchanges=['binance', 'okx'],
            proxy_enabled=False
        )

        # 验证结果
        assert result['success'] is True
        assert 'results' in result
        assert 'binance' in result['results']
        assert 'okx' in result['results']
        assert mock_sync.call_count == 2

    @patch('collector.services.crypto_symbol_service.sync_crypto_symbols')
    def test_sync_all_exchanges_default(self, mock_sync):
        """测试sync_all_exchanges方法使用默认交易所"""
        # 设置模拟返回值
        mock_sync.return_value = {
            'success': True,
            'message': '同步成功',
            'exchange': 'binance',
            'symbol_count': 10
        }

        # 调用方法（不传递exchanges参数）
        result = CryptoSymbolService.sync_all_exchanges()

        # 验证结果 - 应该使用默认的binance
        assert result['success'] is True
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        assert call_kwargs[1]['exchange'] == 'binance'


class TestCryptoSymbolServiceIntegration:
    """集成测试 - 测试与数据库的交互"""

    def test_service_structure(self):
        """测试服务类结构正确"""
        # 验证类存在且有正确的静态方法
        assert hasattr(CryptoSymbolService, 'sync_symbols')
        assert hasattr(CryptoSymbolService, 'sync_all_exchanges')

    def test_sync_crypto_symbols_function_exists(self):
        """测试sync_crypto_symbols函数存在"""
        assert callable(sync_crypto_symbols)


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v'])
