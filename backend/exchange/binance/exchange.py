from datetime import datetime
import time
import asyncio
from typing import Optional, List, Dict, Any

import ccxt

from exchange import Exchange, ConnectionTestResult, ConnectionStatus
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class BinanceExchange(Exchange):
    """
    定义 BinanceExchange 类，继承自 Exchange 类，用于与 Binance 交易所进行交互
    
    支持 testnet 模式（参考 QuantDinger 实现）
    """

    # Binance 测试网 URL 配置
    BINANCE_TESTNET_URLS = {
        "spot": "https://testnet.binance.vision",
        "future": "https://testnet.binancefuture.com",
    }

    def __init__(self, exchange_name: str = 'binance', api_key: Optional[str] = None, 
                 secret_key: Optional[str] = None, trading_mode: str = 'spot', 
                 proxy_url: Optional[str] = None, testnet: bool = False):
        super().__init__(exchange_name, api_key, secret_key, trading_mode, proxy_url, testnet)
        
        config = {
            'enableRateLimit': True,
            'options': {'defaultType': trading_mode},
        }
        
        if api_key:
            config['apiKey'] = api_key
        if secret_key:
            config['secret'] = secret_key
        
        if proxy_url:
            config['proxies'] = {'http': proxy_url, 'https': proxy_url}
        
        self.exchange = ccxt.binance(config)
        
        # 配置测试网络 - 完全不使用 CCXT 的 sandbox 机制
        # 只需手动覆盖所有 URL 到 testnet 端点即可（参考 QuantDinger 实现）
        if testnet:
            self._configure_testnet(trading_mode)
        
        self.exchange.parse_ohlcv = self.parse_ohlcv_custom
        self.candle_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ]
        self.trading_mode = trading_mode
        self._symbols = None
    
    def _patch_sandbox_method(self) -> None:
        """
        Monkey-patch CCXT binance 的 set_sandbox_mode 方法
        避免其检查 sapi/public 端点配置时报错
        """
        original_method = getattr(self.exchange, 'set_sandbox_mode', None)
        if original_method is not None:
            def patched_set_sandbox_mode(self_inner, enabled: bool):
                """空操作的 sandbox 模式切换（URL 已由 _configure_testnet 手动配置）"""
                self_inner.sandbox = enabled
                return self_inner
            import types
            self.exchange.set_sandbox_mode = types.MethodType(patched_set_sandbox_mode, self.exchange)
    
    def _patch_load_markets(self) -> None:
        """
        Monkey-patch load_markets 方法，忽略 CCXT 内部的 sandbox URL 检查错误
        在 sandbox=True 时，CCXT 会验证 public/sapi 端点是否存在
        testnet 模式下这些端点不适用（我们已手动配置正确的 URL）
        """
        original_load_markets = self.exchange.load_markets
        
        import types
        
        def patched_load_markets(self_inner, reload=False, params={}):
            """忽略 sandbox URL 检查错误的 load_markets"""
            try:
                return original_load_markets(reload=reload, params=params)
            except Exception as e:
                error_msg = str(e)
                if 'testnet/sandbox URL' in error_msg or 'sandbox' in error_msg.lower():
                    # 忽略 sandbox URL 检查错误，继续使用已配置的 URL 加载市场数据
                    logger.debug(f"忽略 sandbox URL 检查: {error_msg}")
                    # 直接调用底层 fetchMarkets（不经过 sandbox 检查）
                    return self_inner.fetch_markets(params=params)
                raise
        
        self.exchange.load_markets = types.MethodType(patched_load_markets, self.exchange)
    
    def _configure_testnet(self, trading_mode: str) -> None:
        """配置 Binance testnet URL（手动覆盖所有相关端点，避免 CCXT set_sandbox_mode 的 sapi 报错）"""
        # 统一处理 futures/future 两种写法
        is_futures = trading_mode in ('future', 'futures')
        
        testnet_url = self.BINANCE_TESTNET_URLS.get(trading_mode)
        if not testnet_url and is_futures:
            testnet_url = self.BINANCE_TESTNET_URLS.get('future')
        if not testnet_url:
            return
        
        base_url = testnet_url
        if is_futures:
            fapi_base = base_url + '/fapi/v1'
            self.exchange.urls['www'] = base_url
            self.exchange.urls['fapi'] = fapi_base
            self.exchange.urls['fapiPublic'] = fapi_base
            self.exchange.urls['fapiPrivate'] = fapi_base
            self.exchange.urls['public'] = fapi_base + '/ticker/price'
            self.exchange.urls['private'] = fapi_base
        else:
            self.exchange.urls['www'] = base_url
            self.exchange.urls['api'] = base_url + '/api/v3'
            self.exchange.urls['public'] = base_url + '/api/v3'
            self.exchange.urls['private'] = base_url + '/api/v3'
        
        # 覆盖 api 字典中的所有端点（将 binance.com 域名替换为 testnet 域名）
        # 注意：不设置 sandbox=True，避免触发 CCXT 的内部 URL 检查
        if isinstance(self.exchange.urls.get('api'), dict):
            for key in list(self.exchange.urls['api'].keys()):
                old_val = self.exchange.urls['api'][key]
                if not isinstance(old_val, str):
                    continue
                # 统一替换所有 binance.com 相关域名
                if 'fapi.binance.com' in old_val:
                    self.exchange.urls['api'][key] = old_val.replace('fapi.binance.com', 'testnet.binancefuture.com')
                elif 'dapi.binance.com' in old_val:
                    self.exchange.urls['api'][key] = old_val.replace('dapi.binance.com', 'testnet.binancefuture.com')
                elif 'api.binance.com' in old_val:
                    if trading_mode == 'future':
                        new_val = old_val.replace('api.binance.com', 'testnet.binancefuture.com')
                        # futures 模式下，sapi/v3 路径也需要映射到 fapi
                        new_val = new_val.replace('/api/v3/', '/fapi/v1/').replace('/api/v3', '/fapi/v1')
                        self.exchange.urls['api'][key] = new_val
                    else:
                        self.exchange.urls['api'][key] = old_val.replace('api.binance.com', 'testnet.binance.vision')

    def connect(self) -> bool:
        try:
            self.exchange.load_markets()
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Binance 连接失败: {e}")
            self._connected = False
            return False

    def health_check(self) -> bool:
        try:
            self.exchange.fetch_time()
            return True
        except Exception as e:
            logger.warning(f"健康检查失败: {e}")
            return False

    def check_status(self) -> bool:
        try:
            status = self.exchange.fetch_status()
            return status.get('status', 'unknown') == 'ok'
        except Exception:
            return self.health_check()

    def test_connection(self) -> ConnectionTestResult:
        """
        测试 Binance 交易所连通性
        使用直接 HTTP 请求（参考 QuantDinger 实现），避免 CCXT sandbox 检查问题
        """
        import time as _time
        import requests as _requests
        
        start_time = _time.time()
        details: Dict[str, Any] = {
            "tests": {},
            "exchange": self.exchange_name,
            "trading_mode": self.trading_mode,
            "testnet": self.testnet,
        }
        
        # 确定基础 URL（统一处理 futures/future 两种写法）
        is_futures = self.trading_mode in ('future', 'futures')
        
        if self.testnet:
            testnet_url = self.BINANCE_TESTNET_URLS.get(self.trading_mode, '')
            if not testnet_url and is_futures:
                testnet_url = self.BINANCE_TESTNET_URLS.get('future', '')
            if is_futures:
                base_url = testnet_url + '/fapi/v1'
            else:
                base_url = testnet_url + '/api/v3'
        else:
            if is_futures:
                base_url = 'https://fapi.binance.com/fapi/v1'
            else:
                base_url = 'https://api.binance.com/api/v3'
        
        logger.info(f"测试连接开始: exchange={self.exchange_name}, mode={self.trading_mode}, testnet={self.testnet}, base_url={base_url}")
        
        try:
            # 测试1: 直接请求 exchangeInfo（验证网络连通性）
            exchange_info_url = f"{base_url}/exchangeInfo"
            logger.debug(f"测试1 - 请求市场数据: {exchange_info_url}")
            
            t1 = _time.time()
            resp = _requests.get(exchange_info_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            symbols_count = len(data.get('symbols', []))
            elapsed_ms = (_time.time() - t1) * 1000
            
            details["tests"]["market_data"] = {
                "success": True,
                "markets_count": symbols_count
            }
            logger.info(f"测试1 市场数据通过: {symbols_count} 个交易对 ({elapsed_ms:.0f}ms)")
            
            # 测试2: 获取服务器时间（验证 API 可达性和时间同步）
            time_url = base_url.replace('/fapi/v1', '/fapi/v1').replace('/api/v3', '/api/v3')
            if '/fapi' in time_url:
                time_url = time_url.rsplit('/v1', 1)[0] + '/v1/time'
            else:
                time_url = time_url.rsplit('/v3', 1)[0] + '/v3/time'
            
            logger.debug(f"测试2 - 请求服务器时间: {time_url}")
            
            t2 = _time.time()
            try:
                time_resp = _requests.get(time_url, timeout=10)
                server_time_ms = int(time_resp.json().get('serverTime', 0))
                local_time_ms = int(_time.time() * 1000)
                time_diff = abs(server_time_ms - local_time_ms)
                elapsed_ms = (_time.time() - t2) * 1000
                
                details["tests"]["server_time"] = {
                    "success": True,
                    "time_diff_ms": time_diff
                }
                logger.info(f"测试2 时间同步通过: 差异 {time_diff}ms ({elapsed_ms:.0f}ms)")
            except Exception as time_err:
                elapsed_ms = (_time.time() - t2) * 1000
                details["tests"]["server_time"] = {
                    "success": False,
                    "error": str(time_err),
                    "note": "时间同步失败，但市场数据正常，可能是网络波动"
                }
                logger.warning(f"测试2 时间同步失败 (非致命): {time_err} ({elapsed_ms:.0f}ms)")
                time_diff = None
            
            # 测试3: API Key 认证测试（需要 API Key 时）
            if self.api_key and self.secret_key:
                logger.info("测试3 - API Key 认证测试 (有密钥)")
                auth_details = self._test_auth_direct(base_url, details)
                details["tests"]["authentication"] = auth_details
                if auth_details.get("success"):
                    logger.info(f"测试3 API 认证通过")
                else:
                    logger.warning(f"测试3 API 认证失败: {auth_details.get('error', '未知错误')}")
            else:
                details["tests"]["authentication"] = {"success": None, "message": "未提供API密钥"}
                logger.info("测试3 跳过 (未提供API密钥)")
            
            # 测试4: WebSocket 连通性测试（可选，失败不影响整体结果）
            logger.info("测试4 - WebSocket 连通性测试")
            ws_details = self._test_websocket_connection(is_futures)
            details["tests"]["websocket"] = ws_details
            if ws_details.get("success"):
                logger.info(f"测试4 WebSocket 通过")
            elif ws_details.get("error"):
                logger.warning(f"测试4 WebSocket 失败 (非致命): {ws_details.get('error', '未知错误')}")
            
            response_time_ms = (_time.time() - start_time) * 1000
            
            logger.info(
                f"测试连接全部通过: status=success, "
                f"总耗时={response_time_ms:.0f}ms, "
                f"markets={symbols_count}, time_diff={time_diff}ms"
            )
            
            return ConnectionTestResult(
                success=True,
                status=ConnectionStatus.SUCCESS,
                message=f"连接成功 (交易模式: {self.trading_mode}, 测试网: {self.testnet})",
                details=details,
                response_time_ms=response_time_ms
            )
            
        except _requests.exceptions.ConnectionError as e:
            error_msg = str(e)
            details["tests"]["network"] = {"success": False, "error": error_msg}
            logger.error(f"测试连接失败 [网络错误]: {error_msg}")
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.NETWORK_ERROR,
                message="网络连接失败，请检查代理设置或网络状态",
                details=details
            )
        except _requests.exceptions.Timeout as e:
            error_msg = str(e)
            details["tests"]["timeout"] = {"success": False, "error": error_msg}
            logger.error(f"测试连接失败 [超时]: {error_msg}")
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.TIMEOUT_ERROR,
                message="请求超时，交易所响应时间过长",
                details=details
            )
        except Exception as e:
            error_msg = str(e)
            details["tests"]["unknown"] = {"success": False, "error": error_msg}
            import traceback as _tb
            logger.error(f"测试连接失败 [未知错误]: {e}\n{_tb.format_exc()}")
            return ConnectionTestResult(
                success=False,
                status=ConnectionStatus.UNKNOWN_ERROR,
                message=f"未知错误: {error_msg}",
                details=details
            )
    
    def _test_auth_direct(self, base_url: str, details: dict) -> dict:
        """使用直接 HTTP 请求测试 API Key 认证（HMAC 签名）"""
        import hashlib
        import hmac
        import requests as _requests
        from urllib.parse import urlencode
        
        try:
            # 根据交易模式选择正确的端点（统一处理 futures/future）
            is_futures = self.trading_mode in ('future', 'futures')
            
            if is_futures:
                # futures: 主网用 v2，testnet 用 v1（更稳定）
                api_base = base_url.rstrip('/')
                if self.testnet:
                    url = f"{api_base}/balance"
                else:
                    url = f"{api_base.rsplit('/v1', 1)[0]}/v2/balance"
            else:
                # spot
                api_base = base_url.rstrip('/')
                url = f"{api_base}/account"
            
            timestamp = str(int(__import__('time').time() * 1000))
            query_string = f'timestamp={timestamp}'
            
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            headers = {'X-MBX-APIKEY': self.api_key}
            params = {'timestamp': timestamp, 'signature': signature}
            
            logger.debug(f"API认证测试请求: {url}")
            
            resp = _requests.get(url, headers=headers, params=params, timeout=10)
            
            logger.debug(f"API认证测试响应状态码: {resp.status_code}, Content-Type: {resp.headers.get('Content-Type')}")
            
            # 检查响应是否为 JSON（非 JSON 返回 HTML 错误页面）
            content_type = resp.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                raw_text = resp.text[:200]
                logger.warning(f"API返回非JSON内容 (Content-Type={content_type}): {raw_text}")
                return {"success": False, "error": f"API返回非JSON内容 ({resp.status_code}): {raw_text}"}
            
            data = resp.json()
            
            if isinstance(data, list):
                balance_available = any(float(b.get('balance', 0)) > 0 for b in data if b.get('balance'))
            elif isinstance(data, dict):
                balance_available = bool(data.get('balances') or data.get('assets'))
            else:
                balance_available = bool(data)
                
            return {"success": True, "balance_available": balance_available}
            
        except Exception as e:
            error_msg = str(e)
            
            # Binance -2015 错误的特殊处理（参考 QuantDinger）
            if "-2015" in error_msg:
                hint = (
                    f"币安接口返回 -2015（密钥/IP/权限不匹配）。请逐项核对："
                    f"① API Key 是否勾选与当前测试一致的业务；"
                    f"② 若启用 IP 白名单，是否包含当前服务器出口 IP；"
                    f"③ 测试网模式必须使用在 testnet.binance.vision 申请的专用 API Key；"
                    f"④ 无多余空格、复制完整 Secret。"
                )
                if self.testnet:
                    hint += " 当前为测试网模式，请确保使用的是测试网专用密钥。"
                return {"success": False, "error": f"{error_msg} | {hint}"}
            
            error_lower = error_msg.lower()
            if any(kw in error_lower for kw in ['permission', 'unauthorized', '-2014']):
                return {"success": False, "error": error_msg, "reason": "权限不足"}
            
            return {"success": False, "error": error_msg}

    def _test_websocket_connection(self, is_futures: bool) -> dict:
        """
        测试 WebSocket 连通性（TCP + SSL 握手）
        
        注意：WebSocket 测试是可选的，失败不会导致整体连接测试失败
        因为 WebSocket 可能因为网络环境（防火墙、代理等）无法连接
        
        Args:
            is_futures: 是否为合约模式
        
        Returns:
            dict: 包含 WebSocket 测试结果的字典
        """
        import socket as _socket
        import ssl as _ssl
        
        result = {"success": False, "error": None, "host": None, "port": None}
        
        try:
            # 确定 WebSocket 端点
            if self.testnet:
                if is_futures:
                    ws_host = "stream.binancefuture.com"
                    ws_port = 443
                    ws_url = "wss://stream.binancefuture.com/ws"
                else:
                    ws_host = "testnet.binance.vision"
                    ws_port = 443
                    ws_url = "wss://testnet.binance.vision/ws"
            else:
                if is_futures:
                    ws_host = "fstream.binance.com"
                    ws_port = 443
                    ws_url = "wss://fstream.binance.com/ws"
                else:
                    # Spot 主网使用端口 9443（官方推荐）
                    ws_host = "stream.binance.com"
                    ws_port = 9443
                    ws_url = "wss://stream.binance.com:9443/ws"
            
            result["host"] = ws_host
            result["port"] = ws_port
            result["url"] = ws_url
            
            logger.debug(f"WebSocket 测试 - 目标: {ws_url}")
            
            # 测试1: TCP 连通性
            t1 = __import__('time').time()
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(5)
            tcp_result = sock.connect_ex((ws_host, ws_port))
            elapsed_tcp = (__import__('time').time() - t1) * 1000
            
            if tcp_result != 0:
                error_messages = {
                    111: "Connection refused (连接被拒绝)",
                    110: "Connection timed out (连接超时)",
                    113: "No route to host (无路由到主机)",
                    61: "Connection refused (连接被拒绝)",
                    35: "Timeout (超时)",
                }
                error_msg = error_messages.get(tcp_result, f"Error code: {tcp_result}")
                sock.close()
                
                result["success"] = False
                result["error"] = f"TCP 连接失败 ({ws_host}:{ws_port}): {error_msg}"
                result["tcp_elapsed_ms"] = round(elapsed_tcp)
                
                logger.warning(f"WebSocket TCP 失败: {result['error']} ({elapsed_tcp:.0f}ms)")
                return result
            
            logger.info(f"WebSocket TCP 通过: {ws_host}:{ws_port} ({elapsed_tcp:.0f}ms)")
            
            # 测试2: SSL/TLS 握手
            context = _ssl.create_default_context()
            wrapped_sock = context.wrap_socket(sock, server_hostname=ws_host)
            cert = wrapped_sock.getpeercert()
            elapsed_ssl = (__import__('time').time() - t1) * 1000
            
            wrapped_sock.close()
            
            result["success"] = True
            result["ssl_elapsed_ms"] = round(elapsed_ssl)
            result["certificate"] = dict(x[0] for x in cert.get('subject', ())).get('commonName', 'N/A')
            
            logger.info(f"WebSocket SSL 通过: {ws_host}:{ws_port}, 证书={result['certificate']} ({elapsed_ssl:.0f}ms)")
            return result
            
        except _socket.gaierror as e:
            result["error"] = f"DNS 解析失败: {e}"
            logger.warning(f"WebSocket DNS 失败: {e}")
            return result
        except _socket.timeout:
            result["error"] = "连接超时"
            logger.warning("WebSocket 超时")
            return result
        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"WebSocket 异常: {e}")
            return result

    def parse_ohlcv_custom(self, ohlcv: List[Any], market: Any) -> List[Any]:
        return ohlcv

    @staticmethod
    def format_candle(candle: list) -> dict:
        return dict(
            open_time=candle[0], open=candle[1], high=candle[2], low=candle[3],
            close=candle[4], volume=candle[5], close_time=candle[6],
            quote_volume=candle[7], count=candle[8], taker_buy_volume=candle[9],
            taker_buy_quote_volume=candle[10], ignore=candle[11]
        )

    def download_data(self, symbol: str, interval: str, start_time: Optional[int] = None, 
                     end_time: Optional[int] = None, limit: int = 500, 
                     candle_type: Optional[str] = None, progress_queue: Optional[Any] = None) -> List[Dict[str, Any]]:
        try:
            ohlcv_data = self.exchange.fetch_ohlcv(symbol=symbol, timeframe=interval, since=start_time, limit=limit)
            return [self.format_candle(candle) for candle in ohlcv_data]
        except Exception as e:
            logger.error(f"下载 K 线数据失败: {e}")
            return []

    def load_data(self, symbol: str, interval: str, start_time: Optional[int] = None, 
                 end_time: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.download_data(symbol, interval, start_time, end_time)

    @property
    def symbols(self) -> List[str]:
        if not self._symbols:
            self._symbols = [symbol for symbol in self.exchange.symbols if ':' not in symbol]
        return self._symbols

    def get_balance(self) -> Dict[str, Any]:
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            logger.error(f"获取账户余额失败: {e}")
            return {}

    def set_account_config(self) -> None:
        logger.info("账户配置设置方法")


if __name__ == '__main__':
    client = BinanceExchange(testnet=True, trading_mode='future')
    print(f"支持的交易对数量: {len(client.symbols)}")
    result = client.test_connection()
    print(f"连通性测试: {result.status.value} - {result.message}")
