# 币安WebSocket客户端
import asyncio
import websockets
import json
from typing import Dict, List, Any, Optional
from loguru import logger
from .data_parser import BinanceDataParser


class BinanceWebSocketClient:
    """币安WebSocket客户端，负责与币安WebSocket API通信"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化币安WebSocket客户端
        
        Args:
            config: 客户端配置
        """
        self.config = config
        self.base_url = config.get('base_url', 'wss://stream.binance.com:9443/ws')
        self.stream_url = config.get('stream_url', 'wss://stream.binance.com:9443/stream')
        self.websocket = None
        self.parser = BinanceDataParser()
        self.connected = False
        self.reconnect_count = 0
        self.max_reconnect = config.get('max_reconnect', 5)
        self.reconnect_delay = config.get('reconnect_delay', 5)
        self.subscriptions = set()
    
    async def connect(self) -> bool:
        """
        建立WebSocket连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info(f"正在连接到币安WebSocket: {self.stream_url}")
            
            # 建立WebSocket连接
            self.websocket = await websockets.connect(
                self.stream_url,
                ping_interval=30,
                ping_timeout=10
            )
            
            self.connected = True
            self.reconnect_count = 0
            logger.info("成功连接到币安WebSocket")
            return True
        except Exception as e:
            logger.error(f"连接币安WebSocket失败: {e}")
            self.connected = False
            return False
    
    async def disconnect(self) -> bool:
        """
        断开WebSocket连接
        
        Returns:
            bool: 断开是否成功
        """
        try:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            self.connected = False
            logger.info("成功断开币安WebSocket连接")
            return True
        except Exception as e:
            logger.error(f"断开币安WebSocket连接失败: {e}")
            return False
    
    async def reconnect(self) -> bool:
        """
        重新连接WebSocket
        
        Returns:
            bool: 重新连接是否成功
        """
        if self.reconnect_count >= self.max_reconnect:
            logger.error(f"已达到最大重连次数: {self.max_reconnect}")
            return False
        
        self.reconnect_count += 1
        delay = self.reconnect_delay * self.reconnect_count
        logger.info(f"尝试第 {self.reconnect_count} 次重连，延迟 {delay} 秒")
        
        await asyncio.sleep(delay)
        
        # 断开现有连接
        await self.disconnect()
        
        # 重新建立连接
        success = await self.connect()
        if success:
            # 重新订阅所有频道
            if self.subscriptions:
                logger.info(f"重新订阅 {len(self.subscriptions)} 个频道")
                await self._subscribe_channels(list(self.subscriptions))
        
        return success
    
    async def _subscribe_channels(self, channels: List[str]) -> bool:
        """
        订阅多个频道
        
        Args:
            channels: 要订阅的频道列表
        
        Returns:
            bool: 订阅是否成功
        """
        try:
            if not self.connected or not self.websocket:
                logger.error("WebSocket未连接，无法订阅频道")
                return False
            
            # 构建订阅消息
            subscribe_message = {
                'method': 'SUBSCRIBE',
                'params': channels,
                'id': 1
            }
            
            # 发送订阅请求
            await self.websocket.send(json.dumps(subscribe_message))
            
            # 接收订阅确认
            response = await asyncio.wait_for(self.websocket.recv(), timeout=5)
            logger.debug(f"订阅响应: {response}")
            
            # 添加到已订阅列表
            self.subscriptions.update(channels)
            logger.info(f"成功订阅 {len(channels)} 个频道")
            return True
        except Exception as e:
            logger.error(f"订阅频道失败: {e}")
            return False
    
    async def _unsubscribe_channels(self, channels: List[str]) -> bool:
        """
        取消订阅多个频道
        
        Args:
            channels: 要取消订阅的频道列表
        
        Returns:
            bool: 取消订阅是否成功
        """
        try:
            if not self.connected or not self.websocket:
                logger.error("WebSocket未连接，无法取消订阅频道")
                return False
            
            # 构建取消订阅消息
            unsubscribe_message = {
                'method': 'UNSUBSCRIBE',
                'params': channels,
                'id': 2
            }
            
            # 发送取消订阅请求
            await self.websocket.send(json.dumps(unsubscribe_message))
            
            # 接收取消订阅确认
            response = await asyncio.wait_for(self.websocket.recv(), timeout=5)
            logger.debug(f"取消订阅响应: {response}")
            
            # 从已订阅列表中移除
            self.subscriptions.difference_update(channels)
            logger.info(f"成功取消订阅 {len(channels)} 个频道")
            return True
        except Exception as e:
            logger.error(f"取消订阅频道失败: {e}")
            return False
    
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """
        接收并解析WebSocket消息
        
        Returns:
            Optional[Dict[str, Any]]: 解析后的消息，None表示连接已关闭或发生错误
        """
        try:
            if not self.connected or not self.websocket:
                logger.error("WebSocket未连接，无法接收消息")
                return None
            
            # 接收原始消息
            raw_message = await self.websocket.recv()
            
            # 解析消息
            parsed_message = self.parser.parse_message(raw_message)
            
            return parsed_message
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"WebSocket连接已关闭: {e}")
            self.connected = False
            return None
        except asyncio.TimeoutError:
            logger.warning("接收消息超时")
            return None
        except Exception as e:
            logger.error(f"接收或解析消息失败: {e}")
            return None
    
    async def subscribe(self, symbols: List[str], data_types: List[str], intervals: List[str] = None) -> bool:
        """
        订阅指定交易对的指定数据类型
        
        Args:
            symbols: 交易对列表
            data_types: 数据类型列表
            intervals: K线时间间隔列表（仅对K线数据有效）
        
        Returns:
            bool: 订阅是否成功
        """
        if not symbols or not data_types:
            logger.error("交易对或数据类型不能为空")
            return False
        
        # 构建频道列表
        channels = []
        for symbol in symbols:
            for data_type in data_types:
                if data_type == 'kline' and intervals:
                    for interval in intervals:
                        channels.append(f"{symbol.lower()}@kline_{interval}")
                else:
                    channels.append(f"{symbol.lower()}@{data_type}")
        
        return await self._subscribe_channels(channels)
    
    async def unsubscribe(self, symbols: List[str], data_types: List[str], intervals: List[str] = None) -> bool:
        """
        取消订阅指定交易对的指定数据类型
        
        Args:
            symbols: 交易对列表
            data_types: 数据类型列表
            intervals: K线时间间隔列表（仅对K线数据有效）
        
        Returns:
            bool: 取消订阅是否成功
        """
        if not symbols or not data_types:
            logger.error("交易对或数据类型不能为空")
            return False
        
        # 构建频道列表
        channels = []
        for symbol in symbols:
            for data_type in data_types:
                if data_type == 'kline' and intervals:
                    for interval in intervals:
                        channels.append(f"{symbol.lower()}@kline_{interval}")
                else:
                    channels.append(f"{symbol.lower()}@{data_type}")
        
        return await self._unsubscribe_channels(channels)
    
    @property
    def is_connected(self) -> bool:
        """
        获取连接状态
        
        Returns:
            bool: 连接状态
        """
        return self.connected