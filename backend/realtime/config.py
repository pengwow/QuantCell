# 配置管理
from typing import Dict, Any, Optional
from loguru import logger


class RealtimeConfig:
    """实时引擎配置管理类"""
    
    def __init__(self):
        """初始化配置管理类"""
        # 默认配置
        self.default_config = {
            # 实时引擎开关
            'realtime_enabled': False,
            
            # 数据模式：realtime（实时模式）或 cache（缓存模式）
            'data_mode': 'cache',
            
            # 交易所配置
            'default_exchange': 'binance',
            'quote': 'USDT',  # 计价货币
            
            # 币安配置
            'binance_websocket_url': 'wss://stream.binance.com:9443/stream',
            'binance_max_reconnect': 5,
            'binance_reconnect_delay': 5,
            
            # 数据配置
            'symbols': ['BTCUSDT', 'ETHUSDT'],
            'data_types': ['kline'],
            'intervals': ['1m', '5m'],
            
            # 消费者配置
            'enable_database': True,
            'enable_memory_cache': True,
            'enable_websocket_push': True,
            
            # 监控配置
            'monitor_interval': 30,
            
            # 前端配置
            'frontend_update_interval': 1000,  # 毫秒
            'frontend_data_cache_size': 1000
        }
        
        # 当前配置
        self.config = self.default_config.copy()
    
    def load_config(self, config_dict: Dict[str, Any]) -> bool:
        """
        加载配置
        
        Args:
            config_dict: 配置字典
        
        Returns:
            bool: 加载是否成功
        """
        try:
            # 更新配置
            self.config.update(config_dict)
            logger.info("成功加载配置")
            return True
        
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return False
    
    def get_config(self, key: str = None, default: Any = None) -> Any:
        """
        获取配置
        
        Args:
            key: 配置键，None表示获取所有配置
            default: 默认值
        
        Returns:
            Any: 配置值
        """
        if key is None:
            return self.config.copy()
        
        return self.config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> bool:
        """
        设置配置
        
        Args:
            key: 配置键
            value: 配置值
        
        Returns:
            bool: 设置是否成功
        """
        try:
            self.config[key] = value
            logger.info(f"成功设置配置: {key} = {value}")
            return True
        
        except Exception as e:
            logger.error(f"设置配置失败: {e}")
            return False
    
    def reset_config(self) -> bool:
        """
        重置配置为默认值
        
        Returns:
            bool: 重置是否成功
        """
        try:
            self.config = self.default_config.copy()
            logger.info("成功重置配置为默认值")
            return True
        
        except Exception as e:
            logger.error(f"重置配置失败: {e}")
            return False
    
    def validate_config(self) -> bool:
        """
        验证配置
        
        Returns:
            bool: 验证是否通过
        """
        try:
            # 验证数据模式
            data_mode = self.config.get('data_mode', '')
            if data_mode not in ['realtime', 'cache']:
                logger.error(f"无效的数据模式: {data_mode}")
                return False
            
            # 验证交易所
            default_exchange = self.config.get('default_exchange', '')
            if default_exchange not in ['binance']:
                logger.error(f"无效的交易所: {default_exchange}")
                return False
            
            # 验证实时引擎开关
            realtime_enabled = self.config.get('realtime_enabled', False)
            if not isinstance(realtime_enabled, bool):
                logger.error(f"无效的实时引擎开关: {realtime_enabled}")
                return False
            
            # 验证符号列表
            symbols = self.config.get('symbols', [])
            if not isinstance(symbols, list):
                logger.error(f"无效的符号列表: {symbols}")
                return False
            
            # 验证数据类型列表
            data_types = self.config.get('data_types', [])
            if not isinstance(data_types, list):
                logger.error(f"无效的数据类型列表: {data_types}")
                return False
            
            # 验证时间间隔列表
            intervals = self.config.get('intervals', [])
            if not isinstance(intervals, list):
                logger.error(f"无效的时间间隔列表: {intervals}")
                return False
            
            logger.info("配置验证通过")
            return True
        
        except Exception as e:
            logger.error(f"验证配置失败: {e}")
            return False