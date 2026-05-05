"""
交易所连接测试服务（向后兼容层）

已迁移至 exchange 模块，此文件保留用于向后兼容。
新代码请使用: from exchange import test_exchange_connection, SUPPORTED_EXCHANGES
"""

import warnings
from typing import Optional

from exchange.types import ConnectionTestResult, ConnectionStatus
from exchange.connection import (
    test_exchange_connection as _test_exchange_connection,
    test_exchange_connection_sync,
    SUPPORTED_EXCHANGES,
)

warnings.warn(
    "collector.services.exchange_connection_service 已废弃，"
    "请使用 from exchange import test_exchange_connection 替代",
    DeprecationWarning,
    stacklevel=2
)


class ExchangeConnectionService:
    """向后兼容的连通性测试服务类"""
    
    SUPPORTED_EXCHANGES = SUPPORTED_EXCHANGES
    
    async def test_connection(
        self,
        exchange_name: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        api_passphrase: Optional[str] = None,
        proxy_url: Optional[str] = None,
        trading_mode: str = "spot",
        testnet: bool = False,
    ) -> ConnectionTestResult:
        return await _test_exchange_connection(
            exchange_name=exchange_name,
            api_key=api_key,
            secret_key=secret_key,
            api_passphrase=api_passphrase,
            proxy_url=proxy_url,
            trading_mode=trading_mode,
            testnet=testnet,
        )


exchange_connection_service = ExchangeConnectionService()
