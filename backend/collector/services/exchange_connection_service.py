"""
交易所连接测试服务

提供统一的交易所连接测试功能，支持多种交易所和代理配置
直接使用CCXT进行测试，避免抽象基类的限制
"""

import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import ccxt


class ConnectionStatus(Enum):
    """连接状态枚举"""
    SUCCESS = "success"
    NETWORK_ERROR = "network_error"
    AUTH_ERROR = "auth_error"
    PERMISSION_ERROR = "permission_error"
    PROXY_ERROR = "proxy_error"
    TIMEOUT_ERROR = "timeout_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ConnectionTestResult:
    """连接测试结果数据类"""
    success: bool
    status: ConnectionStatus
    message: str
    details: Dict[str, Any]
    response_time_ms: Optional[float] = None


class ExchangeConnectionService:
    """交易所连接测试服务"""
    
    # 超时时间（秒）
    DEFAULT_TIMEOUT = 30
    WEBSOCKET_TIMEOUT = 10
    
    # 支持的交易所列表
    SUPPORTED_EXCHANGES = ["binance", "okx"]
    
    # WebSocket URL配置
    WEBSOCKET_URLS = {
        "binance": {
            "spot": "wss://stream.binance.com:9443/ws",
            "future": "wss://fstream.binance.com/ws",
            "testnet_spot": "wss://testnet.binance.vision/ws",
            "testnet_future": "wss://stream.binancefuture.com/ws"
        },
        "okx": {
            "spot": "wss://ws.okx.com:8443/ws/v5/public",
            "future": "wss://ws.okx.com:8443/ws/v5/public",
            "testnet_spot": "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999",
            "testnet_future": "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
        }
    }
    
    async def test_connection(
        self,
        exchange_name: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        api_passphrase: Optional[str] = None,
        proxy_url: Optional[str] = None,
        trading_mode: str = "spot",
        testnet: bool = False
    ) -> ConnectionTestResult:
        """
        测试交易所连接
        
        Args:
            exchange_name: 交易所名称 (binance, okx)
            api_key: API密钥
            secret_key: API密钥
            api_passphrase: API密码（OKX需要）
            proxy_url: 代理URL
            trading_mode: 交易模式 (spot, future)
            testnet: 是否使用测试网络
            
        Returns:
            ConnectionTestResult: 连接测试结果
        """
        import time
        start_time = time.time()
        
        # 参数验证
        exchange_name = exchange_name.lower()
        if exchange_name not in self.SUPPORTED_EXCHANGES:
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.UNKNOWN_ERROR,
                message=f"不支持的交易所: {exchange_name}。支持的交易所: {', '.join(self.SUPPORTED_EXCHANGES)}",
                details={"supported_exchanges": self.SUPPORTED_EXCHANGES}
            )
        
        # 创建CCXT交易所实例
        try:
            exchange_class = getattr(ccxt, exchange_name)
            config = {
                'enableRateLimit': True,
                'options': {'defaultType': trading_mode},
            }
            
            # 添加API认证（如果有）
            if api_key:
                config['apiKey'] = api_key
            if secret_key:
                config['secret'] = secret_key
            if api_passphrase:
                config['password'] = api_passphrase
            
            # 添加代理配置
            if proxy_url:
                config['proxies'] = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            
            exchange = exchange_class(config)
            
            # 配置测试网络
            if testnet:
                exchange.set_sandbox_mode(True)
                
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.UNKNOWN_ERROR,
                message=f"创建交易所实例失败: {str(e)}",
                details={"error_type": "initialization", "error": str(e)}
            )
        
        # 执行连接测试
        try:
            # 使用asyncio.wait_for设置超时
            result = await asyncio.wait_for(
                self._perform_connection_test(exchange, exchange_name, api_key, proxy_url, trading_mode, testnet),
                timeout=self.DEFAULT_TIMEOUT
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            result.response_time_ms = round(elapsed_ms, 2)
            return result
            
        except asyncio.TimeoutError:
            elapsed_ms = (time.time() - start_time) * 1000
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.TIMEOUT_ERROR,
                message=f"连接超时，超过{self.DEFAULT_TIMEOUT}秒未响应",
                details={"timeout_seconds": self.DEFAULT_TIMEOUT},
                response_time_ms=round(elapsed_ms, 2)
            )
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.UNKNOWN_ERROR,
                message=f"测试过程中发生未知错误: {str(e)}",
                details={"error": str(e)},
                response_time_ms=round(elapsed_ms, 2)
            )
    
    async def _test_websocket_connection(
        self,
        exchange_name: str,
        trading_mode: str,
        testnet: bool,
        proxy_url: Optional[str]
    ) -> Dict[str, Any]:
        """
        测试WebSocket连接
        
        Args:
            exchange_name: 交易所名称
            trading_mode: 交易模式
            testnet: 是否使用测试网络
            proxy_url: 代理URL
            
        Returns:
            Dict: 测试结果
        """
        import aiohttp
        
        # 获取WebSocket URL
        key = f"testnet_{trading_mode}" if testnet else trading_mode
        ws_url = self.WEBSOCKET_URLS.get(exchange_name, {}).get(key)
        
        if not ws_url:
            return {
                "success": False,
                "error": f"未找到{exchange_name}的WebSocket URL配置"
            }
        
        try:
            # 设置超时
            timeout = aiohttp.ClientTimeout(total=self.WEBSOCKET_TIMEOUT)
            
            # 配置代理
            connector = None
            if proxy_url:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(proxy_url)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.ws_connect(ws_url) as ws:
                    # 发送ping测试
                    if exchange_name == "binance":
                        # Binance: 订阅ticker流
                        await ws.send_json({
                            "method": "SUBSCRIBE",
                            "params": ["btcusdt@ticker"],
                            "id": 1
                        })
                    elif exchange_name == "okx":
                        # OKX: 订阅tickers频道
                        await ws.send_json({
                            "op": "subscribe",
                            "args": [{"channel": "tickers", "instId": "BTC-USDT"}]
                        })
                    
                    # 等待响应
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.json()
                            # 检查是否收到有效数据
                            if exchange_name == "binance" and "e" in data:
                                return {
                                    "success": True,
                                    "message": "WebSocket连接成功，已收到数据"
                                }
                            elif exchange_name == "okx" and "event" in data:
                                if data.get("event") == "subscribe":
                                    return {
                                        "success": True,
                                        "message": "WebSocket连接成功，订阅已确认"
                                    }
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            return {
                                "success": False,
                                "error": f"WebSocket错误: {msg.data}"
                            }
                        
                        # 只等待一条消息就关闭
                        break
                    
                    return {
                        "success": True,
                        "message": "WebSocket连接成功"
                    }
                    
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"WebSocket连接超时({self.WEBSOCKET_TIMEOUT}秒)"
            }
        except Exception as e:
            error_msg = str(e).lower()
            if "proxy" in error_msg or "tunnel" in error_msg:
                return {
                    "success": False,
                    "error": f"WebSocket代理连接失败: {str(e)}"
                }
            return {
                "success": False,
                "error": f"WebSocket连接失败: {str(e)}"
            }
    
    async def _perform_connection_test(
        self,
        exchange: ccxt.Exchange,
        exchange_name: str,
        api_key: Optional[str],
        proxy_url: Optional[str],
        trading_mode: str,
        testnet: bool
    ) -> ConnectionTestResult:
        """
        执行实际的连接测试
        
        Args:
            exchange: CCXT交易所实例
            exchange_name: 交易所名称
            api_key: API密钥（用于判断是否有API Key）
            proxy_url: 代理URL
            trading_mode: 交易模式
            testnet: 是否使用测试网络
            
        Returns:
            ConnectionTestResult: 连接测试结果
        """
        details = {
            "exchange": exchange_name,
            "has_api_key": bool(api_key),
            "tests": {}
        }
        
        # 测试1: 基础网络连接（加载市场数据）
        try:
            await asyncio.get_event_loop().run_in_executor(None, exchange.load_markets)
            details["tests"]["ping"] = {"success": True}
        except Exception as e:
            error_msg = str(e).lower()
            details["tests"]["ping"] = {"success": False, "error": str(e)}
            
            # 判断是否为代理错误
            if "proxy" in error_msg or "tunnel" in error_msg:
                return ConnectionTestResult(
                    success=False,
                    status=ConnectionStatus.PROXY_ERROR,
                    message=f"代理连接失败: {str(e)}",
                    details=details
                )
            
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.NETWORK_ERROR,
                message=f"网络连接失败: {str(e)}",
                details=details
            )
        
        # 测试2: 交易所状态检查
        try:
            status = await asyncio.get_event_loop().run_in_executor(None, exchange.fetch_status)
            status_ok = status.get('status', 'unknown') == 'ok'
            details["tests"]["status"] = {"success": status_ok, "status": status}
            if not status_ok:
                return ConnectionTestResult(
                    success=False,
                    status=ConnectionStatus.NETWORK_ERROR,
                    message="交易所当前不可用，可能正在维护中",
                    details=details
                )
        except Exception as e:
            # fetch_status可能不被所有交易所支持，失败不直接返回错误
            details["tests"]["status"] = {"success": False, "error": str(e)}
        
        # 测试3: 获取市场数据（无需API Key）
        try:
            # 获取BTC/USDT的ticker数据作为测试
            ticker = await asyncio.get_event_loop().run_in_executor(
                None, exchange.fetch_ticker, "BTC/USDT"
            )
            details["tests"]["market_data"] = {
                "success": True,
                "symbol": "BTC/USDT",
                "last_price": ticker.get("last")
            }
        except Exception as e:
            details["tests"]["market_data"] = {"success": False, "error": str(e)}
            # 市场数据获取失败不直接返回错误，继续后续测试
        
        # 测试4: WebSocket连接测试
        try:
            ws_result = await self._test_websocket_connection(
                exchange_name, trading_mode, testnet, proxy_url
            )
            details["tests"]["websocket"] = ws_result
        except Exception as e:
            details["tests"]["websocket"] = {
                "success": False,
                "error": f"WebSocket测试异常: {str(e)}"
            }
        
        # 测试5: API认证测试（需要API Key）
        if api_key:
            try:
                balance = await asyncio.get_event_loop().run_in_executor(
                    None, exchange.fetch_balance
                )
                details["tests"]["authentication"] = {
                    "success": True,
                    "balance_available": bool(balance and balance.get('total'))
                }
            except ccxt.AuthenticationError as e:
                details["tests"]["authentication"] = {"success": False, "error": str(e)}
                return ConnectionTestResult(
                    success=False,
                    status=ConnectionStatus.AUTH_ERROR,
                    message="API Key认证失败，请检查API Key和Secret是否正确",
                    details=details
                )
            except ccxt.PermissionDenied as e:
                details["tests"]["authentication"] = {"success": False, "error": str(e)}
                return ConnectionTestResult(
                    success=False,
                    status=ConnectionStatus.PERMISSION_ERROR,
                    message="API Key权限不足，请检查API Key的权限设置",
                    details=details
                )
            except Exception as e:
                error_msg = str(e).lower()
                details["tests"]["authentication"] = {"success": False, "error": str(e)}
                
                # 判断错误类型
                if "permission" in error_msg or "unauthorized" in error_msg:
                    return ConnectionTestResult(
                        success=False,
                        status=ConnectionStatus.PERMISSION_ERROR,
                        message="API Key权限不足，请检查API Key的权限设置",
                        details=details
                    )
                elif "invalid" in error_msg or "key" in error_msg or "api" in error_msg:
                    return ConnectionTestResult(
                        success=False,
                        status=ConnectionStatus.AUTH_ERROR,
                        message="API Key无效，请检查API Key和Secret",
                        details=details
                    )
                else:
                    # 其他错误，但市场数据获取成功，认为连接基本正常
                    pass
        else:
            details["tests"]["authentication"] = {"skipped": True, "reason": "未提供API Key"}
        
        # 综合判断测试结果
        ping_success = details["tests"].get("ping", {}).get("success", False)
        market_data_success = details["tests"].get("market_data", {}).get("success", False)
        auth_success = details["tests"].get("authentication", {}).get("success", False)
        
        if ping_success and (market_data_success or auth_success):
            message = "连接测试成功"
            if api_key and auth_success:
                message += "，API认证通过"
            elif api_key and not auth_success:
                message += "，但API认证失败"
            elif not api_key:
                message += "（未测试API认证）"
                
            return ConnectionTestResult(
                success=True,
                status=ConnectionStatus.SUCCESS,
                message=message,
                details=details
            )
        else:
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.UNKNOWN_ERROR,
                message="连接测试失败，无法获取必要数据",
                details=details
            )


# 全局服务实例
exchange_connection_service = ExchangeConnectionService()
