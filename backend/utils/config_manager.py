#!/usr/bin/env python3
"""
配置文件管理模块

用于处理config.toml配置文件的读写操作，与系统配置表兼容
"""
import os
from pathlib import Path
from typing import Dict, Any, List
from loguru import logger

# 使用tomli和tomli-w处理TOML文件
import tomli
import tomli_w


class ConfigManager:
    """配置文件管理器
    
    用于处理config.toml配置文件的读写操作
    支持与系统配置表的数据结构兼容
    """
    
    def __init__(self, config_path: str = None):
        """初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认使用backend/config.toml
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            # 默认配置文件路径
            current_dir = Path(__file__).parent.parent
            self.config_path = current_dir / "config.toml"
        
        logger.info(f"配置文件路径: {self.config_path}")
    
    def read_config(self) -> Dict[str, Any]:
        """读取配置文件
        
        Returns:
            Dict[str, Any]: 配置数据
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}")
                return {}
            
            with open(self.config_path, 'rb') as f:
                config_data = tomli.load(f)
            
            logger.info(f"成功读取配置文件: {self.config_path}")
            return config_data
        except Exception as e:
            logger.error(f"读取配置文件失败: {str(e)}")
            return {}
    
    def write_config(self, config_data: Dict[str, Any]) -> bool:
        """写入配置文件
        
        Args:
            config_data: 配置数据
            
        Returns:
            bool: 写入成功返回True，失败返回False
        """
        try:
            # 确保配置文件目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'wb') as f:
                tomli_w.dump(config_data, f)
            
            logger.info(f"成功写入配置文件: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"写入配置文件失败: {str(e)}")
            return False
    
    def save_config_items(self, config_items: List[Dict[str, Any]]) -> bool:
        """保存配置项到配置文件
        
        Args:
            config_items: 配置项列表，每个配置项包含key, value, description, name等字段
            
        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 读取现有配置
            existing_config = self.read_config()
            
            # 按name分组配置项
            config_groups = {}
            for item in config_items:
                name = item.get('name', 'system')
                if name not in config_groups:
                    config_groups[name] = {}
                
                # 处理value类型
                value = item.get('value')
                # 直接使用原始值，不进行类型转换
                config_groups[name][item['key']] = value
            
            # 将分组后的配置写入配置文件
            for group_name, group_config in config_groups.items():
                existing_config[group_name] = group_config
            
            # 写入配置文件
            return self.write_config(existing_config)
        except Exception as e:
            logger.error(f"保存配置项失败: {str(e)}")
            return False
    
    def get_config_by_group(self, group_name: str) -> Dict[str, Any]:
        """获取指定分组的配置
        
        Args:
            group_name: 分组名称
            
        Returns:
            Dict[str, Any]: 分组配置
        """
        config_data = self.read_config()
        return config_data.get(group_name, {})
    
    def get_config_item(self, group_name: str, key: str, default: Any = None) -> Any:
        """获取指定分组的指定配置项
        
        Args:
            group_name: 分组名称
            key: 配置键名
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        config_data = self.read_config()
        group_config = config_data.get(group_name, {})
        return group_config.get(key, default)
    
    def update_config_item(self, group_name: str, key: str, value: Any) -> bool:
        """更新指定分组的指定配置项
        
        Args:
            group_name: 分组名称
            key: 配置键名
            value: 配置值
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            # 读取现有配置
            existing_config = self.read_config()
            
            # 确保分组存在
            if group_name not in existing_config:
                existing_config[group_name] = {}
            
            # 直接使用原始值，不进行类型转换
            existing_config[group_name][key] = value
            
            # 写入配置文件
            return self.write_config(existing_config)
        except Exception as e:
            logger.error(f"更新配置项失败: {str(e)}")
            return False


# 创建全局配置管理器实例
config_manager = ConfigManager()


if __name__ == "__main__":
    # 测试配置管理器
    test_config_items = [
        {"key": "test_key", "value": "test_value", "description": "test.description", "name": "test_group"}
    ]
    
    # 测试保存配置项
    result = config_manager.save_config_items(test_config_items)
    print(f"保存配置项结果: {result}")
    
    # 测试读取配置
    config = config_manager.read_config()
    print(f"读取配置结果: {config}")
    
    # 测试获取分组配置
    test_group = config_manager.get_config_by_group("test_group")
    print(f"获取test_group配置: {test_group}")
