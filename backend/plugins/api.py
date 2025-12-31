from typing import Any, Dict, List
from loguru import logger

class PluginAPI:
    """插件API，提供核心功能访问和插件间通信"""
    
    def __init__(self, plugin_manager: Any):
        """初始化插件API
        
        Args:
            plugin_manager: 插件管理器实例
        """
        self.plugin_manager = plugin_manager
        self.logger = logger.bind(component="plugin_api")
        self._registered_services: Dict[str, Any] = {}
    
    def register_service(self, name: str, service: Any) -> None:
        """注册服务，供其他插件使用
        
        Args:
            name: 服务名称
            service: 服务实例
        """
        self._registered_services[name] = service
        self.logger.info(f"服务 {name} 注册成功")
    
    def get_service(self, name: str) -> Any or None:
        """获取指定服务
        
        Args:
            name: 服务名称
            
        Returns:
            服务实例，不存在返回None
        """
        return self._registered_services.get(name)
    
    def get_plugin(self, plugin_name: str) -> Any or None:
        """获取指定插件实例
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            插件实例，不存在返回None
        """
        return self.plugin_manager.get_plugin(plugin_name)
    
    def get_all_plugins(self) -> List[str]:
        """获取所有插件名称
        
        Returns:
            插件名称列表
        """
        return list(self.plugin_manager.plugins.keys())
    
    def send_event(self, event_name: str, data: Any = None) -> None:
        """发送事件给所有插件
        
        Args:
            event_name: 事件名称
            data: 事件数据
        """
        self.logger.info(f"发送事件 {event_name}，数据: {data}")
        # 这里可以实现事件总线，通知所有插件
        # 暂时只记录日志
    
    def log(self, message: str, level: str = "info") -> None:
        """记录日志
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        getattr(self.logger, level)(message)
