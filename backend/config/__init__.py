# 配置管理模块

import os
from pathlib import Path
from typing import Any, Dict, Optional

import tomli
from loguru import logger


class ConfigManager:
    """配置管理器类
    
    负责加载和合并配置，实现配置优先级逻辑
    """
    
    def __init__(self, config_path: str = None):
        """初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认使用backend/config.toml
        """
        # 默认配置文件路径
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.toml"
        else:
            config_path = Path(config_path)
        
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件
        
        Returns:
            Dict[str, Any]: 配置字典
        """
        try:
            if self.config_path.exists():
                with open(self.config_path, "rb") as f:
                    config = tomli.load(f)
                logger.info(f"成功加载配置文件: {self.config_path}")
                return config or {}
            else:
                logger.warning(f"配置文件不存在: {self.config_path}")
                return {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key: 配置键名，支持点分隔符，如 "database.host"
            default: 默认值，如果配置不存在则返回默认值
        
        Returns:
            Any: 配置值
        """
        try:
            keys = key.split(".")
            value = self.config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value
        except Exception as e:
            logger.error(f"获取配置失败: key={key}, error={e}")
            return default
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置
        
        Returns:
            Dict[str, Any]: 所有配置的字典
        """
        return self.config
    
    def reload(self) -> None:
        """重新加载配置
        """
        self.config = self._load_config()


# 创建全局配置管理器实例
config_manager = ConfigManager()


def get_config(key: str, default: Any = None) -> Any:
    """获取配置值的便捷函数
    
    Args:
        key: 配置键名，支持点分隔符，如 "database.host"
        default: 默认值，如果配置不存在则返回默认值
    
    Returns:
        Any: 配置值
    """
    return config_manager.get(key, default)


def get_all_configs() -> Dict[str, Any]:
    """获取所有配置的便捷函数
    
    Returns:
        Dict[str, Any]: 所有配置的字典
    """
    return config_manager.get_all()


def reload_config() -> None:
    """重新加载配置的便捷函数
    """
    config_manager.reload()
