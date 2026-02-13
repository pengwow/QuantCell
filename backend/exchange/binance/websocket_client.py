"""
Binance WebSocket客户端

实现AbstractExchangeClient接口的WebSocket客户端，用于实时数据订阅
包含自动重连和连接状态监控功能
"""

import asyncio
import json
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import time

from binance import AsyncClient
from binance.ws.streams import BinanceSocketManager
from loguru import logger

from realtime.abstract_client import AbstractExchangeClient
from .config import BinanceConfig
from .exceptions import BinanceWebSocketError, BinanceConnectionError


class BinanceWebSocketClient(AbstractExchangeClient):
    """
    Binance WebSocket客户端
    
    实现AbstractExchangeClient接口，提供实时数据订阅功能
    支持自动重连和连接状态监控
    """
    
    exchange_name: str = "binance"
    
    def __init__(self, config: Optional[BinanceConfig] = None):
        """
        初始化Binance WebSocket客户端
        
        Args:
            config: Binance配置
        """
        # 将BinanceConfig转换为字典格式
        if config is None:
            config = BinanceConfig()
        
        config_dict = {
            'api_key': config.api_key,
            'api_secret': config.api_secret,
            'testnet': config.testnet,
            'tld': config.tld,
            'proxy_url': config.proxy_url,
        }
        
        super().__init__(config_dict)
        self._binance_config = config
        self._client: Optional[AsyncClient] = None
        self._socket_manager: Optional[BinanceSocketManager] = None
        self._connected = False
        self._active_sockets: Dict[str, Any] = {}
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._receive_task: Optional[asyncio.Task] = None
        
        # 重连相关
        self._reconnect_enabled = True
        self._reconnect_delay = 5.0  # 重连延迟（秒）
        self._max_reconnect_attempts = 3
        self._reconnect_attempts = 0
        self._last_ping_time = 0
        self._ping_interval = 30  # ping间隔（秒）
        
        logger.info("BinanceWebSocketClient initialized")
    
    async def connect(self) -> bool:
        """
        建立WebSocket连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 如果已连接，先断开
            if self._connected:
                await self.disconnect()
            
            # 创建异步客户端
            self._client = await AsyncClient.create(
                api_key=self.config.get('api_key'),
                api_secret=self.config.get('api_secret'),
                testnet=self.config.get('testnet', True),
                tld=self.config.get('tld', 'com'),
            )
            
            # 创建Socket管理器
            self._socket_manager = BinanceSocketManager(self._client)
            
            self._connected = True
            self._reconnect_attempts = 0
            self._last_ping_time = time.time()
            
            logger.info("Binance WebSocket client connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect Binance WebSocket: {e}")
            self._connected = False
            return False
    
    async def disconnect(self) -> bool:
        """
        断开WebSocket连接
        
        Returns:
            bool: 断开是否成功
        """
        try:
            self._connected = False
            
            # 取消接收任务
            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
                self._receive_task = None
            
            # 关闭所有活跃的socket
            for channel, socket in list(self._active_sockets.items()):
                try:
                    if hasattr(socket, 'close'):
                        await socket.close()
                except Exception as e:
                    logger.warning(f"Error closing socket {channel}: {e}")
            self._active_sockets.clear()
            
            # 关闭客户端连接
            if self._client:
                try:
                    await self._client.close_connection()
                except Exception as e:
                    logger.warning(f"Error closing client connection: {e}")
                self._client = None
            
            self._socket_manager = None
            
            logger.info("Binance WebSocket client disconnected")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting Binance WebSocket: {e}")
            return False
    
    async def _reconnect(self) -> bool:
        """
        尝试重新连接
        
        Returns:
            bool: 重连是否成功
        """
        if not self._reconnect_enabled:
            return False
        
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"Max reconnection attempts ({self._max_reconnect_attempts}) reached")
            return False
        
        self._reconnect_attempts += 1
        logger.info(f"Attempting to reconnect... (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})")
        
        # 保存当前订阅的频道
        saved_channels = list(self.subscribed_channels)
        
        # 断开当前连接
        await self.disconnect()
        
        # 等待重连延迟
        await asyncio.sleep(self._reconnect_delay)
        
        # 尝试重新连接
        if await self.connect():
            # 重新订阅之前的频道
            if saved_channels:
                logger.info(f"Resubscribing to {len(saved_channels)} channels")
                await self.subscribe(saved_channels)
            return True
        
        return False
    
    async def subscribe(self, channels: List[str]) -> bool:
        """
        订阅指定的WebSocket频道
        
        Args:
            channels: 要订阅的频道列表，格式如 ["BTCUSDT@kline_1m", "ETHUSDT@depth"]
        
        Returns:
            bool: 订阅是否成功
        """
        try:
            if not self._connected or not self._socket_manager:
                logger.error("WebSocket not connected")
                return False
            
            for channel in channels:
                try:
                    # 如果已经订阅，跳过
                    if channel in self._active_sockets:
                        logger.debug(f"Channel {channel} already subscribed")
                        continue
                    
                    # 解析频道名
                    if '@' in channel:
                        symbol, stream_type = channel.split('@', 1)
                    else:
                        logger.warning(f"Invalid channel format: {channel}")
                        continue
                    
                    # 根据类型创建对应的socket
                    if stream_type.startswith('kline_'):
                        interval = stream_type.split('_', 1)[1]
                        socket = self._socket_manager.kline_socket(
                            symbol=symbol,
                            interval=interval
                        )
                    elif stream_type == 'depth':
                        socket = self._socket_manager.depth_socket(symbol=symbol)
                    elif stream_type == 'trade':
                        socket = self._socket_manager.trade_socket(symbol=symbol)
                    elif stream_type == 'ticker':
                        socket = self._socket_manager.ticker_socket(symbol=symbol)
                    else:
                        logger.warning(f"Unsupported stream type: {stream_type}")
                        continue
                    
                    # 建立WebSocket连接
                    try:
                        await socket.connect()
                        logger.info(f"Socket connected for channel: {channel}")
                    except Exception as e:
                        logger.error(f"Failed to connect socket for {channel}: {e}")
                        continue
                    
                    # 存储socket引用
                    self._active_sockets[channel] = socket
                    self.subscribed_channels.add(channel)
                    
                    logger.info(f"Subscribed to channel: {channel}")
                    
                except Exception as e:
                    logger.error(f"Failed to subscribe to {channel}: {e}")
                    continue
            
            # 启动消息接收任务（如果未启动）
            if not self._receive_task or self._receive_task.done():
                self._receive_task = asyncio.create_task(self._receive_messages())
            
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to channels: {e}")
            return False
    
    async def unsubscribe(self, channels: List[str]) -> bool:
        """
        取消订阅指定的WebSocket频道
        
        Args:
            channels: 要取消订阅的频道列表
        
        Returns:
            bool: 取消订阅是否成功
        """
        try:
            for channel in channels:
                if channel in self._active_sockets:
                    try:
                        socket = self._active_sockets.pop(channel)
                        if hasattr(socket, 'close'):
                            await socket.close()
                    except Exception as e:
                        logger.warning(f"Error closing socket {channel}: {e}")
                    
                    if channel in self.subscribed_channels:
                        self.subscribed_channels.remove(channel)
                    
                    logger.info(f"Unsubscribed from channel: {channel}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error unsubscribing from channels: {e}")
            return False
    
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """
        接收并处理WebSocket消息
        
        Returns:
            Optional[Dict[str, Any]]: 处理后的消息
        """
        # 实际的消息接收在_receive_messages中处理
        # 这里返回None，因为消息通过回调处理
        return None
    
    async def _receive_messages(self):
        """
        后台任务：接收所有活跃socket的消息
        包含连接断开检测和自动重连逻辑
        """
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        try:
            while self._connected:
                try:
                    # 检查是否需要发送ping保持连接
                    current_time = time.time()
                    if current_time - self._last_ping_time > self._ping_interval:
                        # 更新ping时间
                        self._last_ping_time = current_time
                    
                    # 遍历所有活跃的socket
                    for channel, socket in list(self._active_sockets.items()):
                        try:
                            # 检查socket是否已关闭
                            if hasattr(socket, '_conn') and socket._conn is None:
                                logger.warning(f"Socket {channel} connection is None, removing")
                                self._active_sockets.pop(channel, None)
                                continue
                            
                            # 使用asyncio.wait_for设置超时
                            msg = await asyncio.wait_for(socket.recv(), timeout=1.0)
                            
                            if msg:
                                # 重置连续错误计数
                                consecutive_errors = 0
                                
                                # 解析消息
                                data = json.loads(msg) if isinstance(msg, str) else msg
                                
                                # 添加频道信息
                                data['channel'] = channel

                                # 调用回调
                                for callback in self._callbacks:
                                    try:
                                        callback(data)
                                    except Exception as e:
                                        logger.error(f"[KlinePush] 回调函数执行失败: {e}")
                                
                        except asyncio.TimeoutError:
                            # 超时是正常的，继续下一个
                            continue
                        except Exception as e:
                            error_msg = str(e).lower()
                            # 检查是否是连接关闭的错误
                            if 'read loop has been closed' in error_msg or \
                               'websocket connection is closed' in error_msg or \
                               'connection reset' in error_msg:
                                logger.warning(f"Socket {channel} connection closed: {e}")
                                self._active_sockets.pop(channel, None)
                                consecutive_errors += 1
                            else:
                                logger.error(f"Error receiving message from {channel}: {e}")
                                consecutive_errors += 1
                    
                    # 如果没有活跃的socket，退出循环
                    if not self._active_sockets and self.subscribed_channels:
                        logger.warning("No active sockets but channels still subscribed")
                        consecutive_errors += 1
                    
                    # 如果连续错误过多，尝试重连
                    if consecutive_errors >= max_consecutive_errors:
                        logger.warning(f"Too many consecutive errors ({consecutive_errors}), attempting reconnect")
                        if await self._reconnect():
                            consecutive_errors = 0
                        else:
                            logger.error("Reconnection failed")
                            break
                    
                    # 短暂休眠避免CPU占用过高
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"Error in message receive loop: {e}")
                    consecutive_errors += 1
                    await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            logger.info("Message receive task cancelled")
        except Exception as e:
            logger.error(f"Fatal error in receive messages loop: {e}")
        finally:
            logger.info("Message receive task ended")
    
    def is_connected(self) -> bool:
        """
        检查是否已连接
        
        Returns:
            bool: 是否已连接
        """
        return self._connected and self._client is not None
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        获取连接状态信息
        
        Returns:
            Dict[str, Any]: 连接状态
        """
        return {
            'connected': self._connected,
            'active_sockets': len(self._active_sockets),
            'subscribed_channels': len(self.subscribed_channels),
            'reconnect_attempts': self._reconnect_attempts,
        }
    
    def get_data_parser(self):
        """
        获取数据解析器实例
        
        Returns:
            Any: 数据解析器实例
        """
        return BinanceDataParser()
    
    def get_available_channels(self) -> List[str]:
        """
        获取交易所支持的频道列表
        
        Returns:
            List[str]: 支持的频道列表
        """
        return [
            "kline", "depth", "trade", "ticker",
            "miniTicker", "bookTicker", "aggTrade"
        ]
    
    def add_message_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        添加消息回调函数
        
        Args:
            callback: 回调函数，接收消息字典
        """
        self._callbacks.append(callback)
    
    def remove_message_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        移除消息回调函数
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)


class BinanceDataParser:
    """Binance数据解析器"""
    
    def parse_kline(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析K线数据"""
        k = data.get('k', {})
        return {
            'symbol': k.get('s'),
            'open_time': k.get('t'),
            'close_time': k.get('T'),
            'open': float(k.get('o', 0)),
            'high': float(k.get('h', 0)),
            'low': float(k.get('l', 0)),
            'close': float(k.get('c', 0)),
            'volume': float(k.get('v', 0)),
            'quote_volume': float(k.get('q', 0)),
            'trades': k.get('n', 0),
            'interval': k.get('i'),
            'is_final': k.get('x', False),
        }
    
    def parse_depth(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析深度数据"""
        return {
            'symbol': data.get('s'),
            'last_update_id': data.get('u'),
            'bids': [[float(p), float(q)] for p, q in data.get('b', [])],
            'asks': [[float(p), float(q)] for p, q in data.get('a', [])],
        }
    
    def parse_trade(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析交易数据"""
        return {
            'symbol': data.get('s'),
            'trade_id': data.get('t'),
            'price': float(data.get('p', 0)),
            'quantity': float(data.get('q', 0)),
            'trade_time': data.get('T'),
            'is_buyer_maker': data.get('m', False),
        }
