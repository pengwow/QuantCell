# 交易所客户端工厂
from typing import Dict, Any, Optional, List
from loguru import logger
from .abstract_client import AbstractExchangeClient


class ExchangeClientFactory:
    """交易所客户端工厂，负责创建不同交易所的客户端实例"""
    
    def __init__(self):
        """初始化交易所客户端工厂"""
        self.client_registry: Dict[str, Any] = {}
        self._register_clients()
    
    def _register_clients(self) -> None:
        """
        注册支持的交易所客户端
        """
        try:
            # 注册币安客户端
            from .exchanges.binance.client import BinanceClient
            self.client_registry['binance'] = BinanceClient
            logger.info("成功注册币安客户端")
        
        except ImportError as e:
            logger.error(f"注册交易所客户端失败: {e}")
    
    def create_client(self, exchange_name: str, config: Dict[str, Any]) -> Optional[AbstractExchangeClient]:
        """
        创建交易所客户端实例
        
        Args:
            exchange_name: 交易所名称
            config: 客户端配置
        
        Returns:
            Optional[AbstractExchangeClient]: 交易所客户端实例，None表示创建失败
        """
        try:
            if exchange_name not in self.client_registry:
                logger.error(f"不支持的交易所: {exchange_name}")
                return None
            
            # 创建客户端实例
            client_class = self.client_registry[exchange_name]
            client = client_class(config)
            
            logger.info(f"成功创建交易所客户端: {exchange_name}")
            return client
        
        except Exception as e:
            logger.error(f"创建交易所客户端失败: {e}")
            return None
    
    def get_supported_exchanges(self) -> List[str]:
        """
        获取支持的交易所列表
        
        Returns:
            List[str]: 支持的交易所列表
        """
        return list(self.client_registry.keys())
    
    def is_supported(self, exchange_name: str) -> bool:
        """
        检查交易所是否支持
        
        Args:
            exchange_name: 交易所名称
        
        Returns:
            bool: 是否支持
        """
        return exchange_name in self.client_registry