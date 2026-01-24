# 抽象交易所客户端接口
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class AbstractExchangeClient(ABC):
    """抽象交易所客户端接口，定义统一的交易所客户端行为"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化交易所客户端
        
        Args:
            config: 交易所客户端配置
        """
        self.config = config
        self.connected = False
        self.subscribed_channels = set()
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        建立与交易所WebSocket API的连接
        
        Returns:
            bool: 连接是否成功
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        断开与交易所WebSocket API的连接
        
        Returns:
            bool: 断开是否成功
        """
        pass
    
    @abstractmethod
    async def subscribe(self, channels: List[str]) -> bool:
        """
        订阅指定的WebSocket频道
        
        Args:
            channels: 要订阅的频道列表
        
        Returns:
            bool: 订阅是否成功
        """
        pass
    
    @abstractmethod
    async def unsubscribe(self, channels: List[str]) -> bool:
        """
        取消订阅指定的WebSocket频道
        
        Args:
            channels: 要取消订阅的频道列表
        
        Returns:
            bool: 取消订阅是否成功
        """
        pass
    
    @abstractmethod
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """
        接收并处理WebSocket消息
        
        Returns:
            Optional[Dict[str, Any]]: 处理后的消息，None表示无消息或连接已关闭
        """
        pass
    
    @abstractmethod
    def get_data_parser(self):
        """
        获取数据解析器实例
        
        Returns:
            Any: 数据解析器实例
        """
        pass
    
    @abstractmethod
    def get_available_channels(self) -> List[str]:
        """
        获取交易所支持的频道列表
        
        Returns:
            List[str]: 支持的频道列表
        """
        pass
    
    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """
        获取交易所名称
        
        Returns:
            str: 交易所名称
        """
        pass
    
    @property
    def is_connected(self) -> bool:
        """
        检查连接状态
        
        Returns:
            bool: 连接状态
        """
        return self.connected
    
    @property
    def subscribed_channels_list(self) -> List[str]:
        """
        获取已订阅的频道列表
        
        Returns:
            List[str]: 已订阅的频道列表
        """
        return list(self.subscribed_channels)


class BaseExchangeClient(AbstractExchangeClient):
    """基础交易所客户端，实现通用的交易所客户端逻辑"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化基础交易所客户端
        
        Args:
            config: 交易所客户端配置
        """
        super().__init__(config)
        self._exchange_name = ""
    
    @property
    @abstractmethod
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
    
    def _parse_channels(self, channels: List[Any]) -> Dict[str, set]:
        """
        通用频道解析逻辑，从频道参数中提取交易对、数据类型和时间间隔
        
        Args:
            channels: 要解析的频道列表
        
        Returns:
            Dict[str, set]: 解析后的频道参数，包含symbols、data_types和intervals
        """
        symbols = set()
        data_types = set()
        intervals = set()
        
        for channel in channels:
            if isinstance(channel, str):
                # 完整频道名格式
                try:
                    symbol_part, type_part = channel.split('@')
                    data_type = type_part.split('_')[0]
                    interval = type_part.split('_')[1] if '_' in type_part else None
                    
                    symbols.add(symbol_part.upper())
                    data_types.add(data_type)
                    if interval:
                        intervals.add(interval)
                except Exception as e:
                    from loguru import logger
                    logger.error(f"解析频道名失败: {channel}, 错误: {e}")
                    continue
            elif isinstance(channel, dict):
                # 字典格式
                symbol = channel.get('symbol', '').upper()
                data_type = channel.get('data_type', '')
                interval = channel.get('interval', '')
                
                if symbol and data_type:
                    symbols.add(symbol)
                    data_types.add(data_type)
                    if interval:
                        intervals.add(interval)
        
        return {
            'symbols': symbols,
            'data_types': data_types,
            'intervals': intervals
        }
