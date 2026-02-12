"""
Binance WebSocket管理器

基于python-binance的BinanceSocketManager实现的WebSocket连接管理，支持：
- 多路复用WebSocket连接
- 实时K线数据订阅
- 实时深度数据订阅
- 实时交易数据订阅
- 用户数据流（账户更新、订单更新）
- 自动重连机制
- 心跳保活
"""

import asyncio
import json
from typing import Optional, Dict, Any, List, Callable, Set
from dataclasses import dataclass
from datetime import datetime
import time

from binance import AsyncClient
from binance.ws.streams import BinanceSocketManager
from loguru import logger

from .config import BinanceConfig
from .exceptions import BinanceWebSocketError, BinanceConnectionError


@dataclass
class WebSocketStats:
    """WebSocket统计信息"""
    connected_at: Optional[datetime] = None
    messages_received: int = 0
    messages_sent: int = 0
    reconnect_count: int = 0
    last_message_time: Optional[datetime] = None
    
    @property
    def connection_duration(self) -> float:
        """连接持续时间（秒）"""
        if self.connected_at:
            return (datetime.now() - self.connected_at).total_seconds()
        return 0.0


class BinanceWebSocketManager:
    """
    Binance WebSocket管理器
    
    提供实时数据订阅功能，包括：
    - K线数据
    - 深度数据
    - 交易数据
    - 用户数据流
    """
    
    def __init__(self, config: Optional[BinanceConfig] = None):
        """
        初始化WebSocket管理器
        
        Args:
            config: Binance配置
        """
        self.config = config or BinanceConfig()
        self._client: Optional[AsyncClient] = None
        self._socket_manager: Optional[BinanceSocketManager] = None
        self._connected = False
        self._stats = WebSocketStats()
        
        # 回调函数字典
        self._callbacks: Dict[str, List[Callable]] = {
            "kline": [],
            "depth": [],
            "trade": [],
            "ticker": [],
            "account": [],
            "order": [],
        }
        
        # 活跃的socket连接
        self._active_sockets: Dict[str, Any] = {}
        
        # 重连控制
        self._reconnect_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
        logger.info("BinanceWebSocketManager initialized")
    
    async def connect(self) -> bool:
        """
        建立WebSocket连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 创建异步客户端
            self._client = await AsyncClient.create(
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
                testnet=self.config.testnet,
                tld=self.config.tld,
            )
            
            # 创建Socket管理器
            self._socket_manager = BinanceSocketManager(
                client=self._client,
                user_timeout=60,
            )
            
            self._connected = True
            self._stats.connected_at = datetime.now()
            
            logger.info("Binance WebSocket connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            raise BinanceWebSocketError(f"Connection failed: {e}")
    
    async def disconnect(self):
        """断开WebSocket连接"""
        self._stop_event.set()
        
        # 关闭所有socket
        for socket_name, socket in self._active_sockets.items():
            try:
                if hasattr(socket, 'close'):
                    await socket.close()
                logger.debug(f"Closed socket: {socket_name}")
            except Exception as e:
                logger.warning(f"Error closing socket {socket_name}: {e}")
        
        self._active_sockets.clear()
        
        # 关闭客户端
        if self._client:
            await self._client.close_connection()
            self._client = None
        
        self._socket_manager = None
        self._connected = False
        
        logger.info("Binance WebSocket disconnected")
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected
    
    @property
    def stats(self) -> WebSocketStats:
        """获取统计信息"""
        return self._stats
    
    # ==================== 数据订阅接口 ====================
    
    async def subscribe_kline(self, symbol: str, interval: str = "1m") -> str:
        """
        订阅K线数据
        
        Args:
            symbol: 交易对，如 "BTCUSDT"
            interval: 时间间隔，如 "1m", "5m", "1h", "1d"
            
        Returns:
            str: 订阅ID
        """
        self._ensure_connected()
        
        socket_name = f"kline_{symbol.lower()}_{interval}"
        
        try:
            # 创建K线socket
            socket = self._socket_manager.kline_socket(
                symbol=symbol.upper(),
                interval=interval,
            )
            
            # 启动接收任务
            task = asyncio.create_task(
                self._handle_socket(socket_name, socket, "kline")
            )
            
            self._active_sockets[socket_name] = {
                "socket": socket,
                "task": task,
                "symbol": symbol,
                "interval": interval,
            }
            
            logger.info(f"Subscribed to kline: {symbol} {interval}")
            return socket_name
            
        except Exception as e:
            logger.error(f"Failed to subscribe kline: {e}")
            raise BinanceWebSocketError(f"Subscribe failed: {e}")
    
    async def subscribe_depth(self, symbol: str, depth: str = "20") -> str:
        """
        订阅深度数据
        
        Args:
            symbol: 交易对
            depth: 深度，可选 "5", "10", "20"
            
        Returns:
            str: 订阅ID
        """
        self._ensure_connected()
        
        socket_name = f"depth_{symbol.lower()}_{depth}"
        
        try:
            # 创建深度socket
            socket = self._socket_manager.depth_socket(
                symbol=symbol.upper(),
                depth=depth,
            )
            
            # 启动接收任务
            task = asyncio.create_task(
                self._handle_socket(socket_name, socket, "depth")
            )
            
            self._active_sockets[socket_name] = {
                "socket": socket,
                "task": task,
                "symbol": symbol,
                "depth": depth,
            }
            
            logger.info(f"Subscribed to depth: {symbol} {depth}")
            return socket_name
            
        except Exception as e:
            logger.error(f"Failed to subscribe depth: {e}")
            raise BinanceWebSocketError(f"Subscribe failed: {e}")
    
    async def subscribe_trade(self, symbol: str) -> str:
        """
        订阅实时交易数据
        
        Args:
            symbol: 交易对
            
        Returns:
            str: 订阅ID
        """
        self._ensure_connected()
        
        socket_name = f"trade_{symbol.lower()}"
        
        try:
            # 创建交易socket
            socket = self._socket_manager.trade_socket(symbol=symbol.upper())
            
            # 启动接收任务
            task = asyncio.create_task(
                self._handle_socket(socket_name, socket, "trade")
            )
            
            self._active_sockets[socket_name] = {
                "socket": socket,
                "task": task,
                "symbol": symbol,
            }
            
            logger.info(f"Subscribed to trade: {symbol}")
            return socket_name
            
        except Exception as e:
            logger.error(f"Failed to subscribe trade: {e}")
            raise BinanceWebSocketError(f"Subscribe failed: {e}")
    
    async def subscribe_ticker(self, symbol: str) -> str:
        """
        订阅ticker数据
        
        Args:
            symbol: 交易对
            
        Returns:
            str: 订阅ID
        """
        self._ensure_connected()
        
        socket_name = f"ticker_{symbol.lower()}"
        
        try:
            # 创建ticker socket
            socket = self._socket_manager.symbol_ticker_socket(symbol=symbol.upper())
            
            # 启动接收任务
            task = asyncio.create_task(
                self._handle_socket(socket_name, socket, "ticker")
            )
            
            self._active_sockets[socket_name] = {
                "socket": socket,
                "task": task,
                "symbol": symbol,
            }
            
            logger.info(f"Subscribed to ticker: {symbol}")
            return socket_name
            
        except Exception as e:
            logger.error(f"Failed to subscribe ticker: {e}")
            raise BinanceWebSocketError(f"Subscribe failed: {e}")
    
    async def subscribe_user_data(self) -> str:
        """
        订阅用户数据流（需要API Key）
        
        Returns:
            str: 订阅ID
        """
        self._ensure_connected()
        
        if not self.config.api_key:
            raise BinanceWebSocketError("API Key required for user data stream")
        
        socket_name = "user_data"
        
        try:
            # 创建用户数据socket
            socket = self._socket_manager.user_socket()
            
            # 启动接收任务
            task = asyncio.create_task(
                self._handle_user_socket(socket_name, socket)
            )
            
            self._active_sockets[socket_name] = {
                "socket": socket,
                "task": task,
            }
            
            logger.info("Subscribed to user data stream")
            return socket_name
            
        except Exception as e:
            logger.error(f"Failed to subscribe user data: {e}")
            raise BinanceWebSocketError(f"Subscribe failed: {e}")
    
    async def unsubscribe(self, subscription_id: str):
        """
        取消订阅
        
        Args:
            subscription_id: 订阅ID
        """
        if subscription_id not in self._active_sockets:
            logger.warning(f"Subscription not found: {subscription_id}")
            return
        
        socket_info = self._active_sockets[subscription_id]
        
        try:
            # 取消任务
            if "task" in socket_info:
                socket_info["task"].cancel()
                try:
                    await socket_info["task"]
                except asyncio.CancelledError:
                    pass
            
            # 关闭socket
            if "socket" in socket_info:
                socket = socket_info["socket"]
                if hasattr(socket, 'close'):
                    await socket.close()
            
            del self._active_sockets[subscription_id]
            logger.info(f"Unsubscribed: {subscription_id}")
            
        except Exception as e:
            logger.error(f"Error unsubscribing {subscription_id}: {e}")
    
    # ==================== 回调注册 ====================
    
    def register_callback(self, data_type: str, callback: Callable):
        """
        注册数据回调
        
        Args:
            data_type: 数据类型 (kline, depth, trade, ticker, account, order)
            callback: 回调函数
        """
        if data_type not in self._callbacks:
            self._callbacks[data_type] = []
        
        self._callbacks[data_type].append(callback)
        logger.debug(f"Registered callback for {data_type}")
    
    def unregister_callback(self, data_type: str, callback: Callable):
        """
        注销数据回调
        
        Args:
            data_type: 数据类型
            callback: 回调函数
        """
        if data_type in self._callbacks and callback in self._callbacks[data_type]:
            self._callbacks[data_type].remove(callback)
            logger.debug(f"Unregistered callback for {data_type}")
    
    # ==================== 内部方法 ====================
    
    async def _handle_socket(self, socket_name: str, socket, data_type: str):
        """处理socket消息"""
        try:
            async with socket as stream:
                while not self._stop_event.is_set():
                    try:
                        # 接收消息
                        msg = await asyncio.wait_for(
                            stream.recv(),
                            timeout=30.0,
                        )
                        
                        # 更新统计
                        self._stats.messages_received += 1
                        self._stats.last_message_time = datetime.now()
                        
                        # 处理消息
                        await self._process_message(data_type, msg)
                        
                    except asyncio.TimeoutError:
                        # 超时，继续等待
                        continue
                    except Exception as e:
                        logger.error(f"Error in socket {socket_name}: {e}")
                        break
                        
        except asyncio.CancelledError:
            logger.debug(f"Socket {socket_name} cancelled")
        except Exception as e:
            logger.error(f"Socket {socket_name} error: {e}")
            
            # 尝试重连
            if self.config.websocket_auto_reconnect:
                await self._schedule_reconnect(socket_name, data_type)
    
    async def _handle_user_socket(self, socket_name: str, socket):
        """处理用户数据socket"""
        try:
            async with socket as stream:
                while not self._stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(
                            stream.recv(),
                            timeout=60.0,  # 用户数据流超时更长
                        )
                        
                        self._stats.messages_received += 1
                        self._stats.last_message_time = datetime.now()
                        
                        # 处理用户数据
                        await self._process_user_message(msg)
                        
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Error in user socket: {e}")
                        break
                        
        except asyncio.CancelledError:
            logger.debug("User socket cancelled")
        except Exception as e:
            logger.error(f"User socket error: {e}")
    
    async def _process_message(self, data_type: str, msg: Dict[str, Any]):
        """处理消息"""
        # 标准化消息格式
        standardized_msg = self._standardize_message(data_type, msg)
        
        # 调用回调
        callbacks = self._callbacks.get(data_type, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(standardized_msg)
                else:
                    callback(standardized_msg)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    async def _process_user_message(self, msg: Dict[str, Any]):
        """处理用户数据消息"""
        event_type = msg.get("e", "")
        
        if event_type == "outboundAccountPosition":
            # 账户更新
            await self._process_message("account", msg)
        elif event_type == "executionReport":
            # 订单更新
            await self._process_message("order", msg)
    
    def _standardize_message(self, data_type: str, msg: Dict[str, Any]) -> Dict[str, Any]:
        """标准化消息格式"""
        if data_type == "kline":
            k = msg.get("k", {})
            return {
                "type": "kline",
                "symbol": msg.get("s"),
                "interval": k.get("i"),
                "open_time": k.get("t"),
                "close_time": k.get("T"),
                "open": float(k.get("o", 0)),
                "high": float(k.get("h", 0)),
                "low": float(k.get("l", 0)),
                "close": float(k.get("c", 0)),
                "volume": float(k.get("v", 0)),
                "quote_volume": float(k.get("q", 0)),
                "trades": k.get("n", 0),
                "is_closed": k.get("x", False),
                "raw": msg,
            }
        
        elif data_type == "depth":
            return {
                "type": "depth",
                "symbol": msg.get("s"),
                "last_update_id": msg.get("lastUpdateId"),
                "bids": [[float(p), float(q)] for p, q in msg.get("bids", [])],
                "asks": [[float(p), float(q)] for p, q in msg.get("asks", [])],
                "raw": msg,
            }
        
        elif data_type == "trade":
            return {
                "type": "trade",
                "symbol": msg.get("s"),
                "trade_id": msg.get("t"),
                "price": float(msg.get("p", 0)),
                "quantity": float(msg.get("q", 0)),
                "time": msg.get("T"),
                "is_buyer_maker": msg.get("m", False),
                "raw": msg,
            }
        
        elif data_type == "ticker":
            return {
                "type": "ticker",
                "symbol": msg.get("s"),
                "price_change": float(msg.get("p", 0)),
                "price_change_percent": float(msg.get("P", 0)),
                "weighted_avg_price": float(msg.get("w", 0)),
                "last_price": float(msg.get("c", 0)),
                "last_qty": float(msg.get("Q", 0)),
                "bid_price": float(msg.get("b", 0)),
                "bid_qty": float(msg.get("B", 0)),
                "ask_price": float(msg.get("a", 0)),
                "ask_qty": float(msg.get("A", 0)),
                "open_price": float(msg.get("o", 0)),
                "high_price": float(msg.get("h", 0)),
                "low_price": float(msg.get("l", 0)),
                "volume": float(msg.get("v", 0)),
                "quote_volume": float(msg.get("q", 0)),
                "open_time": msg.get("O"),
                "close_time": msg.get("C"),
                "first_trade_id": msg.get("F"),
                "last_trade_id": msg.get("L"),
                "trade_count": msg.get("n"),
                "raw": msg,
            }
        
        return {"type": data_type, "raw": msg}
    
    async def _schedule_reconnect(self, socket_name: str, data_type: str):
        """调度重连"""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        async def reconnect():
            await asyncio.sleep(self.config.websocket_reconnect_interval)
            
            try:
                # 获取socket信息
                if socket_name in self._active_sockets:
                    socket_info = self._active_sockets[socket_name]
                    symbol = socket_info.get("symbol")
                    
                    # 重新订阅
                    if data_type == "kline":
                        await self.subscribe_kline(symbol, socket_info.get("interval", "1m"))
                    elif data_type == "depth":
                        await self.subscribe_depth(symbol, socket_info.get("depth", "20"))
                    elif data_type == "trade":
                        await self.subscribe_trade(symbol)
                    elif data_type == "ticker":
                        await self.subscribe_ticker(symbol)
                    
                    self._stats.reconnect_count += 1
                    logger.info(f"Reconnected {socket_name}")
                    
            except Exception as e:
                logger.error(f"Reconnect failed: {e}")
        
        self._reconnect_task = asyncio.create_task(reconnect())
    
    def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            raise BinanceWebSocketError("Not connected. Call connect() first.")
