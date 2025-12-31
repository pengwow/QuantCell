from loguru import logger
from typing import Any, Dict, List

class PluginBase:
    """插件基类，定义插件的生命周期方法和API"""
    
    def __init__(self, name: str, version: str):
        """初始化插件
        
        Args:
            name: 插件名称
            version: 插件版本
        """
        self.name = name
        self.version = version
        self.logger = logger.bind(plugin=self.name)
        self.plugin_manager = None
        self.is_active = False
    
    def register(self, plugin_manager: Any) -> None:
        """注册插件
        
        Args:
            plugin_manager: 插件管理器实例
        """
        self.plugin_manager = plugin_manager
        self.logger.info(f"插件 {self.name} 注册成功")
    
    def start(self) -> None:
        """启动插件"""
        self.is_active = True
        self.logger.info(f"插件 {self.name} 启动成功")
    
    def stop(self) -> None:
        """停止插件"""
        self.is_active = False
        self.logger.info(f"插件 {self.name} 停止成功")
    
    def get_info(self) -> Dict[str, str]:
        """获取插件信息
        
        Returns:
            插件信息字典
        """
        return {
            "name": self.name,
            "version": self.version,
            "is_active": self.is_active
        }
