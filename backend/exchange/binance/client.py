"""
Binance REST API客户端

基于python-binance库实现的REST API客户端，提供账户管理、市场行情、订单操作等功能。
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from decimal import Decimal
from datetime import datetime
import time

from binance import Client, AsyncClient
from binance.exceptions import BinanceAPIException, BinanceRequestException
from loguru import logger

from .config import (
    BinanceConfig,
    OrderRequest,
    OrderResponse,
    AccountBalance,
    TickerData,
    TradingMode,
)
from .exceptions import (
    BinanceConnectionError,
    BinanceAPIError,
    BinanceOrderError,
    BinanceRateLimitError,
    BinanceAuthenticationError,
)


class BinanceClient:
    """
    Binance REST API客户端
    
    提供以下功能：
    - 账户信息查询（余额、持仓等）
    - 市场行情数据获取（K线、深度、ticker等）
    - 订单管理（下单、撤单、查询订单状态）
    - 错误处理和重试机制
    - 日志记录
    """
    
    def __init__(self, config: Optional[BinanceConfig] = None):
        """
        初始化Binance客户端
        
        Args:
            config: Binance配置，如果为None则使用默认配置
        """
        self.config = config or BinanceConfig()
        self._client: Optional[Client] = None
        self._async_client: Optional[AsyncClient] = None
        self._connected = False
        
        logger.info(f"BinanceClient initialized (testnet={self.config.testnet})")
    
    def connect(self) -> bool:
        """
        建立与Binance的连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 创建同步客户端
            self._client = Client(
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
                testnet=self.config.testnet,
                tld=self.config.tld,
                requests_params={
                    "timeout": self.config.request_timeout,
                    "proxies": {"https": self.config.proxy_url} if self.config.proxy_url else None,
                },
            )
            
            # 测试连接
            self._client.ping()
            self._connected = True
            
            logger.info("Binance client connected successfully")
            return True
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error during connection: {e}")
            raise BinanceAPIError(str(e), code=e.code)
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            raise BinanceConnectionError(str(e))
    
    async def connect_async(self) -> bool:
        """
        异步建立与Binance的连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 创建异步客户端
            self._async_client = await AsyncClient.create(
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
                testnet=self.config.testnet,
                tld=self.config.tld,
            )
            
            # 测试连接
            await self._async_client.ping()
            self._connected = True
            
            logger.info("Binance async client connected successfully")
            return True
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error during async connection: {e}")
            raise BinanceAPIError(str(e), code=e.code)
        except Exception as e:
            logger.error(f"Failed to connect to Binance async: {e}")
            raise BinanceConnectionError(str(e))
    
    def disconnect(self):
        """断开连接"""
        if self._client:
            self._client.session.close()
            self._client = None
        self._connected = False
        logger.info("Binance client disconnected")
    
    async def disconnect_async(self):
        """异步断开连接"""
        if self._async_client:
            await self._async_client.close_connection()
            self._async_client = None
        self._connected = False
        logger.info("Binance async client disconnected")
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected
    
    # ==================== 账户相关接口 ====================
    
    def get_account(self) -> Dict[str, Any]:
        """
        获取账户信息
        
        Returns:
            Dict: 账户信息
        """
        self._ensure_connected()
        try:
            return self._client.get_account()
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get account info: {e}", code=e.code)
    
    def get_balance(self, asset: Optional[str] = None) -> List[AccountBalance]:
        """
        获取账户余额
        
        Args:
            asset: 指定资产，如果为None则返回所有资产余额
            
        Returns:
            List[AccountBalance]: 余额列表
        """
        self._ensure_connected()
        try:
            account = self._client.get_account()
            balances = []
            
            for balance in account["balances"]:
                free = float(balance["free"])
                locked = float(balance["locked"])
                
                # 如果指定了资产，只返回该资产
                if asset and balance["asset"].upper() != asset.upper():
                    continue
                
                # 只返回有余额的资产（如果未指定资产）
                if not asset and free == 0 and locked == 0:
                    continue
                
                balances.append(AccountBalance(
                    asset=balance["asset"],
                    free=free,
                    locked=locked,
                ))
            
            return balances
            
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get balance: {e}", code=e.code)
    
    # ==================== 市场行情接口 ====================
    
    def get_ticker(self, symbol: str) -> TickerData:
        """
        获取最新价格
        
        Args:
            symbol: 交易对，如 "BTCUSDT"
            
        Returns:
            TickerData: 行情数据
        """
        self._ensure_connected()
        try:
            ticker = self._client.get_symbol_ticker(symbol=symbol.upper())
            return TickerData(
                symbol=ticker["symbol"],
                price=float(ticker["price"]),
                timestamp=int(time.time() * 1000),
            )
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get ticker: {e}", code=e.code)
    
    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对
            interval: 时间间隔，如 "1m", "5m", "1h", "1d"
            start_time: 开始时间（毫秒时间戳）
            end_time: 结束时间（毫秒时间戳）
            limit: 返回条数，最大1000
            
        Returns:
            List[Dict]: K线数据列表
        """
        self._ensure_connected()
        try:
            klines = self._client.get_klines(
                symbol=symbol.upper(),
                interval=interval,
                startTime=start_time,
                endTime=end_time,
                limit=limit,
            )
            
            # 转换为字典格式
            result = []
            for k in klines:
                result.append({
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6],
                    "quote_volume": float(k[7]),
                    "trades": k[8],
                    "taker_buy_base": float(k[9]),
                    "taker_buy_quote": float(k[10]),
                })
            
            return result
            
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get klines: {e}", code=e.code)
    
    def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        获取订单簿（深度）
        
        Args:
            symbol: 交易对
            limit: 深度，可选 5, 10, 20, 50, 100, 500, 1000
            
        Returns:
            Dict: 订单簿数据
        """
        self._ensure_connected()
        try:
            depth = self._client.get_order_book(symbol=symbol.upper(), limit=limit)
            return {
                "last_update_id": depth["lastUpdateId"],
                "bids": [[float(price), float(qty)] for price, qty in depth["bids"]],
                "asks": [[float(price), float(qty)] for price, qty in depth["asks"]],
            }
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get order book: {e}", code=e.code)
    
    def get_recent_trades(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        """
        获取最近成交
        
        Args:
            symbol: 交易对
            limit: 返回条数，最大1000
            
        Returns:
            List[Dict]: 成交记录列表
        """
        self._ensure_connected()
        try:
            trades = self._client.get_recent_trades(symbol=symbol.upper(), limit=limit)
            return [
                {
                    "id": t["id"],
                    "price": float(t["price"]),
                    "qty": float(t["qty"]),
                    "time": t["time"],
                    "is_buyer_maker": t["isBuyerMaker"],
                }
                for t in trades
            ]
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get recent trades: {e}", code=e.code)
    
    # ==================== 订单相关接口 ====================
    
    def create_order(self, order: OrderRequest) -> OrderResponse:
        """
        创建订单
        
        Args:
            order: 订单请求
            
        Returns:
            OrderResponse: 订单响应
        """
        self._ensure_connected()
        try:
            params = order.to_binance_params()
            response = self._client.order_limit_buy(**params) if order.order_type.value == "LIMIT" and order.side.value == "BUY" else \
                      self._client.order_limit_sell(**params) if order.order_type.value == "LIMIT" and order.side.value == "SELL" else \
                      self._client.order_market_buy(**params) if order.order_type.value == "MARKET" and order.side.value == "BUY" else \
                      self._client.order_market_sell(**params)
            
            return OrderResponse.from_binance_response(response)
            
        except BinanceAPIException as e:
            raise BinanceOrderError(
                f"Failed to create order: {e}",
                symbol=order.symbol,
            )
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """
        取消订单
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            
        Returns:
            Dict: 取消结果
        """
        self._ensure_connected()
        try:
            result = self._client.cancel_order(
                symbol=symbol.upper(),
                orderId=order_id,
            )
            return result
        except BinanceAPIException as e:
            raise BinanceOrderError(
                f"Failed to cancel order: {e}",
                order_id=str(order_id),
                symbol=symbol,
            )
    
    def get_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """
        查询订单状态
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            
        Returns:
            Dict: 订单信息
        """
        self._ensure_connected()
        try:
            order = self._client.get_order(
                symbol=symbol.upper(),
                orderId=order_id,
            )
            return order
        except BinanceAPIException as e:
            raise BinanceOrderError(
                f"Failed to get order: {e}",
                order_id=str(order_id),
                symbol=symbol,
            )
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取当前挂单
        
        Args:
            symbol: 交易对，如果为None则返回所有挂单
            
        Returns:
            List[Dict]: 挂单列表
        """
        self._ensure_connected()
        try:
            orders = self._client.get_open_orders(
                symbol=symbol.upper() if symbol else None,
            )
            return orders
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get open orders: {e}", code=e.code)
    
    def get_all_orders(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        获取所有订单
        
        Args:
            symbol: 交易对
            order_id: 从该订单ID开始查询
            start_time: 开始时间（毫秒时间戳）
            end_time: 结束时间（毫秒时间戳）
            limit: 返回条数，最大1000
            
        Returns:
            List[Dict]: 订单列表
        """
        self._ensure_connected()
        try:
            orders = self._client.get_all_orders(
                symbol=symbol.upper(),
                orderId=order_id,
                startTime=start_time,
                endTime=end_time,
                limit=limit,
            )
            return orders
        except BinanceAPIException as e:
            raise BinanceAPIError(f"Failed to get all orders: {e}", code=e.code)
    
    # ==================== 辅助方法 ====================
    
    def _ensure_connected(self):
        """确保已连接"""
        if not self._connected or not self._client:
            raise BinanceConnectionError("Client not connected. Call connect() first.")
    
    def _handle_error(self, error: Exception, operation: str):
        """处理错误"""
        if isinstance(error, BinanceAPIException):
            if error.code == -2015:  # Invalid API-key, IP, or permissions
                raise BinanceAuthenticationError(f"Authentication failed: {error}")
            elif error.code == -1003:  # Too many requests
                raise BinanceRateLimitError(f"Rate limit exceeded: {error}")
            else:
                raise BinanceAPIError(f"{operation} failed: {error}", code=error.code)
        elif isinstance(error, BinanceRequestException):
            raise BinanceConnectionError(f"Request failed: {error}")
        else:
            raise BinanceError(f"{operation} failed: {error}")
