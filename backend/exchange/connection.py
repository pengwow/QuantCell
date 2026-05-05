"""
交易所连通性测试服务

基于 exchange 模块的 BaseExchange/BinanceExchange 实现，
提供统一的交易所连接测试功能。

使用示例:
    >>> from exchange.connection import test_exchange_connection
    >>> result = await test_exchange_connection('binance', api_key='xxx', secret_key='xxx', testnet=True)
    >>> print(result.status, result.message)
"""

import asyncio
from typing import Optional

from utils.logger import get_logger, LogType
from exchange.types import ConnectionTestResult, ConnectionStatus
from exchange.base import BaseExchange

logger = get_logger(__name__, LogType.APPLICATION)

SUPPORTED_EXCHANGES = ["binance", "okx"]


def _create_exchange_instance(
    exchange_name: str,
    api_key=None,
    secret_key=None,
    trading_mode="spot",
    proxy_url=None,
    testnet=False,
) -> BaseExchange:
    """内部工厂函数，避免循环导入"""
    if exchange_name == "binance":
        from exchange.binance.exchange import BinanceExchange
        return BinanceExchange(
            exchange_name=exchange_name,
            api_key=api_key,
            secret_key=secret_key,
            trading_mode=trading_mode,
            proxy_url=proxy_url,
            testnet=testnet,
        )
    elif exchange_name == "okx":
        from exchange.okx.exchange import OkxExchange
        return OkxExchange(
            exchange_name=exchange_name,
            api_key=api_key,
            secret_key=secret_key,
            trading_mode=trading_mode,
            proxy_url=proxy_url,
            testnet=testnet,
        )
    else:
        raise ValueError(f"不支持的交易所: {exchange_name}")


async def test_exchange_connection(
    exchange_name: str,
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    api_passphrase: Optional[str] = None,
    proxy_url: Optional[str] = None,
    trading_mode: str = "spot",
    testnet: bool = False,
) -> ConnectionTestResult:
    """
    异步测试交易所连接（内部调用同步的 Exchange.test_connection）
    
    Args:
        exchange_name: 交易所名称 (binance, okx)
        api_key: API密钥
        secret_key: API密钥密钥
        api_passphrase: API密码（OKX需要）
        proxy_url: 代理URL
        trading_mode: 交易模式 (spot, future)
        testnet: 是否使用测试网络
    
    Returns:
        ConnectionTestResult: 连接测试结果
    """
    if exchange_name not in SUPPORTED_EXCHANGES:
        return ConnectionTestResult(
            success=False,
            status=ConnectionStatus.UNKNOWN_ERROR,
            message=f"不支持的交易所: {exchange_name}，支持的交易所: {SUPPORTED_EXCHANGES}",
            details={"supported": SUPPORTED_EXCHANGES},
        )
    
    try:
        logger.info(f"开始测试连接: exchange={exchange_name}, mode={trading_mode}, testnet={testnet}")
        loop = asyncio.get_event_loop()
        
        def _run_test():
            logger.debug(f"创建 Exchange 实例: {exchange_name}")
            exchange = _create_exchange_instance(
                exchange_name=exchange_name,
                api_key=api_key,
                secret_key=secret_key,
                trading_mode=trading_mode,
                proxy_url=proxy_url,
                testnet=testnet,
            )
            logger.debug(f"调用 test_connection()...")
            result = exchange.test_connection()
            logger.debug(f"test_connection() 返回: status={result.status.value}, success={result.success}")
            return result
        
        result = await loop.run_in_executor(None, _run_test)
        
        if result.success:
            logger.info(f"测试连接成功: {exchange_name} ({result.response_time_ms:.0f}ms)")
        else:
            logger.warning(
                f"测试连接失败: {exchange_name}, status={result.status.value}, "
                f"message={result.message}, details={result.details}"
            )
        return result
    
    except ImportError as e:
        logger.error(f"导入交易所模块失败: {e}")
        return ConnectionTestResult(
            success=False,
            status=ConnectionStatus.UNKNOWN_ERROR,
            message=f"交易所模块加载失败: {e}",
            details={"error": str(e)},
        )
    except Exception as e:
        logger.error(f"测试连接异常: {e}")
        return ConnectionTestResult(
            success=False,
            status=ConnectionStatus.UNKNOWN_ERROR,
            message=f"测试过程发生异常: {e}",
            details={"error": str(e)},
        )


def test_exchange_connection_sync(
    exchange_name: str,
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    api_passphrase: Optional[str] = None,
    proxy_url: Optional[str] = None,
    trading_mode: str = "spot",
    testnet: bool = False,
) -> ConnectionTestResult:
    """
    同步版本：测试交易所连接
    
    适用于非异步上下文（如脚本、CLI工具等）。
    
    Args:
        exchange_name: 交易所名称 (binance, okx)
        api_key: API密钥
        secret_key: API密钥密钥
        api_passphrase: API密码（OKX需要）
        proxy_url: 代理URL
        trading_mode: 交易模式 (spot, future)
        testnet: 是否使用测试网络
    
    Returns:
        ConnectionTestResult: 连接测试结果
    """
    if exchange_name not in SUPPORTED_EXCHANGES:
        return ConnectionTestResult(
            success=False,
            status=ConnectionStatus.UNKNOWN_ERROR,
            message=f"不支持的交易所: {exchange_name}，支持的交易所: {SUPPORTED_EXCHANGES}",
            details={"supported": SUPPORTED_EXCHANGES},
        )
    
    try:
        exchange = _create_exchange_instance(
            exchange_name=exchange_name,
            api_key=api_key,
            secret_key=secret_key,
            trading_mode=trading_mode,
            proxy_url=proxy_url,
            testnet=testnet,
        )
        return exchange.test_connection()
    except Exception as e:
        logger.error(f"测试连接异常: {e}")
        return ConnectionTestResult(
            success=False,
            status=ConnectionStatus.UNKNOWN_ERROR,
            message=f"测试过程发生异常: {e}",
            details={"error": str(e)},
        )


__all__ = [
    "test_exchange_connection",
    "test_exchange_connection_sync",
    "SUPPORTED_EXCHANGES",
]
