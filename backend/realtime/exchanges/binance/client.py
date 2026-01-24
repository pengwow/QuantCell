# 币安交易所客户端
from typing import Dict, List, Any, Optional
from loguru import logger

from ...abstract_client import BaseExchangeClient
from .websocket_client import BinanceWebSocketClient
from .data_parser import BinanceDataParser


class BinanceClient(BaseExchangeClient):
    """币安交易所客户端，实现BaseExchangeClient接口"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化币安交易所客户端
        
        Args:
            config: 币安客户端配置
        """
        super().__init__(config)
        self.websocket_client = BinanceWebSocketClient(config)
        self.parser = BinanceDataParser()
        self.exchange_name = 'binance'
        
        # 币安支持的数据类型
        self.supported_data_types = {
            'kline',      # K线数据
            'depth',      # 深度数据
            'aggTrade',   # 聚合交易数据
            'trade',      # 交易数据
            'ticker',     # 完整行情数据
            'miniTicker', # 迷你行情数据
            'bookTicker'  # 最优买卖盘数据
        }
        
        # 币安支持的K线时间间隔
        self.supported_intervals = {
            '1m',  # 1分钟
            '3m',  # 3分钟
            '5m',  # 5分钟
            '15m', # 15分钟
            '30m', # 30分钟
            '1h',  # 1小时
            '2h',  # 2小时
            '4h',  # 4小时
            '6h',  # 6小时
            '8h',  # 8小时
            '12h', # 12小时
            '1d',  # 1天
            '3d',  # 3天
            '1w',  # 1周
            '1M'   # 1月
        }
    
    async def connect(self) -> bool:
        """
        建立与币安WebSocket API的连接
        
        Returns:
            bool: 连接是否成功
        """
        success = await self.websocket_client.connect()
        self.connected = success
        return success
    
    async def disconnect(self) -> bool:
        """
        断开与币安WebSocket API的连接
        
        Returns:
            bool: 断开是否成功
        """
        success = await self.websocket_client.disconnect()
        self.connected = False
        return success
    
    async def subscribe(self, channels: List[Any]) -> bool:
        """
        订阅指定的WebSocket频道
        
        Args:
            channels: 要订阅的频道列表
        
        Returns:
            bool: 订阅是否成功
        """
        # 使用通用频道解析逻辑
        parsed = self._parse_channels(channels)
        symbols = parsed['symbols']
        data_types = parsed['data_types']
        intervals = parsed['intervals']
        
        if not symbols or not data_types:
            logger.error("无法从频道参数中提取有效的交易对和数据类型")
            return False
        
        # 调用币安特定的websocket客户端订阅方法
        success = await self.websocket_client.subscribe(
            list(symbols),
            list(data_types),
            list(intervals) if intervals else None
        )
        
        if success:
            # 更新已订阅频道列表
            self.subscribed_channels.update(channels)
        
        return success
    
    async def unsubscribe(self, channels: List[Any]) -> bool:
        """
        取消订阅指定的WebSocket频道
        
        Args:
            channels: 要取消订阅的频道列表
        
        Returns:
            bool: 取消订阅是否成功
        """
        # 使用通用频道解析逻辑
        parsed = self._parse_channels(channels)
        symbols = parsed['symbols']
        data_types = parsed['data_types']
        intervals = parsed['intervals']
        
        if not symbols or not data_types:
            logger.error("无法从频道参数中提取有效的交易对和数据类型")
            return False
        
        # 调用币安特定的websocket客户端取消订阅方法
        success = await self.websocket_client.unsubscribe(
            list(symbols),
            list(data_types),
            list(intervals) if intervals else None
        )
        
        if success:
            # 更新已订阅频道列表
            for channel in channels:
                if channel in self.subscribed_channels:
                    self.subscribed_channels.remove(channel)
        
        return success
    
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """
        接收并处理WebSocket消息
        
        Returns:
            Optional[Dict[str, Any]]: 处理后的消息，None表示无消息或连接已关闭
        """
        # 检查连接状态，如果断开则尝试重连（币安特定的重连逻辑）
        if not self.connected and self.websocket_client.reconnect_count < self.websocket_client.max_reconnect:
            logger.info("WebSocket连接已断开，尝试重连")
            await self.connect()
        
        # 接收币安特定的WebSocket消息
        message = await self.websocket_client.receive_message()
        
        return message
    
    def get_data_parser(self):
        """
        获取币安特定的数据解析器实例
        
        Returns:
            Any: 数据解析器实例
        """
        return self.parser
    
    def get_available_channels(self) -> List[str]:
        """
        获取币安支持的频道列表
        
        Returns:
            List[str]: 支持的频道列表
        """
        # 注意：这里返回的是币安特定的频道模板，实际使用时需要替换为具体的交易对和参数
        available_channels = []
        
        for data_type in self.supported_data_types:
            if data_type == 'kline':
                for interval in self.supported_intervals:
                    available_channels.append(f"{{symbol}}@{data_type}_{interval}")
            else:
                available_channels.append(f"{{symbol}}@{data_type}")
        
        return available_channels
    
    @property
    def exchange_name(self) -> str:
        """
        获取交易所名称
        
        Returns:
            str: 交易所名称
        """
        return self._exchange_name
    
    @exchange_name.setter
    def exchange_name(self, value: str):
        """
        设置交易所名称
        
        Args:
            value: 交易所名称
        """
        self._exchange_name = value